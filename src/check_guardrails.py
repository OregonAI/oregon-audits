#!/usr/bin/env python3
"""Enforce the corpus rules that AGENTS.md states but nothing else can check.

  python3 src/check_guardrails.py            # exit 1 on any violation

WHY THIS IS A SCRIPT AND NOT SCHEMA CONFIG. `plugins.extra_schema_checks` looked like the
right home and is not: it json/yaml-parses whole FILES and validates them against a JSON
schema, which suits `_meta/catalog/*.yml` and cannot see markdown frontmatter at all. These
rules are also cross-cutting -- two of the three compare frontmatter against the body -- so
no per-file schema could express them regardless.

THE RULE ALL THREE SERVE, from AGENTS.md: an audit finding is a FINDING, not a fact about
the world. It describes one agency, during one audited period, on the evidence available
then. Everything below exists to stop this corpus quietly asserting more than the auditor
did.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"
SNAPSHOTS = ROOT / "_meta" / "snapshots"

RESPONSE_STATES = {"none_indicated", "present_not_extracted", "present_in_text"}

# Lines `## At a glance` is allowed to contain. Anything else is curator prose -- see
# check_at_a_glance.
ALLOWED_GLANCE = (
    re.compile(r"^\s*$"),                          # blank
    re.compile(r"^\*\*Report No\..*"),             # the citation/title line we generate
    re.compile(r"^- [A-Z][A-Za-z ]+:"),            # a metadata bullet we generate
    re.compile(r"^> "),                            # a quotation from the report
    re.compile(r"^### "),                          # a sub-heading we generate
    # The one sentence of our own prose allowed here, matched LITERALLY so this exemption
    # cannot become a hole. It is italic rather than a blockquote precisely so it is not
    # mistaken for the auditor's words.
    re.compile(r"^_NON-AUTHORITATIVE copy\. An audit finding is a finding, not a fact "
               r"about the world: it describes one agency during the period above, on the "
               r"evidence available then\. Verify at the source URL\._$"),
)


def sections(body: str) -> dict[str, str]:
    out, cur, buf = {}, None, []
    for line in body.splitlines():
        m = re.match(r"^## (.+?)\s*$", line)
        if m:
            if cur:
                out[cur] = "\n".join(buf)
            cur, buf = m.group(1), []
        elif cur:
            buf.append(line)
    if cur:
        out[cur] = "\n".join(buf)
    return out


def check_period(fm: dict) -> list[str]:
    """The audited period must be VISIBLE. Not necessarily known -- visible.

    Keys are required; values may be null. That distinction is the whole point. Measured
    during ingest: 8 of 8 financial audits state a period and 0 of 7 performance/IT/hotline
    audits do, because a performance audit is scoped to a topic rather than a fiscal period.
    Requiring a non-null value would therefore force either a guessed date or a failed
    ingest for a whole class of report, and a guessed date is the exact harm this field
    exists to prevent.

    What must never happen is the key being ABSENT, because then an agent cannot tell
    "not stated" from "nobody recorded it" -- and will read the finding as current.
    """
    out = []
    for key in ("audited_period_start", "audited_period_end", "audited_period_text"):
        if key not in fm:
            out.append(f"missing {key} -- an agent cannot tell an unknown period from an "
                       f"unrecorded one, and will read the finding as current")
    if "audited_period_text" in fm and not str(fm.get("audited_period_text") or "").strip():
        out.append("audited_period_text is empty; it must say something true, "
                   "e.g. 'not stated in the report'")
    return out


def check_response(fm: dict, secs: dict) -> list[str]:
    """The agency's response, where it exists, is part of the record.

    Three states, because absence of extractable TEXT is not absence of a RESPONSE. Most
    responses are appended as scanned letters with no text layer -- measured: 3 of 15
    reports say a response exists, only 1 has extractable text. Collapsing that to a
    boolean would have this corpus reporting that two thirds of disputing agencies stayed
    silent, which is not a gap but a wrong answer.
    """
    out = []
    state = fm.get("agency_response")
    if state not in RESPONSE_STATES:
        out.append(f"agency_response={state!r} is not one of {sorted(RESPONSE_STATES)}")
        return out
    has_section = "Agency response" in secs
    if state == "present_in_text" and not has_section:
        out.append("agency_response=present_in_text but there is no '## Agency response' "
                   "section -- the response is claimed and not shown")
    if state != "present_in_text" and has_section:
        out.append(f"agency_response={state} but an '## Agency response' section exists -- "
                   "the section asserts what the field denies")
    return out


def check_at_a_glance(rel: str, secs: dict) -> list[str]:
    """`## At a glance` may state metadata and QUOTE the report. It may not summarise it.

    This is the mechanical form of "never summarize a finding into a conclusion the report
    did not state". A free-prose sentence here is exactly where a plausible-sounding
    conclusion would be written, and once written nothing distinguishes it from the
    auditor's own words.

    Quotations are checked against the committed snapshot, so a `>` line cannot smuggle in
    invented text either.
    """
    out = []
    glance = secs.get("At a glance")
    if glance is None:
        return ["no '## At a glance' section"]
    snap = SNAPSHOTS / f"{rel}.txt"
    body = snap.read_text(encoding="utf-8", errors="replace") if snap.is_file() else ""
    norm = " ".join(body.split())
    for line in glance.splitlines():
        if any(rx.match(line) for rx in ALLOWED_GLANCE):
            if line.startswith("> ") and norm:
                quote = " ".join(line[2:].split())
                if len(quote) > 24 and quote not in norm:
                    out.append(f"quoted line is not in the snapshot: {quote[:70]!r}")
            continue
        out.append(f"unsourced prose in At a glance: {line.strip()[:80]!r}")
    return out


def main() -> int:
    docs = sorted(REPORTS.glob("*.md"))
    if not docs:
        print("no documents found -- refusing to pass vacuously", file=sys.stderr)
        return 1
    failures = 0
    for p in docs:
        text = p.read_text(encoding="utf-8")
        try:
            fm = yaml.safe_load(text.split("---", 2)[1])
        except Exception as e:                      # noqa: BLE001
            print(f"ERROR {p.name}: unparseable frontmatter: {e}", file=sys.stderr)
            failures += 1
            continue
        secs = sections(text)
        problems = (check_period(fm)
                    + check_response(fm, secs)
                    + check_at_a_glance(p.stem, secs))
        for msg in problems:
            print(f"ERROR {p.name}: {msg}", file=sys.stderr)
        failures += bool(problems)

    print(f"guardrails: {len(docs) - failures}/{len(docs)} documents clean")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
