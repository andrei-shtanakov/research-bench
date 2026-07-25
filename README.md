# research-bench

Stage A pilot: research-domain vertical slice over unmodified Maestro/spec-runner.
Design: workspace `_cowork_output/plans/2026-07-24-research-bench-stage-a-design.md` (dev-only).

- `bench-verify` — verification gate: deterministic checks → link-resolve → LLM critic.
  Exit contract: 0=PASS, 1=FAIL, 2=ERROR (fail-closed; ERROR != FAIL != PASS).
- Verdicts are append-only: `verdicts/<topic>/<artifact_sha256>/attempt-NNN.{json,md,raw.txt}`.

## Stage B contract

`project.yaml`'s `domain:` block wires this repo into Maestro's Stage B
workstream-final verification (the `VERIFYING` phase). Summary; see
`docs/examples/domain-profile.research.yaml` for an annotated template and
`Maestro/maestro/domain/profile.py` for the schema SSOT.

- **Schema pin:** everything consumed from Maestro (verdict document shape,
  `DomainProfile` field names, the invocation contract) is vendored/pinned at
  `github.com/andrei-shtanakov/maestro` commit `346222e3b` (PR #105 —
  verification FSM + domain contracts; followed by PR #106, which conveys
  `workstream_id`/`rework_attempt` via echo env). `contracts/maestro-verdict-v2/`
  holds the vendored verdict-v2 JSON schema and the pin record.
- **Invocation:** Maestro spawns
  `uv run bench-verify --artifact {artifact} --criteria {criteria} --out {out}
  --verification-run-id {run_id} --attempt {attempt}` — Maestro owns the
  `--out` address; `bench-verify` never self-allocates in this mode.
- **Five echo env vars** (fail-closed identity, no defaults, no guessing):
  `MAESTRO_PROFILE_SHA256`, `MAESTRO_VERIFIED_SOURCE_COMMIT`,
  `MAESTRO_VERIFIED_SOURCE_TREE`, `MAESTRO_WORKSTREAM_ID`,
  `MAESTRO_REWORK_ATTEMPT`. Any missing/blank var short-circuits the whole
  pipeline (no stage runs) and writes an `ERROR` verdict document instead.
- **Exit codes:** unchanged from Stage A — `0=PASS, 1=FAIL, 2=ERROR`; a
  verdict document is written at `--out` on every path, including an
  unhandled exception (fail-closed always-write).
- **Evidence flow:** the verifier's write authority (`roles.verifier.write`)
  and the author's (`roles.author.write`) are disjoint — verdicts live
  entirely outside the author's scope. Maestro's evidence ledger records
  every attempt outside the worktree; on `PASS` exactly one evidence commit
  lands on the workstream branch (tagged `Maestro-Verification-Run: <run_id>`)
  before delivery (`local_merge: before_remote_pr` → `remote: github_pr`).
