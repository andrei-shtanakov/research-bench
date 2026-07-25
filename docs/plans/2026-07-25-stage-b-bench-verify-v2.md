# Stage B: bench-verify v2 (research-bench part) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adapt research-bench to the merged Maestro Stage B contract: bench-verify
emits verdict v2 documents under Maestro-owned addressing, the critic gains a
native structured-output path with per-finding `author_feedback`, the
single-task guard retires, and `project.yaml` moves to the `domain:` profile.

**Architecture:** Maestro (merged PR #105, master `346222e3b`) now owns the
verification lifecycle: it mints `verification_run_id`, assigns the exact
`--out` path, sets echo env vars, and applies the strict file/process
handshake. research-bench's job shrinks to: produce a schema-valid v2 verdict
at the assigned address, exit with the matching contract code, and never touch
anything else. The cross-repo contract is consumed by vendoring a pinned copy
of `maestro/schemas/verdict_v2.json` (obs-contract precedent).

**Design SSOT:** `../_cowork_output/plans/2026-07-25-stage-b-provider-design.md`
(approved v1.1). Maestro-side reference (AUTHORITATIVE for the invocation
contract — read at the pin, do not guess):
`Maestro/maestro/domain/verifier.py` and `Maestro/tests/fakes/stub_verifier.py`
at commit `346222e3b` (read-only reference per polyrepo rules).

**Tech Stack:** Python 3.12+, uv, pydantic v2, pytest + anyio, ruff, pyrefly.

## Global Constraints

- ONLY `uv` (`uv run pytest`, `uv run pyrefly check`, `uv run ruff format .`,
  `uv run ruff check .`). Never pip.
- Repo is PR-only: branch `feat/stage-b-verdict-v2`, no direct master commits;
  Copilot review must be actioned after `gh pr create`.
- **Contract pin:** everything consumed from Maestro is vendored at master
  commit `346222e3b`; the pin is recorded next to the vendored file. Never
  reference `../Maestro/` paths at runtime.
- **v1 history untouched:** existing `verdicts/**` stay as generation-1
  artifacts (design §5: no migration; v1/v2 coexist).
- Exit contract unchanged: `0=PASS, 1=FAIL, 2=ERROR`; verdict written ALWAYS
  (incl. BaseException) — preserve the Stage A fail-closed write path.
- TDD per task; type hints; line 88; ruff + pyrefly clean per task
  (`uv run pyrefly check` — record the completion line).
- Commit messages end with:
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`

## File Structure

```
contracts/maestro-verdict-v2/verdict_v2.json   # Task 1: vendored pinned schema
contracts/maestro-verdict-v2/VENDORED_FROM     # Task 1: repo + commit pin
src/research_bench/cli.py                      # Task 2: v2 invocation mode
src/research_bench/verdict.py                  # Task 3: v2 document emission
src/research_bench/critic.py                   # Task 4: structured output + author_feedback
prompts/critic-v2.md                           # Task 4: prompt v2
bench.config.yaml                              # Task 4: pin bump (prompt v2)
src/research_bench/criteria.py                 # Task 2: load from explicit path
spec/plugins/single-task-guard/                # Task 5: DELETED
project.yaml                                   # Task 6: domain: profile
docs/examples/domain-profile.research.yaml     # Task 6: canonical example
tests/test_verdict_v2_contract.py              # Task 1/3: schema contract tests
tests/test_cli_v2.py                           # Task 2
tests/test_critic_v2.py                        # Task 4
README.md / docs/                              # Task 6: contract notes
```

---

### Task 1: Vendor the verdict v2 schema + contract test harness

**Files:**
- Create: `contracts/maestro-verdict-v2/verdict_v2.json` (byte-for-byte copy of
  `Maestro/maestro/schemas/verdict_v2.json` @ `346222e3b`)
- Create: `contracts/maestro-verdict-v2/VENDORED_FROM` (two lines:
  `repo: github.com/andrei-shtanakov/maestro` /
  `commit: 346222e3b`)
- Create: `tests/test_verdict_v2_contract.py`

**Interfaces:**
- Produces: `load_vendored_schema()` test helper (jsonschema validation via
  `uv add --dev jsonschema` if not present); every later task validates
  emitted documents against THIS file, never against a live Maestro checkout.

- [ ] Step 1: copy the schema from the local Maestro checkout at the pinned
  commit (`git -C ../Maestro show 346222e3b:maestro/schemas/verdict_v2.json`)
  — this is a dev-time vendoring action, allowed; runtime never does this.
- [ ] Step 2: failing test — `test_vendored_schema_is_valid_jsonschema` +
  `test_stage_a_v1_document_does_NOT_validate` (take any committed
  `verdicts/sqlite-wal/**.json` v1 file; it must be rejected — proves the
  schema actually discriminates generations).
- [ ] Step 3: helper + make tests pass. Step 4: ruff/pyrefly. Step 5: commit
  `feat(contract): vendor Maestro verdict v2 schema @346222e3b + contract tests`.

### Task 2: bench-verify v2 invocation mode

**Files:**
- Modify: `src/research_bench/cli.py` (argparse: add `--artifact`,
  `--criteria`, `--out`, `--verification-run-id`, `--attempt`; v2 mode is
  active iff `--out` is given; legacy `--brief` mode stays for out-of-loop
  local runs)
- Modify: `src/research_bench/criteria.py` (load manifest from the explicit
  `--criteria` path — Maestro stages an ephemeral copy; no assumption that it
  lives under `briefs/`)
- Test: `tests/test_cli_v2.py`

**Binding contract (extract EXACT names by reading
`maestro/domain/verifier.py` @ the pin — argv placeholder order, env var
names, and every identity field Maestro echoes/expects; mirror
`tests/fakes/stub_verifier.py` which is Maestro's own reference
implementation of a conforming verifier):**
- argv: `--artifact {artifact} --criteria {criteria} --out {out}
  --verification-run-id {run_id} --attempt {attempt}` (placeholder set is
  closed on the Maestro side).
- env: `MAESTRO_PROFILE_SHA256`, `MAESTRO_VERIFIED_SOURCE_COMMIT`,
  `MAESTRO_VERIFIED_SOURCE_TREE` + whatever else verifier.py provides for
  `workstream_id`/`rework_attempt` (read the code; if any identity field is
  NOT provided by the invocation, replicate exactly what stub_verifier.py
  does — the handshake's EchoExpectations is the ground truth).
- Output: write canonical JSON to EXACTLY `--out` (atomic tmp+rename, NO
  self-allocation — `allocate_attempt` is legacy-mode-only from now on);
  sidecars `.md`/`.raw.txt` next to it (same stem).
- The worktree must remain untouched: v2 mode writes NOTHING outside the
  `--out` directory (Maestro protocol-errors on a dirty worktree).

- [ ] Steps: TDD (flag parsing, v2/legacy mode dispatch, criteria-from-path,
  out-path discipline incl. "no writes outside out-dir" test with a tmp
  worktree), ruff/pyrefly, commit
  `feat(cli): bench-verify v2 invocation mode (Maestro-owned addressing)`.

### Task 3: Verdict v2 document emission

**Files:**
- Modify: `src/research_bench/verdict.py` (v2 model: `schema_version: 2`,
  `identity` block with run/attempt/workstream/artifact/criteria/profile
  fields + `verified_source_commit`/`verified_source_tree` echoed verbatim
  from env; findings gain `author_feedback`)
- Test: extend `tests/test_verdict_v2_contract.py`

Rules (each a test): every emitted document validates against the VENDORED
schema; echo fields are byte-identical to the env inputs; exit code matches
`verdict` (0/1/2); the fail-closed always-write path survives (BaseException
→ ERROR document at `--out` + exit 2 — port the Stage A behavior into v2
mode); v1 emission path untouched for legacy mode.

- [ ] Steps: TDD, ruff/pyrefly, commit
  `feat(verdict): schema_version 2 emission with identity echo (vendored contract)`.

### Task 4: Critic v2 — native structured output + author_feedback

**Files:**
- Modify: `src/research_bench/critic.py`
- Create: `prompts/critic-v2.md`
- Modify: `bench.config.yaml` (`prompt_path: prompts/critic-v2.md`,
  `prompt_version: v2` — pin bump is an explicit reviewed change)
- Test: `tests/test_critic_v2.py`

Content:
- Findings schema extends to `{criterion_id, severity, evidence,
  author_feedback}`; prompt v2 instructs the critic to author
  `author_feedback` as actionable text FOR the author that must not quote
  rubric wording (this is the §7 declassification channel; Maestro's
  addendum passes ONLY severity + author_feedback to the author).
- Native structured output: invoke the pinned `claude` CLI with a JSON-schema
  -enforced output mode (check the CLI's current flags for structured
  output/JSON mode; friction #6 showed prompt-enforced "no fences" is
  fragile). The fence-tolerant parser from PR #4 STAYS as a backstop —
  belt and suspenders, both tested.
- Adversarial regression: the Stage A injection fixture still yields FAIL
  with the injection recorded as a finding (port the existing test to v2).

- [ ] Steps: TDD (structured-output happy path mocked at the subprocess
  boundary; fence-backstop; author_feedback presence; injection regression),
  ruff/pyrefly, commit
  `feat(critic): v2 prompt + native structured output + author_feedback channel`.

### Task 5: Retire the single-task guard

**Files:**
- Delete: `spec/plugins/single-task-guard/` (entire tree)
- Delete: `tests/test_guard.py`, `tests/test_guard_integration.py`
- Modify: `project.yaml` workstream description (drop the "EXACTLY ONE
  executable task" constraint — done in Task 6's rewrite; here just ensure
  nothing else references the plugin: `grep -r single-task-guard .`)

Rationale (commit message material): workstream-final verification exists in
Maestro now (VERIFYING state); the per-task constraint and its plugin (incl.
the 60s-timeout latent risk, friction #11) retire with their cause.

- [ ] Steps: delete, grep for stragglers, full local test run green, commit
  `chore: retire single-task-guard (workstream-final verification shipped in Maestro)`.

### Task 6: project.yaml domain profile + canonical example + docs

**Files:**
- Modify: `project.yaml`
- Create: `docs/examples/domain-profile.research.yaml` (canonical example —
  `visibility: shared` or placeholder operator path; NEVER a real
  verifier-only rubric, per design §9)
- Modify: `README.md` + `docs/` (short "Stage B contract" section: vendored
  schema pin, invocation contract pointer, exit codes, evidence flow)

`project.yaml` changes (validate against Maestro's shipped schema by running
`maestro validate project.yaml` from the Maestro checkout as a dev-time
check):
- Add `domain:` — `verification` (verifier argv per Task 2 contract,
  `artifact: reports/sqlite-wal/result.md`, `rework_budget: 2`,
  `verdict_schema_version: 2`, `error_retry_budget: 2`,
  `criteria: {visibility: shared, source: briefs/sqlite-wal/criteria.yaml,
  sha256: <computed>}`), `workspace` (roles: author.write=`reports/sqlite-wal/**`
  ONLY — verdicts leave the author scope, THIS closes friction #2;
  verifier.write=`verdicts/sqlite-wal/**`; read_only=`briefs/**`;
  `evidence_root: verdicts/sqlite-wal`; phased expected_outputs), `delivery`
  (`local_merge: before_remote_pr`, `remote: github_pr`, `evidence: all`),
  `spec_gen` (budget from current defaults).
- Remove `test_command` + `run_tests_on_done: true` (per-task verification
  retires for this domain); keep `run_review: false`.
- Workstream `scope:` shrinks to `reports/sqlite-wal/**` (author authority
  only) and the description drops the single-task constraint and the
  "verification tooling off-limits" plea (now enforced by role scopes).

- [ ] Steps: write config + example, `maestro validate` dev-check passes,
  docs, full local suite + ruff + pyrefly green, commit
  `feat(config): domain profile (Stage B) — role-scoped authority, guard retired`.
- [ ] Final: push branch, `gh pr create`, action the Copilot review.

---

## Out of scope (operational phase after this PR merges)

Golden runs 1–4 of the design §10 (live orchestrate runs), the ops/data paper
checks, and the friction-closure matrix are run/authored by the operator with
the orchestrator — they consume this PR but are not code tasks in it.

## Self-review notes

- Every Maestro-facing value in Tasks 2–3 is deliberately specified as
  "extract from `verifier.py`/`stub_verifier.py` @ 346222e3b" rather than
  transcribed here — the pin is the SSOT and transcription drift is the
  known failure mode (friction #6's cousin).
- Task ordering: 1→2→3→4 are dependency-ordered; 5 and 6 are independent of
  4 but 6 depends on 2 (argv shape) and 5 (description text).
