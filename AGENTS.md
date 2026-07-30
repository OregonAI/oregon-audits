# AGENTS.md — Oregon Audits — Secretary of State Audits Division

Corpus of the OregonAI civic corpus platform. Archetype: document.
Read `_meta/corpus.yml` for configuration; the platform rules live in
OregonAI/corpus-toolkit `docs/`.

## Purpose
Non-authoritative, AI-friendly mirror of the performance, financial, IT and hotline
audits published by the Oregon Secretary of State Audits Division — the constitutional
auditor of Oregon state government — together with their findings, recommendations, and
the audited agency's response.

Never a source of truth. Every answer must cite and link the authoritative source.

This is the only corpus on the platform that reports on whether the rest of it worked: a
bill authorizes, a statute directs, a rule implements, a policy operationalizes, dollars
are spent — an audit says whether that produced the intended result.

## A FINDING IS NOT A FACT

The single rule that matters most here, and the reason this corpus needs care that a
statute corpus does not.

An audit finding is a **finding** — one auditor's conclusion, about one agency, during one
audited period, on the evidence available then. It is not a fact about the world, and the
distinction is legally meaningful. Three consequences, each enforced rather than trusted:

1. **The audited period is mandatory, not decorative.** Every document carries
   `audited_period_start`, `audited_period_end` and `audited_period_text`. A 2019 finding
   about an agency's controls says nothing about that agency today, and an agent that
   cannot see the period will state it as current. Note that this is NOT the report date:
   a report published in 2021 routinely examines fiscal 2019.
2. **Where the agency disputed a finding, the dispute is part of the record.** Agency
   responses are usually appended to the report PDF rather than published separately.
   They are extracted into their own `## Agency response` section. Dropping one does not
   make the corpus incomplete — it makes it *wrong*, because silence reads as agreement.
3. **Never summarize a finding into a conclusion the report did not state.** `## At a
   glance` carries the objective, the scope, and the report's own headline conclusion.
   Nothing else. If the report hedged, the corpus hedges.

## Scope

**In:** state audits and reviews published by the Audits Division, report date 2019-01-01
onward, matching `oregon-budget`'s FY2019–FY2025 window so the two join.

**Out:** municipal and local-government filings
(`sos.oregon.gov/audits/Pages/muniaudits.aspx`). Different publisher relationship, and
they would dwarf the state-audit set. `jurisdiction` in `_meta/corpus.yml` is kept a real
field rather than a hardcoded constant, so adding county or city audits later is a data
change and not a schema change.

## Two upstream facts that will bite you

1. **Report URLs move.** Reports before 2020 are no longer served at
   `sos.oregon.gov/audits/Documents/<number>.pdf` — `2019-01` and `2019-14` both 404
   today, while `2026-20` resolves fine from the same path. Search engines still index the
   dead URLs, so a link that appears in a search result is not evidence the file is there.
   Pre-2020 reports live in the Oregon Records Management Solution instead.
2. **Report numbers are not dense, and the path casing varies.** A missing `2024-07` may
   be unpublished, withdrawn, or hosted elsewhere — every gap gets a recorded reason in
   `_meta/source-manifest.yml`, never a silent skip. Both `/audits/Documents/` and
   `/audits/documents/` appear upstream.

## Hard rules (anti-fabrication)
1. Never write content that does not exist in the pinned source. Source
   unreachable or unparseable → insert
   `<!-- TODO: human verification required -->` and stop. Never
   reconstruct from model knowledge.
2. `## Full text` sections are verbatim only. Curator content is confined
   to `## At a glance`, `## Curator notes`, `## Cross-references`.
3. Third-party copyrighted material: summary + official link only.
4. Never invent or infer a citation. Unresolvable → say so.
5. Live-data answers (api/hybrid) must carry the executed query and
   timestamp.
6. All changes via PR. Do not set `last_verified`/`verified_by` to a real
   value — the human reviewer does that at approval. The schema REQUIRES both
   keys, so ingestion writes them as empty strings: schema-valid, and read
   downstream as "never verified", which is exactly true. Never write a date or
   a handle you did not earn; a fabricated verification stamp is worse than an
   obviously-empty one.
7. Update this knowledge body's CHANGELOG.md in the same PR as content
   changes.

## Found a bug you are not fixing right now? Open an issue. Period.

This is not optional and has no size threshold.

If you discover a defect and do not fix it in the change you are working on, **open a
GitHub issue before you finish the task**. Not a note in the commit message, not a
paragraph in the PR body, not a line in your summary to the user. Those are not a work
queue — nobody greps closed PRs six months later, and the next agent rediscovers the same
bug from scratch, usually the expensive way.

This applies to every one of these, not just crashes:

- a check that passes without checking anything
- a documented command, flag, or path that does not exist or does not work
- a claim in a README, docstring, or catalog note that is no longer true
- data known to be wrong, stale, or incomplete
- a guard that cannot fire, or fires on the wrong condition
- something you worked around instead of fixing

**File it in the repo that owns the fix, which may not be the repo you are in.** A parser
defect here, a registry gap in a sibling corpus, and a validator gap in `corpus-toolkit`
are three different issues in three different repos. Say plainly in each which repo the
work belongs to.

An issue must answer four things, because an issue that only says "X is broken" costs the
next person the whole investigation again:

1. **What is wrong** — the specific behaviour, not a category
2. **How it was found** — the command, the data, the failing case
3. **What it breaks** — who or what gets a wrong answer, and how silently
4. **What would fix it**, or what still needs measuring before anyone can know

Prefer counts and reproductions over adjectives. "126 appropriations unjoined, of which 59
are an extraction gap and 41 are correct" is actionable; "agency matching needs work" is
not, and will be re-derived by someone else.

If you genuinely cannot open one — no network, no permission — say so explicitly in your
final message to the user and hand them the text to file. Silently dropping it is the one
outcome that is never acceptable.

## Workflow
Discovery → human-approved source manifest → ingestion → human-reviewed
PR. See toolkit `docs/replication-guide.md`.

## Generated files — never hand-edit

| file | generated by | gate |
|---|---|---|
| `_meta/graph.json` | `src/build_graph.py` | `generated` job, every PR |
| `STATUS.md` | `corpus-generate-status` | `generated` job, every PR (plus a weekly repair in the `drift` job) |
| `_meta/source-manifest.yml` | `src/enumerate_audits.py` | `manifest-complete` job, **weekly, not per-PR** |

`source-manifest.yml` is checked weekly rather than on every PR, and that is deliberate. The
other two derive from **repo content** — deterministic, offline, and a PR is exactly what
invalidates them. The manifest derives from **upstream**: the Audits Division publishes on its
own schedule, so it goes stale for reasons no PR caused and no PR can fix. Gating merges on it
would fail unrelated PRs whenever an audit was published, and put a network call on the critical
path of every merge. Both train an operator to ignore a red check.

Regenerate at the source and commit the result.

`_meta/corpus-index.json` is generated too but is **not committed**: `publish-index.yml`
builds it at deploy time. A committed copy can silently fall behind its own corpus, and
the damage lands in a SIBLING repo whose citation resolution reads it. Publish it; do
not commit it.

**Every generated file you commit needs a step in the `generated` job.** One without a
step is exactly the failure that job exists to prevent, and it is silent by construction
— the toolkit only READS these artifacts, so nothing anywhere notices when one goes
stale. A corpus that ships `joins:` owes itself the same treatment: the toolkit resolves
each `joins[].document_id`, but only this corpus can check that a `{dataset, key}` pair
selects any rows at all.
