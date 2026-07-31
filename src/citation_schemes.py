#!/usr/bin/env python3
"""Citation schemes this corpus resolves, registered with the MCP framework.

Loaded via `plugins.citation_module` in _meta/corpus.yml. Importing this module is the
whole contract — `register_scheme` calls happen at import time.

TWO DIRECTIONS, and they are not symmetric.

  INBOUND   "Report No. 2024-14" -> reports/2024-14.md. Local, exact, one candidate.
  OUTBOUND  "ORS 192.355", "OAR 137-090-0000" -> documents in a SIBLING corpus.

The outbound half is why this corpus exists. An audit finding is only useful if you can get
from it to the statute or rule the agency was found to have violated, and that document
lives in executive-regulatory-frameworks. Marking a scheme with `corpus=` is what tells the
framework to resolve it against a sibling's published index instead of locally.

REGISTER_SCHEME COMPILES WITH NO FLAGS. `re.IGNORECASE` is not applied, so every pattern
here spells out its own case handling. oregon-records-retention hit exactly this and left a
note; repeating the note rather than the mistake.
"""
from corpus_toolkit.mcp.framework import register_scheme

# ---------------------------------------------------------------- inbound: our own reports
#
# The division numbers reports YYYY-NN within a year, and cites them as "Report No. 2024-14"
# on its own site and inside the reports themselves. Both the bare number and the prose form
# must land, because an agent quoting a finding will carry whichever the report used.
#
# NN is normalised to two digits by the ingester, so `2024-5` and `2024-05` are one
# document. The pattern accepts 1-3 digits and the template pads, or `2024-5` would resolve
# to nothing while looking like a perfectly good citation.
register_scheme(
    "audit-report",
    r"(?:[Rr]eport\s+[Nn]o\.?\s*|[Aa]udit\s+[Nn]o\.?\s*)?(?P<year>20\d{2})-(?P<num>\d{1,3})",
    resolver=lambda m: [f"{m['year']}-{int(m['num']):02d}"],
)

# ---------------------------------------------------------------- outbound: sibling corpora
#
# NOW REGISTERED, together with the `siblings:` block in _meta/corpus.yml that makes them
# resolvable. The two must land together: a `corpus=` scheme with no matching sibling entry
# matches a citation and then resolves nothing, which reads as a genuine "not found" rather
# than as missing configuration.
#
# The section number requires >= 3 digits deliberately. PDF text extraction splits long
# numbers across line breaks, and "ORS 238.4" (really 238.415) occurs in this corpus. A
# looser pattern would resolve it confidently to a section that does not exist.
register_scheme("ors-section", r"ORS\s+(?P<num>\d+[A-Z]?\.\d{3,})",
                "ors-{num}", corpus="executive-regulatory-frameworks")
register_scheme("oar-rule", r"OAR\s+(?P<num>\d{3}-\d{3}-\d{4})",
                "oar-{num}", corpus="executive-regulatory-frameworks")

# ---------------------------------------------------------------- outbound: federal instruments
#
# THE MEASUREMENT THAT JUSTIFIES THIS, taken before declaring anything: of 448 federal
# citation occurrences across the 242 reports, 195 (43.5%) resolve into federal-reference.
# 2 CFR 200.303 alone is 58 of them. Only 31 reports cite a federal instrument at all -- the
# single audits carry nearly all of it -- so this edge is narrow and deep rather than broad.
#
# It is also the edge this platform was missing. An audit finds the state out of compliance
# with 2 CFR 200.303; until now the requirement it was measured against resolved to nothing.
#
# IDS COME FROM src/federal_ids.py, COPIED VERBATIM from federal-reference. Sibling
# resolution is exact-id lookup against a published corpus-index.json -- rows are
# [title, doc_type, path], with no version, no status and no search -- so a citing corpus can
# only reach a document whose id it can derive from the citation string alone. Sharing the
# derivation as a pure function means both sides compute the same ids by construction; the
# alternative is a hand-maintained table in every citing corpus, which is how
# `pl-113-128-wioa` stayed unreachable from here without anything failing.
#
# Candidates for instruments federal-reference does not hold (45 CFR 75, 42 CFR 455) are
# emitted anyway and simply miss in the index. That is deliberate: the framework reports
# "the sibling holds no document with id(s) X", which is true and useful, and the citation
# starts resolving on its own the day that instrument is ingested -- with no change here.
import pathlib as _pathlib
import sys as _sys

_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent))
from federal_ids import CFR as _F_CFR, CJIS as _F_CJIS, IRSPUB as _F_IRS, PUBLAW as _F_PL  # noqa: E402
from federal_ids import candidates as _federal_ids  # noqa: E402

for _name, _rx in (("federal-cfr", _F_CFR), ("federal-public-law", _F_PL),
                   ("federal-irs-pub", _F_IRS), ("federal-cjis", _F_CJIS)):
    register_scheme(_name, _rx.pattern,
                    # m.string, NOT m.group(0). group(0) is only the substring the
                    # instrument pattern matched, so `IRS Pub 1075 (Rev. 09-2016)` arrived
                    # here as `IRS Pub 1075` -- the revision was stripped before the id
                    # function could see it, and the citation resolved to whichever revision
                    # federal-reference happens to hold. The whole citation must reach it.
                    resolver=lambda m: _federal_ids(m.string),
                    corpus="federal-reference")
