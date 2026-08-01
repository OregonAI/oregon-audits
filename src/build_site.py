#!/usr/bin/env python3
"""Build the GitHub Pages site into ./site/ (gitignored; produced at deploy time).

    python3 src/build_site.py

Chrome, CSS and the cross-corpus contracts live in `corpus_toolkit.site` — see that module
for why they are shared rather than copied per corpus. This file owns only what is specific
to this corpus: its numbers and what they mean.

THIS REPLACES the reusable publish-index workflow, which publishes corpus-index.json and
nothing else — hence the 404 at the site root. The two must never both exist here; they
fight over the `pages` concurrency group.
"""
import collections
import json
import pathlib
import sys

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from corpus_toolkit import config as config_mod                       # noqa: E402
from corpus_toolkit.site import Page, Section, Tile, build            # noqa: E402

REPO = pathlib.Path(__file__).resolve().parent.parent


def stats() -> dict:
    years = collections.Counter()
    for p in (REPO / "reports").glob("*.md"):
        fm = yaml.safe_load(p.read_text().split("---", 2)[1]) or {}
        d = str(fm.get("report_date") or "")
        if d[:4].isdigit():
            years[d[:4]] += 1
    g = json.loads((REPO / "_meta/graph.json").read_text())
    citing = {e["from"] for e in g["edges"]}
    kinds = collections.Counter(e["to"].split()[0] for e in g["edges"])
    return {"reports": g["n_nodes"], "edges": g["n_edges"],
            "citing": len(citing), "pct": round(len(citing) / g["n_nodes"] * 100),
            "first": min(years), "last": max(years),
            "ors": kinds.get("ORS", 0), "oar": kinds.get("OAR", 0)}


def main() -> int:
    s = stats()
    out = build(Page(
        config=config_mod.load(REPO / "_meta/corpus.yml"),
        repo="oregon-audits",
        title="Oregon Audits — Secretary of State audit reports",
        description=("A non-authoritative, machine-readable mirror of Oregon Secretary of "
                     "State audit reports, with the statutes and rules each one examined."),
        eyebrow="Oregon · Secretary of State Audits Division",
        headline="What the state's own auditors found",
        lede_html=(
            f"<b>{s['reports']} audit reports</b>, {s['first']} to {s['last']} — findings, "
            "recommendations, and the audited agency's response. The only corpus on this "
            "platform that reports on whether the rest of the chain actually worked."),
        disclaimer=("NON-AUTHORITATIVE reference — not the official audit report. Always "
                    "verify against the Secretary of State Audits Division."),
        tiles=[
            Tile("Audit reports", f"{s['reports']}", f"{s['first']} to {s['last']}"),
            Tile("Cite statute or rule", f"{s['pct']}%",
                 f"{s['citing']} of {s['reports']} reports name the law they examined"),
            Tile("Citations resolved", f"{s['edges']}",
                 f"{s['ors']} ORS, {s['oar']} OAR, the rest federal"),
        ],
        sections=[
            Section("A finding is not a fact", """
    <ul class="plain">
      <li>An audit report says what the <b>auditors concluded</b>. This corpus records that
        as a finding attributed to the Audits Division — never as a statement about the
        world, and never as a statement the audited agency agreed with.</li>
      <li>Agency responses are part of the record. Where a report contains one, its
        presence is recorded rather than silently dropped, because a finding without the
        response is half the document.</li>
      <li>CI enforces this. A guardrail fails the build if a finding is rendered as an
        unattributed assertion.</li>
    </ul>"""),
            Section("Where an audit points", """
    <ul class="plain">
      <li>Citations resolve into
        <a href="https://oregonai.github.io/executive-regulatory-frameworks/">Executive
        Regulatory Frameworks</a> for ORS and OAR, and into
        <a href="https://oregonai.github.io/federal-reference/">Federal Reference</a> for
        2 CFR 200, 42 USC and 45 CFR — the federal requirements Oregon agencies are audited
        against.</li>
      <li>Recorded as <code>references_external</code>, not <code>implements</code>: the
        measurable claim is that the report cites the section, not that it construes it.</li>
    </ul>"""),
            Section("For agents", """
    <ul class="plain">
      <li><b>MCP server</b> — tools: <code>search_corpus</code>, <code>get_document</code>,
        <code>resolve_citation</code>, <code>corpus_overview</code>,
        <code>graph_neighbors</code>, <code>authority_chain</code>.</li>
      <li><b>Every report carries provenance</b> — source URL, retrieval date and a content
        hash.</li>
    </ul>"""),
        ],
        footer_note=("Unofficial and non-authoritative; not affiliated with the Oregon "
                     "Secretary of State."),
    ))
    print(f"built site/ — {s['reports']} reports, {s['first']}-{s['last']}")
    print(f"  corpus-index.json: {out['index']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
