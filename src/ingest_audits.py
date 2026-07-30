#!/usr/bin/env python3
"""Fetch each manifest source, snapshot it, and write reports/<report-no>.md.

  python3 src/ingest_audits.py                 # ingest everything in the manifest
  python3 src/ingest_audits.py --limit 5       # first N, for a smoke run
  python3 src/ingest_audits.py --only 2024-33  # one report
  python3 src/ingest_audits.py --refetch       # ignore cached snapshots

HOW THE PDF IS OBTAINED, which is mostly not a download.

240 of 242 sources point at an ORMS WebDrawer viewer page, and ORMS exposes no direct file
endpoint — /Record/<id>/file, /PlayStream/<id>, /Download/<id> and four other spellings all
404 (probed). The document is instead base64-encoded into a <script> in the viewer:

    var myPdfBase64 = 'JVBERi0xLjYN...'      # 'JVBERi0' is '%PDF-1'

So those fetch ~6 MB of HTML to obtain ~2 MB of PDF. The other two are plain PDFs on
sos.oregon.gov, and they are the two most RECENT reports — see fetch_pdf() for all three
shapes, and for why handling only the ORMS one silently loses new publications.

WHAT GETS WRITTEN, and why `## Full text` is the whole document.

corpus-verify-provenance requires every line under `## Full text` to appear IN ORDER in the
snapshot, with >= 0.70 coverage. Quoting selected findings would satisfy that only by
accident and would silently drop the rest of the report. The whole extracted text goes in,
which makes the check exact rather than approximate, and keeps the curator out of deciding
which findings matter -- a decision this corpus must never make (see AGENTS.md).

`## At a glance` carries METADATA ONLY, plus the report's own highlights section quoted
verbatim when it has one. It never contains a sentence about the findings that the report
did not itself write.
"""
from __future__ import annotations

import argparse
import base64
import re
import sys
import time
import urllib.request
from pathlib import Path

import yaml
from pypdf import PdfReader

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from corpus_toolkit.repo import hash_snapshot           # noqa: E402

MANIFEST = REPO_ROOT / "_meta" / "source-manifest.yml"
SNAPSHOTS = REPO_ROOT / "_meta" / "snapshots"
OUT_DIR = REPO_ROOT / "reports"
UA = ("OregonAI-corpus-bot/0.1 (+https://github.com/OregonAI/oregon-audits; "
      "civic corpus ingest)")

B64 = re.compile(r"var myPdfBase64 = '([A-Za-z0-9+/=]+)'")

# Deliberately conservative. A false positive here puts a passage under a heading claiming
# the agency said it, which is worse than having no section at all.
#
# A looser pattern was tried and measured WRONG: it reported 5 of 15 reports as having a
# response, and every extra hit was incidental prose -- "management's responses to our
# inquiries" is audit methodology, not an agency response. Matching a heading on its own
# line is the version that does not invent disputes.
RESPONSE_HEAD = re.compile(
    r"^[ \t]*((?:agency|management|department|division|commission)(?:['’]s)?"
    r"[ \t]+(?:response|comments)"
    r"|response\s+(?:to|from)\s+(?:the\s+)?(?:agency|audit))[ \t]*$",
    re.I | re.M)

# THE REPORT SAYING a response exists. Load-bearing, because most responses are appended as
# SCANNED LETTERS on agency letterhead: the pages are images, pypdf extracts nothing from
# them, and the response is therefore in the PDF but not in our text.
#
# Measured on 15 reports: 3 say a response exists, only 1 has extractable letter text. If
# absence of text were reported as absence of a response, this corpus would say two thirds
# of disputing agencies stayed silent. That is not a gap, it is a wrong answer.
RESPONSE_POINTER = re.compile(
    r"(?:response|responses)\s+can\s+be\s+found"
    r"|response\s+(?:is|are)\s+(?:included|attached|appended)"
    r"|agreed\s+with\s+(?:all\s+of\s+)?(?:our|the)\s+recommendations", re.I)

# The report's own summary heading, quoted rather than paraphrased.
HIGHLIGHT_HEAD = re.compile(
    r"^[ \t]*(what we found|report highlights|summary|executive summary)[ \t]*$", re.I | re.M)

# Only patterns that state an AUDIT SCOPE period. Bare "fiscal year 2018" is excluded on
# purpose: measured, it matches incidental prose (caseload counts, cited reports) far more
# often than the audited period, and a wrong period is worse than a null one.
PERIOD = re.compile(
    r"for the (?:fiscal )?(?:year|biennium|period)s?\s+end(?:ed|ing)\s+"
    r"([A-Z][a-z]+ \d{1,2},? \d{4})"
    r"|fiscal years?\s+(20\d\d)\s*(?:and|through|-|–)\s*(20\d\d)",
    re.I)

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], 1)}


def fetch_pdf(url: str, dest: Path, refetch: bool) -> bytes:
    """THREE upstream URL shapes, and assuming one of them loses reports.

    Found the hard way: a first full run failed on exactly three sources, and each was a
    shape this function did not handle.

      .../Recordhtml/<id>   the ORMS viewer, PDF base64-encoded inside a <script>. 239/242.
      .../Record/<id>       the ORMS metadata page — 13 KB, no payload. Rewritten to
                            Recordhtml, which is the same record.
      .../Documents/*.pdf   a plain PDF on sos.oregon.gov. Only 2 of 242 sources, but they
                            are the two most RECENT reports, so a fetcher that only speaks
                            ORMS would quietly stop working as the division publishes.
    """
    if dest.is_file() and not refetch:
        return dest.read_bytes()

    if "/ORSOSWebDrawer/Record/" in url:
        url = url.replace("/ORSOSWebDrawer/Record/", "/ORSOSWebDrawer/Recordhtml/")

    req = urllib.request.Request(url, headers={"User-Agent": UA})
    body = urllib.request.urlopen(req, timeout=180).read()

    if body.startswith(b"%PDF"):
        raw = body
    else:
        m = B64.search(body.decode("utf-8", "replace"))
        if not m:
            raise ValueError("neither a PDF nor an ORMS viewer with a myPdfBase64 payload")
        raw = base64.b64decode(m.group(1))
    if not raw.startswith(b"%PDF"):
        raise ValueError(f"payload is not a PDF (starts {raw[:8]!r})")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(raw)
    return raw


def page_furniture(pages: list[list[str]]) -> tuple[set[str], set[str]]:
    """Lines repeated at the top/bottom of most pages: letterhead, banners, footers.

    Same idea as oregon-records-retention's ingester. A line only counts as furniture if it
    appears on more than half the pages -- a threshold that keeps a genuine repeated heading
    in a short report from being stripped as chrome.
    """
    if len(pages) < 4:
        return set(), set()
    top, bot = {}, {}
    for p in pages:
        for l in [x.strip() for x in p[:3] if x.strip()]:
            top[l] = top.get(l, 0) + 1
        for l in [x.strip() for x in p[-3:] if x.strip()]:
            bot[l] = bot.get(l, 0) + 1
    half = len(pages) / 2
    return ({l for l, n in top.items() if n > half},
            {l for l, n in bot.items() if n > half})


def is_page_number(line: str, npages: int) -> bool:
    s = line.strip()
    return bool(re.fullmatch(r"(page\s+)?\d{1,3}(\s*(of|/)\s*\d{1,3})?", s, re.I)) and \
        len(s) <= 16 and npages > 1


def extract_text(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    pages = [(p.extract_text() or "").splitlines() for p in reader.pages]
    head, foot = page_furniture(pages)
    out: list[str] = []
    for lines in pages:
        for l in lines:
            s = l.strip()
            if not s or s in head or s in foot or is_page_number(s, len(pages)):
                continue
            out.append(s)
    # Collapse runs of blank lines; keep single blanks as paragraph separators.
    text = "\n".join(out)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    # A LINE OF PDF TEXT THAT STARTS WITH '## ' TRUNCATES THE DOCUMENT.
    #
    # corpus_toolkit.repo.FULLTEXT_RE reads the section as
    #     ^## Full text\s*$(.*?)(?=^## |\Z)
    # so the FIRST line beginning '## ' at column zero ends it. Six reports contain exactly
    # that -- footnote markers extracted as '##' -- and each silently lost half its body:
    # 2021-36 shipped 58,359 of 111,606 characters while `## Full text` looked complete and
    # was byte-identical to the snapshot. It surfaced only as a coverage error.
    #
    # One leading space fixes it: the regex anchors '##' at column zero so it no longer
    # matches, and normalize_ws() erases the space before any comparison, so the verbatim
    # in-order check and source_sha256 are both unaffected. Applied HERE, in extraction, so
    # the committed .txt and the document body stay identical to each other.
    return re.sub(r"^(#{1,6}\s)", r" \1", text, flags=re.M)


def find_section(text: str, head_re: re.Pattern) -> str | None:
    """Text from a matched heading to the next all-caps/Title-Case heading, verbatim."""
    m = head_re.search(text)
    if not m:
        return None
    start = m.end()
    rest = text[start:]
    nxt = re.search(r"\n[ \t]*(?:[A-Z][A-Za-z ]{4,50}|[A-Z][A-Z ]{4,50})\n", rest)
    body = rest[:nxt.start()] if nxt else rest[:4000]
    body = body.strip()
    return body or None


def parse_period(text: str) -> tuple[str | None, str | None, str]:
    """(start, end, human text). Returns nulls freely -- see AGENTS.md.

    27% of a measured sample state no audit-scope period at all, so a null here is a NORMAL
    outcome and not a failure. The one thing that must never happen is a guessed date: an
    agent reading a fabricated period would date a finding wrongly, which is precisely the
    harm this field exists to prevent.
    """
    m = PERIOD.search(text)
    if not m:
        return None, None, "not stated in the report"
    if m.group(1):
        raw = m.group(1).replace(",", "")
        parts = raw.split()
        try:
            end = f"{int(parts[2]):04d}-{MONTHS[parts[0].lower()]:02d}-{int(parts[1]):02d}"
        except (KeyError, ValueError, IndexError):
            return None, None, " ".join(m.group(0).split())
        return None, end, " ".join(m.group(0).split())
    y1, y2 = m.group(2), m.group(3)
    return f"{y1}-07-01", f"{y2}-06-30", " ".join(m.group(0).split())


RESP_LABEL = {
    "present_in_text": "included below, quoted from the report",
    "present_not_extracted": "THE REPORT STATES ONE EXISTS, but it is an appended scanned "
                             "letter with no text layer — read it at the source URL",
    "none_indicated": "nothing in the report indicates one",
}


def build_document(src: dict, text: str, sha: str, report_date: str) -> str:
    rid = src["id"]
    p_start, p_end, p_text = parse_period(text)
    highlights = find_section(text, HIGHLIGHT_HEAD)
    response = find_section(text, RESPONSE_HEAD)
    # Three distinct states, and conflating any two of them misleads:
    #   present_in_text        we have the response and quote it
    #   present_not_extracted  the report says there is one; it is a scanned letter
    #   none_indicated         nothing in the report indicates a response
    if response:
        resp_state = "present_in_text"
    elif RESPONSE_POINTER.search(text):
        resp_state = "present_not_extracted"
    else:
        resp_state = "none_indicated"

    fm = {
        "schema_version": 1,
        "corpus": "oregon-audits",
        "jurisdiction": "oregon",
        "id": rid,
        "title": src.get("title") or f"Audit Report {rid}",
        "doc_type": "audit_report",
        "citation": src["citation"],
        "authority_level": "audit",
        "issuing_body": "Oregon Secretary of State, Audits Division",
        "agency": src.get("audited_agency"),
        "report_number": rid,
        "audit_type": src.get("audit_type"),
        "audited_agency": src.get("audited_agency"),
        "report_date": report_date,
        # Keys ALWAYS present, values may be null. See AGENTS.md: the harm this guards
        # against is an agent silently assuming a finding is current, and an explicit null
        # plus honest text prevents that. A guessed date would not.
        "audited_period_start": p_start,
        "audited_period_end": p_end,
        "audited_period_text": p_text,
        # NOT a boolean. "false" would be read as "the agency did not respond", which is a
        # claim this corpus cannot make from a text layer that omits scanned letters.
        "agency_response": resp_state,
        "source_url": src["url"],
        "source_format": "pdf",
        "retrieved": time.strftime("%Y-%m-%d"),
        "source_sha256": sha,
        "status": "current",
        "content_mode": "verbatim",
        # The raw PDFs are NOT committed, and this is the toolkit's supported way to say so
        # ("e.g. huge image-scan PDFs" -- provenance.py:86). Forced by a hard constraint:
        # the 242 source PDFs total 767 MiB, and 2022-36.pdf alone is 182 MiB, over
        # GitHub's 100 MB per-file hard limit. The push would be rejected outright.
        #
        # Nothing is weakened. With a committed .txt, hash-only still verifies
        # source_sha256 against that text AND still runs the full-text coverage check --
        # the same two guarantees a committed PDF would buy. What is lost is the archival
        # copy, which matters here because this publisher's URLs demonstrably rot (the 2019
        # reports already moved), so it is a real cost and not a free win.
        "snapshot_policy": "hash-only",
        "maintainer": "@morficflux",
        # Written EMPTY on purpose. The schema requires both keys; a human sets them at PR
        # approval. An ingester that stamps a date it did not earn is worse than a blank.
        "last_verified": "",
        "verified_by": "",
    }
    head = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True, width=100).rstrip()

    parts = [f"---\n{head}\n---\n", "## At a glance\n"]
    parts.append(
        f"**{src['citation']}** — {fm['title']}\n\n"
        f"- Audited agency: {fm['audited_agency'] or 'not stated'}\n"
        f"- Audit type: {fm['audit_type'] or 'not stated'}\n"
        f"- Report date: {report_date}\n"
        f"- Period audited: {p_text}\n"
        f"- Agency response: {RESP_LABEL[resp_state]}\n\n"
        "> NON-AUTHORITATIVE copy. An audit finding is a finding, not a fact about the "
        "world: it describes one agency during the period above, on the evidence available "
        "then. Verify at the source URL.\n")
    if highlights:
        parts.append("\n### The report's own summary, quoted\n\n"
                     + "\n".join(f"> {l}" for l in highlights.splitlines()[:40]) + "\n")
    if response:
        parts.append("\n## Agency response\n\n"
                     "_Quoted from the report. Where an agency disputed a finding, that "
                     "dispute is part of the record._\n\n"
                     + "\n".join(f"> {l}" for l in response.splitlines()[:60]) + "\n")
    parts.append("\n## Full text\n\n" + text + "\n")
    return "\n".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--only", metavar="REPORT_NO")
    ap.add_argument("--refetch", action="store_true")
    args = ap.parse_args()

    sources = yaml.safe_load(MANIFEST.read_text())["sources"]
    if args.only:
        sources = [s for s in sources if s["id"] == args.only] or sys.exit(
            f"no manifest source with id {args.only!r}")
    if args.limit:
        sources = sources[:args.limit]

    OUT_DIR.mkdir(exist_ok=True)
    SNAPSHOTS.mkdir(parents=True, exist_ok=True)
    ok = failed = 0
    for i, src in enumerate(sources, 1):
        rid = src["id"]
        try:
            pdf = SNAPSHOTS / f"{rid}.pdf"
            fresh = not pdf.is_file() or args.refetch
            fetch_pdf(src["url"], pdf, args.refetch)
            text = extract_text(pdf)
            if len(text) < 500:
                raise ValueError(f"only {len(text)} chars extracted — scanned or broken PDF")
            (SNAPSHOTS / f"{rid}.txt").write_text(text, encoding="utf-8")
            sha = hash_snapshot(rid, "pdf", SNAPSHOTS)
            year = str(src.get("report_year") or rid[:4])
            month = re.match(r"\s*(\d{1,2})", str(src.get("report_month") or ""))
            report_date = f"{year}-{int(month.group(1)):02d}-01" if month else f"{year}-01-01"
            (OUT_DIR / f"{rid}.md").write_text(
                build_document(src, text, sha, report_date), encoding="utf-8")
            ok += 1
            print(f"  [{i}/{len(sources)}] {rid}  {len(text):>7,} chars")
            if fresh:
                time.sleep(2)          # polite: ~6 MB fetched per report
        except Exception as e:                      # noqa: BLE001 — reported, not hidden
            failed += 1
            print(f"  [{i}/{len(sources)}] {rid}  FAILED: {type(e).__name__}: {e}",
                  file=sys.stderr)

    print(f"\n{ok} ingested, {failed} failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
