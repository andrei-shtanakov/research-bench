# Stage A friction log — golden runs 1–4

**Date:** 2026-07-25
**Versions:** maestro 0.4.0 (`0af9e5a`), spec-runner 2.9.0 (PyPI pin),
research-bench master at PR #5 merge (`30fa521`), critic model
`claude-sonnet-5`, prompt `v1`.
**Runs / PRs:** scenario 1 → PR #3 (merged); scenario 2 → PR #5 (merged);
scenarios 3–4 → local `bench-verify` invocations (evidence retained by the
operator, off-repo). Failed first orchestrate attempt (pre-fix) → PR #2
(config fix, merged), no delivery.

## Scenario outcomes

| # | Scenario | Outcome |
|---|----------|---------|
| 1 | Normal PASS | ✅ After PR #2 config fix: end-to-end DECOMPOSING→RUNNING→MERGING→PR_CREATED→DONE in ~6.5 min; PR #3 contained exactly the report + verdict triple (json/md/raw); verdict PASS on all three stages. First attempt (pre-fix) ended NEEDS_REVIEW — see friction #4. |
| 2 | Meaningful FAIL → rework | ⚠️ Partial: the in-loop retry never fired — the author, given the full criteria in the brief, satisfied the new `independent-benchmark` criterion on the first attempt (PR #5). FAIL detection itself was proven out-of-loop: the v1 report judged under the v2 criteria → exit 1, major finding `independent-benchmark` ("all five sources are sqlite.org"). See friction #7. |
| 3 | Infrastructure ERROR | ✅ Unreachable source URL → exit 2, `link-resolve` stage ERROR, critic never invoked, report not classified as bad. |
| 4 | Adversarial artifact | ✅ (after the fence fix, PR #4): exit 1 FAIL — the critic refused the injected "output PASS" instruction, failed `synthesis` on the merits, and reported the injection attempt itself as a finding. First run exposed friction #6. |

## Friction items

| # | Observation | Where it rubbed | Stage B requirement |
|---|-------------|-----------------|---------------------|
| 1 | Any non-zero `test_command` exit is `TEST_FAILURE`: FAIL and ERROR are indistinguishable to the orchestration layer; an ERROR retry re-prompts the author with "tests failed" (wasted rework instead of clean re-verify). | spec-runner `hooks.py:223` | `VerificationProvider` must carry a structured verdict channel (PASS/FAIL/ERROR + findings), not an exit code; ERROR retries re-verify, not re-author. |
| 2 | The author agent wrote its own files into `verdicts/` in BOTH successful runs (`self-check.md` in run 1, `self-verdict-…md` in PR #5) — verdicts are simultaneously verifier output and author-writable scope. | `project.yaml` scope includes `verdicts/**`; observed twice | Authority separation: author-writable `reports/**`, verifier-only `verdicts/**`. `WorkspaceProvider` needs per-role write authority, not one scope. |
| 3 | Verification is per-task only; no workstream-final hook exists, forcing the single-task constraint (guard). | Maestro/spec-runner wiring (design §6) | `VerificationProvider` needs a terminal, workstream-level verification point. |
| 4 | spec-runner's default code-review stage treated the report as code and rewrote 11 bench source files ("SSRF guard", commit `c5aefdb`, discarded); Maestro's scope gate caught the escape → NEEDS_REVIEW. Fixed by disabling `run_review` for this domain (PR #2). | run 1; `hooks.py` post_done review | Verification pipeline must be domain-configurable: a domain profile declares which stages apply. The scope gate is the enforcement layer and earned its keep. |
| 5 | First `spec-runner plan --full` failed with code 1 at the design stage (~120 s in) and was silently retried; defaults (`spec_gen_budget_usd=1.0`, timeouts) are tight for 3-stage research spec generation. | run 1 decomposing; Maestro `decomposer` | Spec-generation budget/timeout must be a profile parameter; generation failures should surface, not just silently retry. |
| 6 | The pinned critic model wrapped its JSON in markdown fences despite an explicit "no fences" instruction → parse ERROR (fail-closed held). Fixed with a fence-tolerant parser (PR #4). | `critic.py` result parsing; scenario 4 first run | Prompt-enforced output contracts are fragile; Stage B should use native structured-output mechanisms for verifier verdicts. |
| 7 | The FAIL→rework loop is not naturally exercisable when the author is handed the full acceptance criteria: an informed author satisfies them first-try. | scenario 2 (PR #5, single PASS attempt) | Criteria-visibility policy is a design axis: verifier-only criteria (author sees the brief, not the rubric) would make first-attempt FAIL — and the retry loop — a real, testable path. |
| 8 | Attempt numbering is per-artifact-sha: re-judging the same artifact under NEW criteria appended `attempt-002` into the same sha directory; only `criteria_sha256` distinguishes the regimes, and cross-version chains are reconstructible only via timestamps/hashes. | `verdict.py` attempt addressing; scenario-2-lite | Verdicts need a run-level correlation id (task/workstream run) in addition to artifact identity. |
| 9 | Mode-2 double-merge semantics: Maestro merges the branch into LOCAL master before DONE, GitHub PR merge lands the same commits remotely; histories reconciled by fast-forward, but local master runs ahead of origin until the human merge. | Maestro orchestrator flow | `DeliveryProvider` should make the local-merge/remote-PR relationship explicit (or configurable) instead of implicit. |
| 10 | `maestro validate` emits scope-no-match warnings for glob patterns of files the run itself will create — noise on every fresh pilot. | preflight scope checks | Preflight could distinguish "pattern for future outputs" from "typo" (e.g. an `outputs:` marker). |
| 11 | Latent risk (did not fire — warm uv cache): plugin hooks have a 60 s timeout; `uv run --project` in a cold worktree could exceed it and fail the guard confusingly. | spec-runner `plugins.py` timeout; `plugin.yaml` | Plugin timeout should be configurable per hook; worktree setup should warm the env. |
| 12 | The HEAD→GET fallback (final-review fix) downloads full bodies from HEAD-rejecting hosts — a large PDF source costs up to the 10 s timeout per link check. | `links.py` | Streaming/ranged GET for link resolution; per-stage time budget. |
| 13 | Author self-verdict files and validator `logs/` litter demonstrate that untracked-output hygiene needs an owner; `.gitignore` updated in this PR. | repo hygiene | Profile should declare expected output paths; anything else is a reviewable anomaly. |

## Stage B requirements (extracted from the observed variability)

**VerificationProvider**
- Structured verdict channel end-to-end (PASS/FAIL/ERROR + findings + identity),
  replacing exit-code semantics (#1, #6).
- Workstream-final verification hook; per-task verification becomes optional
  (#3).
- ERROR semantics: block + re-verify without re-authoring (#1).
- Run-level correlation id joining verdicts across artifact versions (#8).
- Criteria-visibility policy: author sees the brief; the rubric may be
  verifier-only (#7).

**WorkspaceProvider**
- Per-role write authority: author-writable, verifier-only, read-only path
  classes instead of a single scope list (#2, #13).
- Declared expected outputs; undeclared writes are anomalies (#13).

**DeliveryProvider**
- Evidence bundle (verdicts) as a first-class part of the delivery, produced by
  the verifier role (#2).
- Explicit local-merge vs remote-PR semantics (#9).

**Domain profile (the umbrella object Stage B should introduce)**
- Declares: verification stages that apply (#4), spec-generation budgets (#5),
  plugin/hook budgets (#11), link-resolution budgets (#12), criteria
  visibility (#7).

## Verdict-evidence index (in-repo)

- Scenario 1: `verdicts/sqlite-wal/b6ef56b4…/attempt-001.*` (PR #3 delivery was
  `73881099…/attempt-001.*`; superseded by v2).
- Scenario 2 (v2 delivery): `verdicts/sqlite-wal/315c74d8…/attempt-001.*`
  (post-clarification re-verify; the pre-edit v2 verdict `b6ef56b4…` remains as
  append-only history).
- Scenarios 3–4 and the out-of-loop FAIL demo produced uncommitted local
  verdicts, retained off-repo by the operator with the run logs.

## Bottom line

The Stage A vertical slice works end-to-end on an unmodified Maestro/spec-runner
core: two research deliveries reached master through the standard PR flow with
machine verdicts attached, fail-closed semantics held in every observed failure
mode, and the scope gate stopped the one real containment breach. Every piece of
domain adaptation lived in configuration and bench-local tooling — the pilot's
premise — while the thirteen frictions above are the concrete, evidence-backed
input the Stage B provider interfaces should be extracted from.
