# Contributing

All changes via PR with CODEOWNER review. Before merge, the PR checklist
requires: pinned source URL reachable; retrieval date + hash recorded;
version/effective dates transcribed exactly as the source prints them;
`## Full text` verified verbatim (CI-diffed); relationships resolve;
disclaimer present; CHANGELOG updated. Reviewers set `last_verified` /
`verified_by` at approval. Agent-assisted commits carry
`Claude-Session:` (the session URL) and `Co-authored-by:` trailers —
measured across this repo's history (`git log --all --format='%B' |
grep -c 'Claude-Session:'`), never `Assisted-by:`, which this line used
to name and no commit has ever carried.
