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
