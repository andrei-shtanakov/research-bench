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

from research_bench.cli import main, run_verify_v2
from research_bench.verdict import Stage, StageResult, VerdictKind

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
    root = _project(tmp_path)
    out_path = root / "out" / "attempt-001.json"

    code = _run_v2(root, out_path, verification_run_id="run-xyz", attempt=3)

    assert code == 0
    document = json.loads(out_path.read_text())
    assert document["schema_version"] == 2
    identity = document["identity"]
    assert identity["verification_run_id"] == "run-xyz"
    assert identity["verification_attempt"] == 3
    assert identity["rework_attempt"] == 0
    assert identity["artifact"] == "reports/topic-x/result.md"
    assert len(identity["artifact_sha256"]) == 64
    assert identity["profile_sha256"] == "profile-sha"
    assert identity["verified_source_commit"] == "commit-sha"
    assert identity["verified_source_tree"] == "tree-sha"
    assert document["findings"] == []

    schema = json.loads(VENDORED_SCHEMA_PATH.read_text())
    jsonschema.Draft202012Validator(schema).validate(document)


def test_v2_missing_env_identity_defaults_to_empty_string(tmp_path: Path) -> None:
    root = _project(tmp_path)
    out_path = root / "out" / "attempt-001.json"
    code = _run_v2(root, out_path)
    assert code == 0
    identity = json.loads(out_path.read_text())["identity"]
    assert identity["profile_sha256"] == ""
    assert identity["verified_source_commit"] == ""
    assert identity["verified_source_tree"] == ""


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
