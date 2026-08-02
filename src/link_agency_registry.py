#!/usr/bin/env python3
"""Crosswalk this corpus's audited agencies to the ERF agency registry, and keep it honest.

  python3 src/link_agency_registry.py --check              # CI: committed data only
  python3 src/link_agency_registry.py --verify-registry    # local: slugs exist in ERF
  python3 src/link_agency_registry.py --stamp              # write registry fields into reports/
  python3 src/link_agency_registry.py --unresolved-report  # human work list

ADAPTED FROM oregon-kpm/src/link_agency_registry.py, which records the architectural
reasoning in full: why a crosswalk and not a citation scheme (an agency is not a document
in any corpus-index.json, so no `register_scheme` can express this join), and why the table
lives in the consumer rather than in ERF (`link_budget_codes.py` writing budget codes INTO
ERF works for one consumer and scales badly; ERF's own `_meta/agency-profiles.yml` is the
counter-precedent — a side-file owned by the thing that needs it). Correctness still
belongs to ERF: --verify-registry resolves every slug against the real registry, and a
slug this file invents is a failure.

WHAT IS DELIBERATELY DIFFERENT FROM THE KPM VERSION. That corpus derives an `agency_key`
that collapses cover-page spelling variation, so its crosswalk keys are derived tokens.
Here the ingester already writes one canonical `audited_agency` string per agency, so the
crosswalk is keyed on the EXACT frontmatter string — 40 of them, measured. If a future
ingest introduces a 41st spelling, --check fails with an unclassified key, which is the
correct pressure: classify it, don't normalise it away.

--stamp EXISTS BECAUSE THE DOCUMENTS PREDATE THE CROSSWALK. ingest_audits.py now stamps
`agency_registry_slug`/`agency_registry_corpus` at build time for new reports, but the 242
committed documents were built before the crosswalk existed and re-ingesting them would
re-stamp `retrieved` dates nothing else changed. --stamp inserts (or corrects) exactly the
two registry lines in place and touches nothing else. Idempotent; a second run is a no-op.

CI MUST NOT NEED ERF. `--check` validates only what is committed here: every
audited_agency in reports/ is accounted for, nothing is both mapped and unmapped, every
unmapped entry states a reason, every non-exact basis states its identity argument, and
every document whose agency is mapped carries the stamp. Referential integrity against
the sibling is --verify-registry, run locally and in review.
"""
from __future__ import annotations

import argparse
import difflib
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"
CROSSWALK = ROOT / "_meta" / "agency-crosswalk.yml"
REPORT_OUT = ROOT / "_meta" / "unresolved-agencies.md"

REGISTRY_CORPUS = "executive-regulatory-frameworks"
# Probed in order, --registry overrides. ERF is checked out under its own name on some
# machines and under its former repo name `oregon-policy-repo` on others.
REGISTRY_CANDIDATES = [
    ROOT.parent / "executive-regulatory-frameworks" / "_meta" / "catalog" / "agencies.yml",
    ROOT.parent / "oregon-policy-repo" / "_meta" / "catalog" / "agencies.yml",
]

BASES = {"exact", "alias", "successor", "manual"}

STAMP_RE = re.compile(r"^agency_registry_(slug|corpus): .*\n", re.M)


def frontmatter(path: Path) -> dict:
    parts = path.read_text(encoding="utf-8", errors="replace").split("---", 2)
    return yaml.safe_load(parts[1]) if len(parts) >= 3 else {}


def corpus_names() -> dict[str, int]:
    """{audited_agency string: document count} over every committed report."""
    out: dict[str, int] = {}
    for p in sorted(REPORTS.glob("*.md")):
        name = frontmatter(p).get("audited_agency")
        if name:
            out[name] = out.get(name, 0) + 1
    return out


def load_crosswalk() -> dict:
    if not CROSSWALK.is_file():
        sys.exit(f"missing {CROSSWALK.relative_to(ROOT)}")
    return yaml.safe_load(CROSSWALK.read_text(encoding="utf-8")) or {}


def find_registry(explicit: str | None) -> Path | None:
    if explicit:
        p = Path(explicit)
        return p if p.is_file() else None
    return next((p for p in REGISTRY_CANDIDATES if p.is_file()), None)


def registry_slugs(path: Path) -> set[str]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {o["slug"] for o in data.get("organizations") or [] if o.get("slug")}


def stamp_state(mapping: dict) -> tuple[int, int]:
    """(documents whose agency is mapped, of those, how many carry the correct stamp)."""
    want = stamped = 0
    for p in sorted(REPORTS.glob("*.md")):
        fm = frontmatter(p)
        entry = mapping.get(fm.get("audited_agency") or "")
        if entry:
            want += 1
            stamped += (fm.get("agency_registry_slug") == entry.get("slug")
                        and fm.get("agency_registry_corpus") == REGISTRY_CORPUS)
    return want, stamped


def check(cw: dict, names: dict[str, int]) -> list[str]:
    """Committed-data-only validation. Never touches the sibling."""
    mapping = cw.get("mapping") or {}
    unmapped = cw.get("unmapped") or {}
    bad = []

    # A HALF-STAMPED CORPUS IS THE FAILURE THIS CATCHES: editing the crosswalk without
    # re-stamping leaves documents whose agency IS mapped carrying no link (or a stale
    # one), and the corpus then answers "no registry link" for an agency the crosswalk
    # maps — which reads as a decision rather than as staleness.
    want, stamped = stamp_state(mapping)
    if want != stamped:
        bad.append(f"{want - stamped} document(s) have a mapped audited_agency but a "
                   f"missing or stale registry stamp — run "
                   f"`python3 src/link_agency_registry.py --stamp`")

    both = set(mapping) & set(unmapped)
    if both:
        bad.append(f"{len(both)} name(s) both mapped and unmapped: {sorted(both)[:5]}")

    missing = sorted(set(names) - set(mapping) - set(unmapped))
    if missing:
        # An agency nobody has classified is the state this file exists to make impossible.
        bad.append(f"{len(missing)} audited_agency name(s) in reports/ are in neither "
                   f"mapping nor unmapped: {missing[:5]}")

    stale = sorted((set(mapping) | set(unmapped)) - set(names))
    if stale:
        bad.append(f"{len(stale)} crosswalk name(s) match no document: {stale[:5]}")

    for k, v in mapping.items():
        if not isinstance(v, dict) or not v.get("slug"):
            bad.append(f"{k}: mapping entry has no slug")
            continue
        if v.get("basis") not in BASES:
            bad.append(f"{k}: basis={v.get('basis')!r} (must be one of {sorted(BASES)})")
        # Anything not a plain exact-name match asserts an identity the names do not
        # state, so it has to say why in prose. This is the rule that stops a fuzzy
        # suggestion being quietly promoted into a fact.
        if v.get("basis") in {"alias", "successor", "manual"} and not v.get("note"):
            bad.append(f"{k}: basis={v['basis']} requires a note explaining the identity")

    for k, v in unmapped.items():
        reason = v.get("reason") if isinstance(v, dict) else None
        if not reason:
            # "we looked and there is no counterpart" and "nobody has looked yet" must
            # not be the same state.
            bad.append(f"{k}: unmapped entries require a reason")
    return bad


def verify_registry(cw: dict, slugs: set[str]) -> list[str]:
    return [f"{k}: slug {v['slug']!r} is not in the ERF registry"
            for k, v in (cw.get("mapping") or {}).items()
            if isinstance(v, dict) and v.get("slug") and v["slug"] not in slugs]


def stamp(mapping: dict) -> tuple[int, int]:
    """Insert or correct the two registry lines in each mapped document. Returns
    (documents examined, documents changed). Touches nothing else in the file."""
    examined = changed = 0
    for p in sorted(REPORTS.glob("*.md")):
        text = p.read_text(encoding="utf-8")
        parts = text.split("---", 2)
        if len(parts) < 3:
            continue
        fm = yaml.safe_load(parts[1]) or {}
        entry = mapping.get(fm.get("audited_agency") or "")
        if not entry:
            continue
        examined += 1
        head = STAMP_RE.sub("", parts[1])  # drop any existing stamp, then re-insert
        want = (f"agency_registry_slug: {entry['slug']}\n"
                f"agency_registry_corpus: {REGISTRY_CORPUS}\n")
        # After the audited_agency line, so the link sits beside the name it interprets.
        anchor = re.compile(r"^(audited_agency: .*\n)", re.M)
        if not anchor.search(head):
            print(f"SKIP {p.name}: no audited_agency line to anchor on", file=sys.stderr)
            continue
        new_head = anchor.sub(lambda m: m.group(1) + want, head, count=1)
        new_text = f"---{new_head}---{parts[2]}"
        if new_text != text:
            p.write_text(new_text, encoding="utf-8")
            changed += 1
    return examined, changed


def unresolved_report(cw: dict, names: dict[str, int], slugs: set[str] | None) -> str:
    """A work list bucketed by the response each case needs, not a flat list of failures.
    Fuzzy suggestions appear here and ONLY here: this file is read by a person, and
    `--check` never consults them."""
    mapping = cw.get("mapping") or {}
    unmapped = cw.get("unmapped") or {}
    review = {k: v for k, v in mapping.items() if isinstance(v, dict) and v.get("review")}
    # Confirmed assertions stay listed rather than disappearing once signed off — a
    # curated mapping is the corpus asserting an identity its documents do not state.
    signed = {k: v for k, v in mapping.items() if isinstance(v, dict) and v.get("reviewed_by")}
    todo = sorted(set(names) - set(mapping) - set(unmapped))

    out = ["# Unresolved agencies", "",
           "Generated by `src/link_agency_registry.py --unresolved-report`. Do not hand-edit.",
           "", f"- mapped: {len(mapping)}", f"- unmapped (recorded, with reason): {len(unmapped)}",
           f"- awaiting human confirmation: {len(review)}",
           f"- confirmed by a reviewer: {len(signed)}",
           f"- unclassified: {len(todo)}", ""]

    if signed:
        out += ["## Confirmed curated mappings", "",
                "Identities the names do not state outright, asserted by this corpus and "
                "accepted by a reviewer. Listed so the claim stays visible and attributable.",
                "", "| audited_agency | slug | basis | confirmed by | on |", "|---|---|---|---|---|"]
        for k, v in sorted(signed.items()):
            out.append(f"| {k} | `{v['slug']}` | {v.get('basis')} | {v['reviewed_by']} | "
                       f"{v['reviewed_on']} |")
        out.append("")

    if review:
        out += ["## Awaiting confirmation", "",
                "Mapped on an asserted identity rather than a name match. Confirm against "
                "the ERF registry, then drop `review: required`.", "",
                "| audited_agency | reports | slug | basis | why |", "|---|---:|---|---|---|"]
        for k, v in sorted(review.items()):
            out.append(f"| {k} | {names.get(k, 0)} | `{v['slug']}` | {v.get('basis')} | "
                       f"{(v.get('note') or '').replace('|', '\\|')} |")
        out.append("")

    if todo:
        out += ["## Unclassified", "",
                "Neither mapped nor recorded as absent. Suggestions are FOR A HUMAN and "
                "are never applied by any check.", "",
                "| audited_agency | reports | suggestion |", "|---|---:|---|"]
        for k in todo:
            s = (difflib.get_close_matches(k.lower().replace(",", ""), sorted(slugs),
                                           n=1, cutoff=0.5)[:1] if slugs else [])
            out.append(f"| {k} | {names.get(k, 0)} | {'`' + s[0] + '`' if s else '_none_'} |")
        out.append("")

    if unmapped:
        out += ["## Recorded as having no ERF counterpart", "",
                "These are a decision, not a gap. ERF's registry is keyed on OAR chapter "
                "assignment, so a body issuing no administrative rules is absent by "
                "construction.", "", "| audited_agency | reports | reason |", "|---|---:|---|"]
        for k, v in sorted(unmapped.items()):
            r = (v.get("reason") if isinstance(v, dict) else "") or ""
            out.append(f"| {k} | {names.get(k, 0)} | {r.replace('|', '\\|')} |")
        out.append("")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--verify-registry", action="store_true")
    ap.add_argument("--stamp", action="store_true")
    ap.add_argument("--unresolved-report", action="store_true")
    ap.add_argument("--registry", help="path to ERF's _meta/catalog/agencies.yml")
    args = ap.parse_args()

    cw, names = load_crosswalk(), corpus_names()
    mapping, unmapped = cw.get("mapping") or {}, cw.get("unmapped") or {}

    if args.check:
        problems = check(cw, names)
        for p in problems:
            print(f"FAIL  {p}", file=sys.stderr)
        covered = len(set(names) & (set(mapping) | set(unmapped)))
        print(f"{len(names)} audited_agency name(s); {len(mapping)} mapped, {len(unmapped)} "
              f"recorded as absent, {covered}/{len(names)} accounted for.")
        return 1 if problems else 0

    if args.verify_registry:
        reg = find_registry(args.registry)
        if reg is None:
            # NOT a pass. A missing sibling means the check did not run, and exiting 0
            # would report "verified" for something nobody verified.
            print("SKIPPED: no ERF agency registry found. Checked:\n  " +
                  "\n  ".join(str(p) for p in REGISTRY_CANDIDATES) +
                  "\nClone executive-regulatory-frameworks beside this repo or pass "
                  "--registry. This is NOT a pass.", file=sys.stderr)
            return 2
        slugs = registry_slugs(reg)
        problems = verify_registry(cw, slugs)
        for p in problems:
            print(f"FAIL  {p}", file=sys.stderr)
        print(f"{len(mapping)} mapped slug(s) checked against {len(slugs)} organizations "
              f"in {reg}.")
        return 1 if problems else 0

    if args.stamp:
        examined, changed = stamp(mapping)
        print(f"{examined} document(s) with a mapped agency; {changed} (re)stamped.")
        return 0

    if args.unresolved_report:
        reg = find_registry(args.registry)
        slugs = registry_slugs(reg) if reg else None
        REPORT_OUT.write_text(unresolved_report(cw, names, slugs), encoding="utf-8")
        print(f"wrote {REPORT_OUT.relative_to(ROOT)}"
              f"{'' if slugs else ' (no registry found — suggestions omitted)'}")
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
