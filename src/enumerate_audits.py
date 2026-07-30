#!/usr/bin/env python3
"""Discover every Secretary of State audit report and write _meta/source-manifest.yml.

  python3 src/enumerate_audits.py            # rewrite the manifest
  python3 src/enumerate_audits.py --check    # exit 1 if the manifest would change (CI)

WHERE THE DATA ACTUALLY COMES FROM, because it is not the page a human would guess.

`sos.oregon.gov/audits/pages/state-audits.aspx` renders nothing server-side. Its table is a
DataTables web part whose configuration names the real source:

    "dataSource": "list", "sharePointListUrl": "/audits/Lists/Audit Search",
    "tableCaption": "State Audits and Reviews 2020 to present"

So enumeration reads that SharePoint list over REST rather than scraping HTML. Note the
caption: the division itself declares the list starts at 2020. That is the same boundary
found independently by fetching 2019 PDFs (they 404 while 2026 ones resolve) — two
unrelated signals agreeing, which is why the corpus floor is 2020 and not 2019.

TWO ROW SHAPES LIVE IN THIS LIST, and only one of them is this corpus.

  * 248 rows carry `Report No. YYYY-NN` in Link.Description, plus a type and an agency.
    Those are the audit reports. They are what we ingest.
  * 309 rows carry no report number, no type, and link out of an HTML field instead.
    They are per-agency financial attestation — 148 "Selected Financial Accounts",
    127 "Statewide Single Audit", plus management letters and interim letters.

Their ORMS record ids do not overlap AT ALL (measured: 234 ids vs 264 ids, intersection
empty), so the unnumbered rows are separate publications and not attachments to the
numbered ones. They are deliberately OUT of scope: every document here must carry a
citable report number, and 275 of the 309 are routine attestation that would dominate
every search result. Revisit only when something actually needs them.
"""
from __future__ import annotations

import argparse
import collections
import html as _html
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "_meta" / "source-manifest.yml"

LIST_API = ("https://sos.oregon.gov/audits/_api/web/lists/getbytitle('Audit%20Search')"
            "/items?$top=500")
RECENT_URL = "https://sos.oregon.gov/audits/Pages/recent.aspx"
UA = ("OregonAI-corpus-bot/0.1 (+https://github.com/OregonAI/oregon-audits; "
      "civic corpus ingest)")

# Report numbers are zero-padded to two digits so `2024-05` and `2024-5` are one id and
# sort correctly. Three-digit numbers have never appeared; if one does, the padding leaves
# it alone rather than truncating.
REPNO = re.compile(r"\b(20\d{2})-(\d{1,3})\b")


def _get(url: str, accept: str = "text/html") -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    return urllib.request.urlopen(req, timeout=60).read()


def _norm_repno(text: str) -> str | None:
    m = REPNO.search(text or "")
    return f"{m.group(1)}-{int(m.group(2)):02d}" if m else None


def _urls(item: dict) -> list[str]:
    """Every URL on a row, from both places the list stores them.

    Link.Url is the primary field. Additional_x0020_Documents is an HTML blob whose hrefs
    are entity-escaped (`https&#58;//...`), which no amount of urllib will fix for you —
    unescape before use or every URL 404s in a way that looks like link rot.
    """
    out = []
    primary = ((item.get("Link") or {}).get("Url") or "").strip()
    if primary:
        out.append(primary)
    out += re.findall(r'href="([^"]+)"', item.get("Additional_x0020_Documents") or "")
    return [_html.unescape(u).replace("&#58;", ":") for u in out]


def fetch_list() -> list[dict]:
    """Every row of the Audit Search list, following OData paging."""
    items, url = [], LIST_API
    while url:
        page = json.loads(_get(url, "application/json;odata=nometadata"))
        items += page.get("value", [])
        url = page.get("odata.nextLink")
        if url:
            time.sleep(1)          # be a polite guest on a government web server
    return items


def fetch_recent_numbers() -> set[str]:
    """Report numbers on the static `recent.aspx` page, as an independent cross-check.

    This page is genuinely server-rendered, unlike the search page, so it is the one place
    a second opinion is available for free. It is only a rolling window of the newest
    reports per category — never treat it as a catalogue.
    """
    try:
        text = _get(RECENT_URL).decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError) as e:
        print(f"WARNING: recent.aspx unreachable ({e}); cross-check skipped", file=sys.stderr)
        return set()
    return {f"{y}-{int(n):02d}" for y, n in REPNO.findall(text)}


def build_records(items: list[dict]) -> tuple[list[dict], list[str]]:
    """(manifest records, anomalies). Anomalies are reported, never silently resolved."""
    anomalies: list[str] = []
    by_num: dict[str, dict] = {}

    for it in items:
        num = _norm_repno((it.get("Link") or {}).get("Description") or "")
        if not num:
            continue                                    # unnumbered row: out of scope
        urls = [u for u in _urls(it) if u]
        if not urls:
            anomalies.append(f"{num}: numbered row with no URL at all")
            continue
        rec = {
            "id": num,
            "url": urls[0],
            # The URL serves HTML, and saying `pdf` here would be a lie with consequences:
            # corpus-detect-changes would run pdftotext over an HTML page. The document
            # itself is base64 inside a <script> in that HTML (see ingest_audits.py), so
            # html_to_text excludes it and the drift hash tracks the record's displayed
            # metadata — 386 stable chars, measured. That is blind to the PDF changing,
            # which is ACCEPTABLE here and nowhere else: an audit report is immutable once
            # published. What we need drift detection for is link rot, and a dead URL
            # still surfaces as a fetch failure.
            "format": "html",
            "citation": f"Report No. {num}",
            "title": (it.get("Title") or "").strip(),
            "doc_type": "audit_report",
            "audit_type": ((it.get("Audit_x0020_Type") or [None])[0] or "").lower() or None,
            "audited_agency": (it.get("Agency") or [None])[0],
            "report_year": it.get("Year"),
            "report_month": it.get("Month"),
            "recheck": "annual",
            "sha256": "",
            "why_relevant": "Audits Division findings and recommendations, with the "
                            "audited agency's response.",
            "references_out": [],
        }
        if num in by_num:
            anomalies.append(f"{num}: appears on more than one list row "
                             f"({by_num[num]['title'][:40]!r} / {rec['title'][:40]!r})")
            continue
        by_num[num] = rec

    return [by_num[k] for k in sorted(by_num)], anomalies


def gap_report(records: list[dict], items: list[dict]) -> list[str]:
    """Missing report numbers, each with a reason. A silent gap is a missing document.

    Numbering is per-year and not dense. A hole can mean the report was withdrawn — the
    list literally contains a row reading "Report No. 2023-15 removed in accordance with
    GAGAS 3.34" — or that it is unpublished, or that enumeration lost it. Those are very
    different, and only the last one is a bug, so each is named rather than counted.
    """
    withdrawn = {}
    for it in items:
        t = it.get("Title") or ""
        if re.search(r"\bremoved\b|\bwithdraw", t, re.I):
            n = _norm_repno(t)
            if n:
                withdrawn[n] = " ".join(t.split())

    have = collections.defaultdict(set)
    for r in records:
        y, n = r["id"].split("-")
        have[int(y)].add(int(n))

    lines = []
    for year in sorted(have):
        ns = have[year]
        for missing in sorted(set(range(1, max(ns) + 1)) - ns):
            num = f"{year}-{missing:02d}"
            lines.append(f"{num}: {withdrawn.get(num, 'not present in the Audit Search list')}")
    return lines


def render(records: list[dict], gaps: list[str], anomalies: list[str]) -> str:
    note = (
        "Every upstream source this corpus consumes. Human-approved via PR BEFORE any\n"
        "ingestion. GENERATED by src/enumerate_audits.py — do not hand-edit; re-run it.\n"
        "\n"
        "Source: the SharePoint list behind sos.oregon.gov/audits/pages/state-audits.aspx,\n"
        "which renders nothing server-side. The list is captioned by the division itself as\n"
        "'State Audits and Reviews 2020 to present', which is why this corpus floors at 2020.\n"
        "\n"
        "Traps recorded so a future re-enumeration does not fall into them:\n"
        "1. The search page's HTML carries a fresh __VIEWSTATE per request, so its bytes are\n"
        "   never stable. Compare the extracted RECORD SET, never the page.\n"
        "2. hrefs inside Additional_x0020_Documents are entity-escaped (`https&#58;//`).\n"
        "   Unescape them or every URL 404s in a way that looks exactly like link rot.\n"
        "3. Report numbers are NOT dense. A gap can be a withdrawal under GAGAS 3.34 — one\n"
        "   really is — so every gap is listed below with a reason rather than skipped.\n"
        "4. `format: html` is deliberate and is NOT a mistake: these URLs serve an HTML\n"
        "   viewer with the PDF base64-encoded inside a <script>. Declaring `pdf` would run\n"
        "   pdftotext over HTML.\n"
    )
    doc = {
        "note": note,
        "index": "https://sos.oregon.gov/audits/pages/state-audits.aspx",
        "list_api": LIST_API,
        "recheck": "annual",
        "coverage": {
            "floor": "2020 — the upstream list does not go earlier",
            "in_scope": "numbered audit reports (Report No. YYYY-NN)",
            "out_of_scope": "unnumbered per-agency financial attestation rows, and "
                            "municipal/local-government filings",
        },
        "numbering_gaps": gaps,
        "anomalies": anomalies,
        "sources": records,
    }
    return yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if the manifest is not what enumeration produces")
    args = ap.parse_args()

    items = fetch_list()
    records, anomalies = build_records(items)
    gaps = gap_report(records, items)
    recent = fetch_recent_numbers()

    print(f"list rows: {len(items)}   numbered reports: {len(records)}   "
          f"gaps: {len(gaps)}   anomalies: {len(anomalies)}")

    # RECONCILIATION. recent.aspx is server-rendered and independent of the list, so a
    # report visible there and absent here means enumeration is incomplete — the one
    # failure this whole step exists to catch. Fail loudly; a short manifest that looks
    # fine is worse than no manifest.
    known = {r["id"] for r in records}
    missed = sorted(n for n in recent if n not in known and n.split("-")[0] >= "2020")
    if missed:
        print(f"\nABORT: {len(missed)} report(s) on recent.aspx are absent from the list: "
              f"{missed[:8]}", file=sys.stderr)
        print("Enumeration is incomplete; the manifest was NOT written.", file=sys.stderr)
        return 1
    if recent:
        print(f"cross-check: {len(recent & known)} of {len(recent)} recent.aspx numbers "
              f"confirmed present")

    text = render(records, gaps, anomalies)
    if args.check:
        current = MANIFEST.read_text(encoding="utf-8") if MANIFEST.is_file() else ""
        if current != text:
            print("\nsource-manifest.yml is STALE — re-run src/enumerate_audits.py",
                  file=sys.stderr)
            return 1
        print("source-manifest.yml is current.")
        return 0

    MANIFEST.write_text(text, encoding="utf-8")
    print(f"wrote {MANIFEST.relative_to(REPO_ROOT)}: {len(records)} source(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
