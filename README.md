# research-bench

Stage A pilot: research-domain vertical slice over unmodified Maestro/spec-runner.
Design: workspace `_cowork_output/plans/2026-07-24-research-bench-stage-a-design.md` (dev-only).

- `bench-verify` — verification gate: deterministic checks → link-resolve → LLM critic.
  Exit contract: 0=PASS, 1=FAIL, 2=ERROR (fail-closed; ERROR != FAIL != PASS).
- Verdicts are append-only: `verdicts/<topic>/<artifact_sha256>/attempt-NNN.{json,md,raw.txt}`.
