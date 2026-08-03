# Oregon Audits — Secretary of State Audits Division

> ## ⚠️ NON-AUTHORITATIVE — AI-friendly reference only
> Curated copies/summaries, not official text. Always verify at the
> authoritative source linked in each document. See [DISCLAIMER.md](DISCLAIMER.md).

Part of the OregonAI civic corpus platform
([reference architecture](https://github.com/OregonAI/corpus-toolkit)).
Archetype: **document**. MCP interface: contract v1.

| Entry point | For |
|---|---|
| [llms.txt](llms.txt) | Machine-readable index — AI agents start here |
| [AGENTS.md](AGENTS.md) | Agent rules and anti-fabrication requirements |
| [STATUS.md](STATUS.md) | Generated health: freshness, coverage, drift |
| `_meta/corpus.yml` | Corpus configuration |

## Status: populated — **242 audit reports, 2020–present**

Every numbered report (Report No. `YYYY-NN`) on the Audits Division's own "State Audits
and Reviews 2020 to present" list, with numbering gaps recorded — not skipped — in
`_meta/source-manifest.yml`. For live counts, freshness, and drift, consult the
generated [STATUS.md](STATUS.md) rather than this paragraph; that file is rebuilt from
the corpus, this sentence is prose.

## What this is

Performance, financial, IT and hotline audits published by the **Oregon Secretary of State
Audits Division** — the constitutional auditor of Oregon state government — with their
findings, recommendations, and the audited agency's response.

This is the only corpus on the platform that reports on whether the rest of it worked. A
bill authorizes, a statute directs, a rule implements, a policy operationalizes, dollars
are spent; an audit says whether that produced the intended result. Its value is therefore
mostly in its outbound links — to the ORS and OAR provisions an agency was found to violate
or comply with, to the appropriations whose spending was examined, and to the measures that
mandated the audit.

### Scope

- **In:** state audits and reviews, report date **2019-01-01 onward** — matching
  `oregon-budget`'s FY2019–FY2025 window so the two join.
- **Out:** municipal and local-government filings. Different publisher relationship, and
  they would dwarf the state-audit set. County and city audits remain possible later;
  `jurisdiction` is a real field, not a hardcoded constant.

### The one thing to know before quoting anything from here

An audit finding is a **finding** — one auditor's conclusion, about one agency, during one
audited period, on the evidence available then. It is not a fact about the world.

Every document carries `audited_period_start`/`_end`, and **that is not the report date**: a
report published in 2021 routinely examines fiscal 2019. Where an agency disputed a
finding, its response is present as its own section, because silence would read as
agreement. See [AGENTS.md](AGENTS.md).

## License
Content (curated government material): CC0-1.0. Tooling, structure,
metadata: MIT. See [LICENSE](LICENSE).
