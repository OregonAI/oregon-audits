# Changelog — Oregon Audits — Secretary of State Audits Division

Keep a Changelog format; ISO dates. Change types: Added, Source-Updated,
Superseded, Repealed, Removed, Verified, Fixed, Security.
Repo-curation dates only — official effective dates live in frontmatter.

## [Unreleased]

### Fixed
- 2026-08-02 — Self-description caught up with reality: the README still opened
  with "bootstrapped, no documents yet … the corpus is empty" while the corpus
  serves 242 audit reports (2020–present). Rewritten to state the real coverage
  and defer live numbers to the generated STATUS.md. `llms.txt` `## Contents`
  was still the template's empty stub — an advertised agent entry point serving
  an empty index (corpus-template#16); filled with annotated entries for
  `reports/`, the source manifest, the agency crosswalk, and the authority
  graph.
