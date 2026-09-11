# Changelog — Oregon Audits — Secretary of State Audits Division

Keep a Changelog format; ISO dates. Change types: Added, Source-Updated,
Superseded, Repealed, Removed, Verified, Fixed, Security.
Repo-curation dates only — official effective dates live in frontmatter.

## [Unreleased]

### Fixed
- 2026-09-10 — `link_agency_registry.py --stamp` (and `ingest_audits.py`'s equivalent
  for newly ingested reports) wrote `agency_registry_slug`/`agency_registry_corpus`
  onto a document but dropped the crosswalk's `basis` — so a document joined by
  mechanical name match (`exact`) was indistinguishable in frontmatter from one joined
  on a human-asserted `alias` or `successor`, though the crosswalk itself carries and
  requires that distinction. Now stamps `agency_registry_basis` alongside the slug,
  plus `agency_registry_reviewed_by`/`agency_registry_reviewed_on` where the crosswalk
  entry has them (6 of 37 entries are non-`exact`; one of those six carries no reviewer
  and gets no fabricated one). `--check` now fails a document whose stamped basis (or
  review metadata) has drifted from the crosswalk, exactly as it already did for the
  slug. All 223 mapped documents re-stamped; 0 changed on a second run (issue #23).

- 2026-08-02 — Self-description caught up with reality: the README still opened
  with "bootstrapped, no documents yet … the corpus is empty" while the corpus
  serves 242 audit reports (2020–present). Rewritten to state the real coverage
  and defer live numbers to the generated STATUS.md. `llms.txt` `## Contents`
  was still the template's empty stub — an advertised agent entry point serving
  an empty index (corpus-template#16); filled with annotated entries for
  `reports/`, the source manifest, the agency crosswalk, and the authority
  graph.
