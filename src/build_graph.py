#!/usr/bin/env python3
"""Build _meta/graph.json — the node/edge artifact the toolkit reads.

WHY THIS FILE EXISTS IN THE TEMPLATE. The toolkit only ever READS the graph; it
never writes one. Without it `resolve_citation`, `graph_neighbors` and
`authority_chain` return nothing at all — not an error, just empty results — and
`corpus-validate-frontmatter --changed` loses the universe it resolves
relationship targets against. That failure is completely silent, so a corpus can
look healthy while its citation resolution does nothing. Every corpus needs a
graph builder; this is a working generic one.

It is deliberately simple: nodes from frontmatter, edges from each document's
`relationships` block. That is enough for any corpus whose relationships are
hand-authored or written by its own ingester.

MOST CORPORA WILL OUTGROW IT. The mature reference corpus
(OregonAI/executive-regulatory-frameworks) derives edges MECHANICALLY instead —
parsing authority citations out of each document's own text, resolving statute
renumbering, and keeping implements/implemented_by mirrors symmetric — because
hand-authored edges do not scale to 69,395 documents and drift from the text
they claim to represent. When this corpus reaches that point, replace the
`edges_for` function below rather than bolting derivation on elsewhere.

Cross-corpus targets: an edge whose `to` is a citation string ("ORS 192.311")
rather than a local id is CORRECT and expected — the referenced document lives
in a sibling corpus (see corpus.yml `siblings:`). Those are emitted as-is and
counted separately, so an unresolvable `to` means "look next door", not "broken".

  python3 src/build_graph.py           # write _meta/graph.json
  python3 src/build_graph.py --check   # exit 1 if stale (wire this into CI)
"""
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "_meta/corpus.yml"

_FM = re.compile(r"\A---\n(.*?)\n---\n", re.S)
REL_KEYS = ("implements", "implemented_by", "references_external", "related", "supersedes")


def frontmatter(path: Path) -> dict | None:
    m = _FM.match(path.read_text(encoding="utf-8"))
    return yaml.safe_load(m.group(1)) if m else None


def content_files(config: dict):
    """Every document under the configured content roots.

    Mirrors the toolkit's own scan rules: files beginning with `_` (so `_index.md`)
    and CHANGELOG.md are structure, not content, and are skipped. Keeping this in
    step with the toolkit matters — a node the validator expects but the graph
    lacks becomes an unresolvable relationship target."""
    for root in config.get("content_roots") or []:
        base = ROOT / root["path"]
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.md")):
            if path.name.startswith("_") or path.name == "CHANGELOG.md":
                continue
            yield path


# Citations mined from the report text. Both are anchored on the ORS/OAR prefix so a bare
# number in a table cannot masquerade as a statute.
#
# ORS sections are `chapter.section` with an optional letter suffix on the chapter (163A).
# The section is required to be >= 3 digits: PDF extraction splits long numbers across line
# breaks, and "ORS 238.4" -- a real artifact in this corpus, from "238.415" -- would
# otherwise be emitted as a confident edge to a section that does not exist.
_ORS = re.compile(r"\bORS\s+(\d+[A-Z]?\.\d{3,})")
_OAR = re.compile(r"\bOAR\s+(\d{3}-\d{3}-\d{4})")

# FEDERAL requirements. Single audits are audits AGAINST federal rules, so these edges are
# the state's compliance surface -- and they point at a set Oregon's own rules largely do
# not cite. Measured across this corpus: 2 CFR 200 (the Uniform Guidance, which governs
# every federal grant Oregon receives) is named 180 times here and has ZERO authority
# claims in executive-regulatory-frameworks.
#
# That is the case for emitting them: an intake list built only from what Oregon RULES cite
# would rank IDEA and the Columbia River Gorge first and never reach the broadest
# obligation the state has. These edges are unresolvable until OregonAI/federal-reference
# exists, which is expected -- the module docstring covers cross-corpus targets.
_FED = re.compile(r"\b(\d{1,2})\s+(U\.?\s?S\.?\s?C\.?|C\.?\s?F\.?\s?R\.?)"
                  r"\s*(?:Part\s+|§+\s*)?(\d+[A-Za-z]?)")


def edges_for(fm: dict, body: str = "") -> list[dict]:
    """Edges out of one document: hand-authored relationships, plus statute and rule
    citations mined from the report's own text.

    THE EDGE TYPE IS `references_external`, AND THAT IS A DELIBERATE LIMIT ON THE CLAIM.

    An audit citing ORS 293.726 does NOT mean the agency was found to have violated it. It
    may be the authority for the audit itself, a standard the auditor applied, statutory
    background, or a recommendation's legal basis. Only the report's prose says which, and
    this function does not read prose. Emitting `implements` -- or anything that reads as a
    finding of non-compliance -- would be inventing the auditor's conclusion, which is the
    one thing AGENTS.md forbids outright.

    So the edge means exactly "this report cites this document, go read it", and the reason
    lives in `## Full text` where the auditor wrote it.

    Targets are CITATION STRINGS, not local ids -- these documents live in
    executive-regulatory-frameworks. The module docstring covers why that is expected.
    """
    out = []
    for key in REL_KEYS:
        for target in (fm.get("relationships") or {}).get(key) or []:
            out.append({"from": fm["id"], "type": key, "to": target})
    seen = set()
    for label, rx in (("ORS", _ORS), ("OAR", _OAR)):
        for num in rx.findall(body):
            target = f"{label} {num}"
            if target not in seen:
                seen.add(target)
                out.append({"from": fm["id"], "type": "references_external", "to": target})
    for title, kind, num in _FED.findall(body):
        k = "USC" if kind.upper().replace(" ", "").replace(".", "").startswith("USC") else "CFR"
        target = f"{title} {k} {num}"
        if target not in seen:
            seen.add(target)
            out.append({"from": fm["id"], "type": "references_external", "to": target})
    return out


def build() -> dict:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    nodes, edges = [], []
    for path in content_files(config):
        fm = frontmatter(path)
        if not fm or not fm.get("id"):
            continue
        nodes.append({"id": fm["id"], "title": fm.get("title", ""),
                      "doc_type": fm.get("doc_type", ""),
                      "status": fm.get("status", ""),
                      "path": str(path.relative_to(ROOT))})
        text = path.read_text(encoding="utf-8")
        body = text.split("## Full text", 1)[1] if "## Full text" in text else ""
        edges.extend(edges_for(fm, body))
    local = {n["id"] for n in nodes}
    return {"corpus": (config.get("corpus") or {}).get("id", ""),
            "n_nodes": len(nodes), "n_edges": len(edges),
            "n_edges_external": sum(1 for e in edges if e["to"] not in local),
            "nodes": nodes, "edges": edges}


def main():
    graph = build()
    text = json.dumps(graph, ensure_ascii=False, indent=1) + "\n"
    out = ROOT / ((yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {})
                  .get("graph_path") or "_meta/graph.json")
    if "--check" in sys.argv:
        if not out.exists() or out.read_text(encoding="utf-8") != text:
            print(f"{out.relative_to(ROOT)} is stale — run: python3 src/build_graph.py")
            sys.exit(1)
        print(f"{out.relative_to(ROOT)} is current.")
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    ext = f", {graph['n_edges_external']} pointing outside this corpus" if graph["n_edges_external"] else ""
    print(f"wrote {out.relative_to(ROOT)}: {graph['n_nodes']} nodes, {graph['n_edges']} edges{ext}")


if __name__ == "__main__":
    main()
