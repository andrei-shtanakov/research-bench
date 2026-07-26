# Stage B closure matrix — friction log → shipped closures

**Date:** 2026-07-26
**Inputs:** `docs/stage-a-friction-log.md` (13 items); design SSOT
`2026-07-25-stage-b-provider-design.md` v1.1 (cowork workspace); Maestro PRs
#105/#106/#108/#109 (all merged); research-bench PRs #7/#8/#9 (merged) +
delivery PRs #10 (merged), #11.
**Golden runs:** 1 ✅ (PR #10) · 2 ⛔ blocked (no docker runtime on the
operator host) · 3 ✅ (PR #11) · 4 ✅ (NEEDS_REVIEW terminal, ledger-only).
Forensics: `_cowork_output/golden-runs/run{1,3,4}/` (dev workspace).

## The 13 frictions

| # | Requirement (from Stage A) | Design decision | Owner | CI evidence | Golden evidence | Status / residual |
|---|---|---|---|---|---|---|
| 1 | Structured verdict channel; ERROR ≠ FAIL in orchestration; ERROR → re-verify, not re-author | §4 FSM + §5 handshake (verdict file authoritative, exit backstop) | Maestro | `test_domain_verdict` (handshake table incl. exit/verdict mismatch), `test_orchestrator_verifying` (ERROR loop, reverify resume) | Run 3: 2×link-resolve ERROR → FAILED+`verification_reverify` → infra fixed → attempt 3 PASS; `rework_attempt=0` throughout; artifact sha identical attempt 1 vs 3 | **CLOSED** |
| 2 | Per-role write authority; author must not write verdicts | §6 WorkspacePolicy + evidence ledger; author scope = `reports/**` only | Maestro (enforcement) + project.yaml | `test_preflight_domain` (role coherence, overlap), ledger-inaccessible-to-author test | Run 1: evidence commit `e3fbf6d` authored by orchestrator, diff ⊆ `verifier.write`; Run 4: FAIL verdict retained in ledger only, worktree/PR untouched | **CLOSED** |
| 3 | Workstream-final verification point | §4 VERIFYING state | Maestro | FSM tests; e2e `test_orchestrator_verifying` | Run 1: 21-task author plan, verified once at the end; single-task guard deleted (rb PR #7) | **CLOSED** |
| 4 | Domain declares applicable verification stages | §9 profile + spec-runner flags (`run_review: false`, per-task test_command retired) | project.yaml | preflight domain checks | Run 1: no review-stage escape; scope gate remains the enforcement layer | **CLOSED** (config-level; reviewer wrong-domain behavior documented) |
| 5 | Spec-gen budget as profile parameter; failures surfaced | §9 `domain.spec_gen` wired via `resolve_spec_gen_settings` (SSOT, preflight conflict check) | Maestro / spec-runner | `test_decomposer` (budget argv), preflight SSOT tests | Run 1: DECOMPOSING 8 min within budget 1.0 | **CLOSED** (budget); *residual:* silent-retry surfacing inside spec-runner — owner **spec-runner**, small QoL PR |
| 6 | Robust critic output contract | §5 file handshake + native structured output (`--json-schema`, live-verified) with fence backstop | research-bench | `test_critic_v2` (both parse paths, no live CLI in suite) | Runs 1/3/4: all critic verdicts parsed cleanly first try | **CLOSED** |
| 7 | Criteria-visibility policy (verifier-only rubric) | §7 location-based `verifier_only` + docker capability gate; deterministic addendum (severity+author_feedback only) | Maestro + operator | capability-gate preflight test; addendum exclusion tests (criterion_id/evidence/hashes never pass) | **PENDING RUN 2** (host has no docker runtime) | **MECHANISM SHIPPED, LIVE PROOF PENDING** |
| 8 | Run-level correlation of verdicts | §5 run-keyed layout v2, run_id minted once per run | Maestro + research-bench | contract tests (v1 rejected by v2 schema) | Run 3: one `run_id` across ERROR/ERROR/PASS; chain readable from the tree; evidence commit carries all attempts | **CLOSED** |
| 9 | Explicit local-merge/remote-PR semantics | §8 `local_merge: before_remote_pr` declare-and-validate | Maestro | preflight Literal-lock | Runs 1/3 delivered through the declared path | **CLOSED as declared**; *new observation:* if base moves mid-run, local and GitHub merge commits diverge (identical trees) — ff-reconcile fails; needs a documented reconcile rule (trees-identical → reset) or "don't move base mid-run" ops rule. Stage C item |
| 10 | Preflight must not warn on future-output globs | §6 phased `expected_outputs` exempt from scope-no-match | Maestro | exemption tests (incl. glob-vs-glob non-exemption per Copilot) | `maestro validate` = 0 warnings on all three run configs | **CLOSED** |
| 11 | Plugin timeout risk | Guard retired with its cause (§4) | research-bench | — | rb PR #7 deleted the plugin | **CLOSED by removal** |
| 12 | Link-resolution budgets | Maestro-level: verifier `timeout_seconds` via execution layer | research-bench (residual) | timeout test in `test_command_verifier` | Run 3: per-request 10 s cost visible; no aggregate cap inside bench-verify | **PARTIAL** — streaming GET + per-stage budget remain **research-bench** residual (tracked) |
| 13 | Output hygiene, undeclared writes | §6 expected_outputs + verifier-namespace protocol checks + worktree-clean gates | Maestro | dirty-worktree protocol-error tests | Run 1: PR #10 = exactly report + bundle, nothing stray | **CLOSED** |

## New frictions discovered during the Stage B operational phase

| Item | Found by | Resolution |
|---|---|---|
| H-6 ex-post approval resume bypassed VERIFYING under a domain profile (delivery without verification) | Run 3 (false gate block parked a domain workstream with `vatt=0`) | **FIXED** Maestro #109 (domain-aware resume → VERIFYING; atomic marker/pid clearing); regression-proven live in run 3 |
| Verifier subprocess could not authenticate the pinned `claude` CLI (`inherit_env=False` starved HOME/USER) | Pre-run-1 smoke (predicted by final branch review) | **FIXED** Maestro #108 (HOME/USER passthrough); bisection evidence in the PR |
| Invocation carried no `workstream_id`; `rework_attempt` was not handshake-checked (provenance could silently lie) | Building bench-verify v2 (first real verifier) | **FIXED** Maestro #106 (two more echo env vars + handshake check) |
| Running orchestrator never re-queues an in-run FAILED workstream (retry rule = startup reconcile only) | Run 3 (30 min parked in FAILED with mirror already up) | **OPEN** — restart or operator re-queue required today; Stage C: in-loop retry tick |
| Moving the local base branch mid-run gives the scope gate multiple merge bases → false escape (7 phantom paths) | Run 3 (operator-induced) | **OPS RULE** (never mutate base during a live run) + Stage C candidate: pin the diff base at branch creation |

## Paper checks (design §10, promotion criteria from decision №3)

Promotion of a policy section to a Protocol requires ALL four: (1) behavior
not expressible in the declarative schema; (2) not executable by Maestro's
single enforcement mechanism; (3) replaceable strategy with its own
lifecycle/IO boundary; (4) confirmed by a real run — paper never suffices.

### Ops domain (side-effects, approval/dry-run, no branch rollback)

- **Verification:** fits as-is — post-change checks are a command → verdict
  shape; `CommandVerifier` + workstream-final point transfer unchanged.
- **Workspace:** ops artifacts (manifests, runbooks) are repo files; the
  declarative role model suffices. No promotion signal.
- **Delivery:** the hot spot. An apply → watch → rollback-on-fail sequence
  with a human approval gate is an *executable workflow*: criteria 1–3 are
  met on paper (not expressible as flags; needs a runner; kubectl/terraform/
  API are replaceable strategies). Criterion 4 is deliberately unmet —
  **DeliveryProvider promotion is plausible but gated on a real ops pilot**.
  A bare `require_approval: true` stays a policy flag and must not trigger
  promotion (per decision №3's explicit example).

### Data domain (large artifacts outside git, deterministic quality gates)

- **Verification:** deterministic quality gates are the easy case; fits.
- **Workspace:** the hot spot. An external artifact store means staging/
  materialization/handle behavior the path-glob model cannot express
  (criterion 1), the git-diff scope gate cannot govern (criterion 2), and
  s3/lakeFS/local stores are replaceable strategies (criterion 3).
  **WorkspaceProvider promotion is plausible but gated on a real data
  pilot** (criterion 4). A new URI/path *type* alone would not qualify.
- **Delivery:** dataset publication via pointer-files-in-git may remain
  within the declarative policy; undecidable on paper — defer.

**Bottom line:** both paper checks land exactly where decision №3 predicted —
each future domain nominates ONE section for promotion, and in both cases
the fourth criterion correctly blocks paper-only architecture. No interface
changes are warranted before an ops or data pilot runs.

## Verdict

Stage B's premise holds operationally: 11 of 13 frictions are closed with
machine-checkable evidence, one is mechanism-complete pending the docker-gated
golden run 2, one is a tracked residual split between spec-runner and
research-bench. The operational phase itself surfaced five new items, three of
which were found *and fixed and live-regression-proven* within the phase — the
verification loop is doing its job on its own infrastructure. Input for the
Stage C decision: ops pilot (DeliveryProvider candidate) vs data pilot
(WorkspaceProvider candidate), plus the small open items above.
