"""Tests for bench-verify v2 invocation mode (Maestro-owned addressing).

Covers: flag parsing / mode dispatch, criteria loaded from an arbitrary
--criteria path, out-path discipline (writes confined to --out's parent,
worktree left untouched), and that allocate_attempt (legacy self-numbering)
is never called in v2 mode.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import jsonschema
import pytest

from research_bench.cli import ECHO_ENV_VARS, main, run_verify_v2
from research_bench.verdict import Finding, Stage, StageResult, VerdictKind

VENDORED_SCHEMA_PATH = (
    Path(__file__).parent.parent
    / "contracts"
    / "maestro-verdict-v2"
    / "verdict_v2.json"
)

CRITERIA = """\
schema_version: 1
artifact: reports/topic-x/result.md
criteria:
  - id: synthesis
    description: Conclusions distinguish evidence from inference
"""

CONFIG = """\
critic:
  claude_command: claude
  model: claude-sonnet-5
  prompt_path: prompts/critic-v1.md
  prompt_version: v1
  cost_cap_usd: 1.0
  timeout_seconds: 300
  critic_version: "0.1.0"
"""

GOOD_REPORT = "Claim [S1].\n\n## Sources\n- [S1] https://a.example/x\n"


@pytest.fixture(autouse=True)
def _default_identity_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Valid Maestro echo-env by default; individual tests delete/override.

    The five-var contract (profile/commit/tree/workstream/rework_attempt)
    is fail-closed: any test exercising the normal pipeline needs all five
    present, so this autouse fixture supplies safe defaults and the
    identity-error tests explicitly `delenv`/override the one they probe.
    """
    monkeypatch.setenv("MAESTRO_PROFILE_SHA256", "default-profile-sha")
    monkeypatch.setenv("MAESTRO_VERIFIED_SOURCE_COMMIT", "default-commit-sha")
    monkeypatch.setenv("MAESTRO_VERIFIED_SOURCE_TREE", "default-tree-sha")
    monkeypatch.setenv("MAESTRO_WORKSTREAM_ID", "default-ws")
    monkeypatch.setenv("MAESTRO_REWORK_ATTEMPT", "0")


def _validate_v2(document: dict[str, object]) -> None:
    schema = json.loads(VENDORED_SCHEMA_PATH.read_text())
    jsonschema.Draft202012Validator(schema).validate(document)


def _stage(stage: Stage, verdict: VerdictKind) -> StageResult:
    return StageResult(stage=stage, verdict=verdict)


def _project(tmp_path: Path, *, criteria_name: str = "staged.criteria") -> Path:
    """Build a v2-shaped worktree: no briefs/ dir; criteria lives wherever
    Maestro happens to stage it (here, an extensionless ephemeral copy)."""
    (tmp_path / "bench.config.yaml").write_text(CONFIG)
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts/critic-v1.md").write_text("{criteria_block}\n{artifact}")
    (tmp_path / "reports/topic-x").mkdir(parents=True)
    (tmp_path / "reports/topic-x/result.md").write_text(GOOD_REPORT)
    (tmp_path / "staging").mkdir()
    (tmp_path / "staging" / criteria_name).write_text(CRITERIA)
    return tmp_path


def _run_v2(root: Path, out_path: Path, **overrides: object) -> int:
    kwargs: dict[str, object] = {
        "root": root,
        "config_path": root / "bench.config.yaml",
        "artifact_rel": "reports/topic-x/result.md",
        "criteria_path": root / "staging" / "staged.criteria",
        "out_path": out_path,
        "verification_run_id": "run-123",
        "attempt": 1,
    }
    kwargs.update(overrides)
    with (
        patch(
            "research_bench.cli.run_link_resolve",
            return_value=_stage("link-resolve", VerdictKind.PASS),
        ),
        patch(
            "research_bench.cli.run_critic",
            return_value=(_stage("critic", VerdictKind.PASS), "raw-critic-output"),
        ),
    ):
        return run_verify_v2(**kwargs)  # type: ignore[arg-type]


# --- flag parsing / mode dispatch --------------------------------------


@pytest.mark.parametrize(
    "missing_flag",
    ["--artifact", "--criteria", "--verification-run-id", "--attempt"],
)
def test_v2_mode_missing_required_flag_is_argparse_error(
    tmp_path: Path, missing_flag: str, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = [
        "--out",
        str(tmp_path / "out" / "attempt-001.json"),
        "--artifact",
        "reports/topic-x/result.md",
        "--criteria",
        str(tmp_path / "criteria.yaml"),
        "--verification-run-id",
        "run-1",
        "--attempt",
        "1",
    ]
    # Strip the flag-and-value pair for the one under test.
    idx = argv.index(missing_flag)
    del argv[idx : idx + 2]

    with pytest.raises(SystemExit) as exc_info:
        main(argv)
    assert exc_info.value.code == 2
    assert "--out requires" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()


def test_legacy_mode_missing_brief_is_argparse_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main([])
    assert exc_info.value.code == 2
    assert "--brief is required" in capsys.readouterr().err


def test_out_absent_dispatches_to_legacy_run_verify(tmp_path: Path) -> None:
    with patch("research_bench.cli.run_verify", return_value=0) as run_verify:
        code = main(["--brief", "briefs/topic-x", "--root", str(tmp_path)])
    assert code == 0
    run_verify.assert_called_once()
    (root_arg, brief_arg, config_arg) = run_verify.call_args.args
    assert root_arg == tmp_path.resolve()
    assert brief_arg == tmp_path.resolve() / "briefs/topic-x"
    assert config_arg == tmp_path.resolve() / "bench.config.yaml"


def test_out_given_dispatches_to_run_verify_v2(tmp_path: Path) -> None:
    out_path = tmp_path / "out" / "attempt-001.json"
    with patch("research_bench.cli.run_verify_v2", return_value=0) as v2:
        code = main(
            [
                "--out",
                str(out_path),
                "--artifact",
                "reports/topic-x/result.md",
                "--criteria",
                str(tmp_path / "criteria.yaml"),
                "--verification-run-id",
                "run-1",
                "--attempt",
                "1",
                "--root",
                str(tmp_path),
            ]
        )
    assert code == 0
    v2.assert_called_once()
    kwargs = v2.call_args.kwargs
    assert kwargs["artifact_rel"] == "reports/topic-x/result.md"
    assert kwargs["criteria_path"] == Path(tmp_path / "criteria.yaml")
    assert kwargs["out_path"] == out_path
    assert kwargs["verification_run_id"] == "run-1"
    assert kwargs["attempt"] == 1


# --- criteria loaded from an arbitrary --criteria path ------------------


def test_v2_criteria_loaded_from_exact_path_no_briefs_assumption(
    tmp_path: Path,
) -> None:
    root = _project(tmp_path, criteria_name="attempt-001.criteria")
    out_path = root / "out" / "attempt-001.json"
    code = _run_v2(
        root,
        out_path,
        criteria_path=root / "staging" / "attempt-001.criteria",
    )
    assert code == 0
    document = json.loads(out_path.read_text())
    assert document["verdict"] == "PASS"
    assert len(document["identity"]["criteria_sha256"]) == 64


# --- v2 document shape / identity fields --------------------------------


def test_v2_pass_writes_schema_valid_document_with_env_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MAESTRO_PROFILE_SHA256", "profile-sha")
    monkeypatch.setenv("MAESTRO_VERIFIED_SOURCE_COMMIT", "commit-sha")
    monkeypatch.setenv("MAESTRO_VERIFIED_SOURCE_TREE", "tree-sha")
    monkeypatch.setenv("MAESTRO_WORKSTREAM_ID", "ws-alpha")
    monkeypatch.setenv("MAESTRO_REWORK_ATTEMPT", "2")
    root = _project(tmp_path)
    out_path = root / "out" / "attempt-001.json"

    code = _run_v2(root, out_path, verification_run_id="run-xyz", attempt=3)

    assert code == 0
    document = json.loads(out_path.read_text())
    assert document["schema_version"] == 2
    identity = document["identity"]
    assert identity["verification_run_id"] == "run-xyz"
    assert identity["verification_attempt"] == 3
    assert identity["rework_attempt"] == 2
    assert identity["workstream_id"] == "ws-alpha"
    assert identity["artifact"] == "reports/topic-x/result.md"
    assert len(identity["artifact_sha256"]) == 64
    assert identity["profile_sha256"] == "profile-sha"
    assert identity["verified_source_commit"] == "commit-sha"
    assert identity["verified_source_tree"] == "tree-sha"
    assert document["findings"] == []

    _validate_v2(document)


# --- fail-closed: the five-var echo-env contract ------------------------


@pytest.mark.parametrize("missing_var", ECHO_ENV_VARS)
def test_v2_missing_identity_env_var_is_error_document_exit_2(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    missing_var: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv(missing_var, raising=False)
    root = _project(tmp_path)
    out_path = root / "out" / "attempt-001.json"

    code = _run_v2(root, out_path)

    assert code == 2
    document = json.loads(out_path.read_text())
    assert document["verdict"] == "ERROR"
    assert document["findings"] == []
    _validate_v2(document)
    assert missing_var in capsys.readouterr().err


@pytest.mark.parametrize("empty_value", ["", "   "])
def test_v2_empty_identity_env_var_is_error_document_exit_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, empty_value: str
) -> None:
    monkeypatch.setenv("MAESTRO_WORKSTREAM_ID", empty_value)
    root = _project(tmp_path)
    out_path = root / "out" / "attempt-001.json"

    code = _run_v2(root, out_path)

    assert code == 2
    document = json.loads(out_path.read_text())
    assert document["verdict"] == "ERROR"
    _validate_v2(document)


def test_v2_rework_attempt_not_an_integer_is_error_document_exit_2(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MAESTRO_REWORK_ATTEMPT", "not-an-int")
    root = _project(tmp_path)
    out_path = root / "out" / "attempt-001.json"

    code = _run_v2(root, out_path)

    assert code == 2
    document = json.loads(out_path.read_text())
    assert document["verdict"] == "ERROR"
    assert document["identity"]["rework_attempt"] == 0
    _validate_v2(document)
    assert "MAESTRO_REWORK_ATTEMPT" in capsys.readouterr().err


def test_v2_identity_error_document_still_carries_real_artifact_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Never-guess applies to echo fields, not independently-derivable ones.

    Run id/attempt/artifact path/hashes stay real even on the fail-closed
    ERROR path, since they aid debugging and are not fabricated.
    """
    monkeypatch.delenv("MAESTRO_WORKSTREAM_ID", raising=False)
    root = _project(tmp_path)
    out_path = root / "out" / "attempt-001.json"

    code = _run_v2(root, out_path, verification_run_id="run-real", attempt=5)

    assert code == 2
    identity = json.loads(out_path.read_text())["identity"]
    assert identity["verification_run_id"] == "run-real"
    assert identity["verification_attempt"] == 5
    assert identity["artifact"] == "reports/topic-x/result.md"
    assert len(identity["artifact_sha256"]) == 64
    assert len(identity["criteria_sha256"]) == 64
    assert identity["workstream_id"] == ""


def test_v2_identity_error_writes_no_pipeline_output_and_empty_raw(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pipeline never runs when identity is invalid (fail fast)."""
    monkeypatch.delenv("MAESTRO_PROFILE_SHA256", raising=False)
    root = _project(tmp_path)
    out_path = root / "out" / "attempt-001.json"
    with (
        patch("research_bench.cli.run_deterministic") as deterministic,
        patch("research_bench.cli.run_link_resolve") as link_resolve,
        patch("research_bench.cli.run_critic") as critic,
    ):
        code = run_verify_v2(
            root=root,
            config_path=root / "bench.config.yaml",
            artifact_rel="reports/topic-x/result.md",
            criteria_path=root / "staging" / "staged.criteria",
            out_path=out_path,
            verification_run_id="run-1",
            attempt=1,
        )
    assert code == 2
    deterministic.assert_not_called()
    link_resolve.assert_not_called()
    critic.assert_not_called()
    assert (root / "out" / "attempt-001.raw.txt").read_text() == ""


def test_v2_identity_error_survives_invalid_attempt_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: schema `verification_attempt.minimum` is 1, argparse isn't.

    `--attempt` (argparse `type=int`) has no lower bound. Combined with a
    missing echo-env var (forcing the identity-error path), a naive
    `VerdictIdentityV2(verification_attempt=0, ...)` raises a pydantic
    `ValidationError` -- BEFORE this task's fix, that happened outside any
    try/except in `_write_v2_identity_error` and crashed the whole call:
    no document at --out, no contractual exit 2. This is exactly the
    "untrustworthy invocation" case the always-write guarantee exists for.
    """
    monkeypatch.delenv("MAESTRO_WORKSTREAM_ID", raising=False)
    root = _project(tmp_path)
    out_path = root / "out" / "attempt-001.json"

    code = main(
        [
            "--out",
            str(out_path),
            "--artifact",
            "reports/topic-x/result.md",
            "--criteria",
            str(root / "staging" / "staged.criteria"),
            "--verification-run-id",
            "run-1",
            "--attempt",
            "0",
            "--root",
            str(root),
        ]
    )

    assert code == 2
    assert out_path.is_file()
    document = json.loads(out_path.read_text())
    assert document["verdict"] == "ERROR"
    assert document["identity"]["verification_attempt"] == 1
    _validate_v2(document)


def test_v2_pipeline_document_construction_survives_invalid_attempt_zero(
    tmp_path: Path,
) -> None:
    """Same construction-time crash risk in the pipeline's `finally` block.

    Not just the identity-error path: before the fix, a malformed
    `--attempt 0` with otherwise-valid identity would raise inside
    `finally`'s inner try, get caught by the broad `except Exception`, and
    set `write_failed=True` WITHOUT ever writing a document -- exit 2 with
    nothing at --out, same always-write violation. The actual verdict
    (here PASS) must survive; only the out-of-range attempt is clamped.
    """
    root = _project(tmp_path)
    out_path = root / "out" / "attempt-001.json"

    code = _run_v2(root, out_path, attempt=0)

    assert code == 0
    document = json.loads(out_path.read_text())
    assert document["verdict"] == "PASS"
    assert document["identity"]["verification_attempt"] == 1
    _validate_v2(document)


# --- fail-closed: BaseException during the pipeline ----------------------


def test_v2_keyboard_interrupt_still_writes_error_document(tmp_path: Path) -> None:
    root = _project(tmp_path)
    out_path = root / "out" / "attempt-001.json"
    with (
        patch("research_bench.cli.run_deterministic", side_effect=KeyboardInterrupt),
        pytest.raises(KeyboardInterrupt),
    ):
        run_verify_v2(
            root=root,
            config_path=root / "bench.config.yaml",
            artifact_rel="reports/topic-x/result.md",
            criteria_path=root / "staging" / "staged.criteria",
            out_path=out_path,
            verification_run_id="run-123",
            attempt=1,
        )
    document = json.loads(out_path.read_text())
    assert document["verdict"] == "ERROR"
    _validate_v2(document)


def test_v2_fail_verdict_exit_1_document_written(tmp_path: Path) -> None:
    root = _project(tmp_path)
    (root / "reports/topic-x/result.md").write_text("No sources here [S9].")
    out_path = root / "out" / "attempt-001.json"
    code = _run_v2(root, out_path)
    assert code == 1
    assert json.loads(out_path.read_text())["verdict"] == "FAIL"


def test_v2_sidecars_written_same_stem(tmp_path: Path) -> None:
    root = _project(tmp_path)
    out_path = root / "out" / "attempt-001.json"
    code = _run_v2(root, out_path)
    assert code == 0
    assert (root / "out" / "attempt-001.md").is_file()
    assert (root / "out" / "attempt-001.raw.txt").is_file()


# --- findings wired into the v2 document (Task 4) ------------------------


def test_v2_deterministic_finding_populates_document_with_author_feedback(
    tmp_path: Path,
) -> None:
    """A real (unmocked) deterministic-stage finding reaches the document.

    `findings` used to be hardcoded `[]` in v2 mode (Task 3's deliberate
    deferral). This proves the wiring: a bad artifact produces a FAIL
    document whose `findings` are populated and schema-valid, each with a
    non-empty `author_feedback` (the rework-addendum channel).
    """
    root = _project(tmp_path)
    (root / "reports/topic-x/result.md").write_text("No sources here [S9].")
    out_path = root / "out" / "attempt-001.json"

    code = _run_v2(root, out_path)

    assert code == 1
    document = json.loads(out_path.read_text())
    assert document["verdict"] == "FAIL"
    assert document["findings"]
    for finding in document["findings"]:
        assert finding["author_feedback"]
    _validate_v2(document)


def test_v2_critic_findings_translated_with_author_feedback_validate(
    tmp_path: Path,
) -> None:
    """Critic-stage findings (with `author_feedback`) flow into the document.

    `run_critic` is mocked at the boundary (same pattern as `_run_v2`), but
    here it returns a FAIL with a populated finding to prove `cli.py`
    translates v1 `Finding` -> v2 `Finding` end to end and the result
    validates against the vendored schema.
    """
    root = _project(tmp_path)
    out_path = root / "out" / "attempt-001.json"
    critic_finding = Finding(
        criterion_id="synthesis",
        severity="major",
        evidence="conclusion states X without qualification",
        author_feedback="Distinguish your conclusion from the cited evidence.",
    )
    with (
        patch(
            "research_bench.cli.run_link_resolve",
            return_value=_stage("link-resolve", VerdictKind.PASS),
        ),
        patch(
            "research_bench.cli.run_critic",
            return_value=(
                StageResult(
                    stage="critic",
                    verdict=VerdictKind.FAIL,
                    findings=[critic_finding],
                    detail="1 of 1 criteria failed",
                ),
                "raw-critic-output",
            ),
        ),
    ):
        code = run_verify_v2(
            root=root,
            config_path=root / "bench.config.yaml",
            artifact_rel="reports/topic-x/result.md",
            criteria_path=root / "staging" / "staged.criteria",
            out_path=out_path,
            verification_run_id="run-123",
            attempt=1,
        )

    assert code == 1
    document = json.loads(out_path.read_text())
    assert document["verdict"] == "FAIL"
    [finding] = document["findings"]
    assert finding["criterion_id"] == "synthesis"
    assert finding["severity"] == "major"
    assert finding["author_feedback"] == (
        "Distinguish your conclusion from the cited evidence."
    )
    _validate_v2(document)


# --- allocate_attempt is legacy-mode-only --------------------------------


def test_v2_mode_never_calls_allocate_attempt(tmp_path: Path) -> None:
    root = _project(tmp_path)
    out_path = root / "out" / "attempt-001.json"
    with patch("research_bench.cli.allocate_attempt") as allocate:
        code = _run_v2(root, out_path)
    assert code == 0
    allocate.assert_not_called()
    # And no v1-shaped verdicts/ tree was created either.
    assert not (root / "verdicts").exists()


# --- out-path discipline: nothing written outside --out's parent --------


def test_v2_writes_nothing_outside_out_dir_worktree_untouched(tmp_path: Path) -> None:
    root = _project(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=t@t.com",
            "-c",
            "user.name=t",
            "commit",
            "-q",
            "-m",
            "x",
        ],
        cwd=root,
        check=True,
    )

    before = {p.relative_to(root) for p in root.rglob("*") if p.is_file()}
    out_path = root / "out" / "attempt-001.json"
    code = _run_v2(root, out_path)
    assert code == 0

    after_files = {p.relative_to(root) for p in root.rglob("*") if p.is_file()}
    new_files = after_files - before
    assert new_files == {
        Path("out/attempt-001.json"),
        Path("out/attempt-001.md"),
        Path("out/attempt-001.raw.txt"),
    }
    for f in new_files:
        assert f.parent == Path("out")

    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    # The out/ dir + its contents are untracked (never `git add`-ed), so
    # they show up as untracked -- that's expected and fine; what matters
    # is that no TRACKED file was modified.
    modified = [
        line for line in status.stdout.splitlines() if not line.startswith("??")
    ]
    assert modified == []
