"""Tests for the bench-verify orchestration CLI."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from research_bench.cli import run_verify
from research_bench.verdict import Stage, StageResult, VerdictKind

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


def _project(tmp_path: Path, report: str | None = GOOD_REPORT) -> Path:
    (tmp_path / "briefs/topic-x").mkdir(parents=True)
    (tmp_path / "briefs/topic-x/criteria.yaml").write_text(CRITERIA)
    (tmp_path / "bench.config.yaml").write_text(CONFIG)
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts/critic-v1.md").write_text("{criteria_block}\n{artifact}")
    if report is not None:
        (tmp_path / "reports/topic-x").mkdir(parents=True)
        (tmp_path / "reports/topic-x/result.md").write_text(report)
    return tmp_path


def _stage(stage: Stage, verdict: VerdictKind) -> StageResult:
    return StageResult(stage=stage, verdict=verdict)


def _verdict_files(root: Path) -> list[Path]:
    return sorted((root / "verdicts").rglob("attempt-*.json"))


def test_pass_path_exit_0_and_verdict_written(tmp_path: Path) -> None:
    root = _project(tmp_path)
    with (
        patch(
            "research_bench.cli.run_link_resolve",
            return_value=_stage("link-resolve", VerdictKind.PASS),
        ),
        patch(
            "research_bench.cli.run_critic",
            return_value=(_stage("critic", VerdictKind.PASS), "raw"),
        ),
    ):
        code = run_verify(root, root / "briefs/topic-x", root / "bench.config.yaml")
    assert code == 0
    [report_path] = _verdict_files(root)
    data = json.loads(report_path.read_text())
    assert data["verdict"] == "PASS"
    assert len(data["artifact_sha256"]) == 64
    assert data["attempt"] == 1


def test_deterministic_fail_stops_early_exit_1(tmp_path: Path) -> None:
    root = _project(tmp_path, report="No sources here [S9].")
    with patch("research_bench.cli.run_critic") as critic:
        code = run_verify(root, root / "briefs/topic-x", root / "bench.config.yaml")
    assert code == 1
    critic.assert_not_called()  # first non-PASS stage stops the pipeline
    [report_path] = _verdict_files(root)
    assert json.loads(report_path.read_text())["verdict"] == "FAIL"


def test_link_error_exit_2_critic_skipped(tmp_path: Path) -> None:
    root = _project(tmp_path)
    with (
        patch(
            "research_bench.cli.run_link_resolve",
            return_value=_stage("link-resolve", VerdictKind.ERROR),
        ),
        patch("research_bench.cli.run_critic") as critic,
    ):
        code = run_verify(root, root / "briefs/topic-x", root / "bench.config.yaml")
    assert code == 2
    critic.assert_not_called()
    [report_path] = _verdict_files(root)
    assert json.loads(report_path.read_text())["verdict"] == "ERROR"


def test_broken_manifest_still_writes_error_verdict(tmp_path: Path) -> None:
    root = _project(tmp_path)
    (root / "briefs/topic-x/criteria.yaml").write_text("schema_version: 1\n")
    code = run_verify(root, root / "briefs/topic-x", root / "bench.config.yaml")
    assert code == 2
    [report_path] = _verdict_files(root)
    assert json.loads(report_path.read_text())["verdict"] == "ERROR"


def test_retry_appends_new_attempt(tmp_path: Path) -> None:
    root = _project(tmp_path)
    with (
        patch(
            "research_bench.cli.run_link_resolve",
            return_value=_stage("link-resolve", VerdictKind.PASS),
        ),
        patch(
            "research_bench.cli.run_critic",
            return_value=(_stage("critic", VerdictKind.PASS), "raw"),
        ),
    ):
        run_verify(root, root / "briefs/topic-x", root / "bench.config.yaml")
        run_verify(root, root / "briefs/topic-x", root / "bench.config.yaml")
    files = _verdict_files(root)
    assert [p.name for p in files] == ["attempt-001.json", "attempt-002.json"]


def test_finally_write_failure_returns_error_exit_2(tmp_path: Path) -> None:
    root = _project(tmp_path)
    # "verdicts" exists as a regular file, so allocate_attempt's mkdir(...)
    # raises and the finally block itself fails.
    (root / "verdicts").write_text("not a directory")
    with (
        patch(
            "research_bench.cli.run_link_resolve",
            return_value=_stage("link-resolve", VerdictKind.PASS),
        ),
        patch(
            "research_bench.cli.run_critic",
            return_value=(_stage("critic", VerdictKind.PASS), "raw"),
        ),
    ):
        code = run_verify(root, root / "briefs/topic-x", root / "bench.config.yaml")
    assert code == 2


def test_out_of_tree_artifact_is_not_hashed(tmp_path: Path) -> None:
    # manifest.artifact points outside reports/ (deterministic stage already
    # FAILs it), but the finally block must not use it as a content oracle
    # by hashing whatever file happens to sit at that out-of-tree path.
    root = _project(tmp_path, report=None)
    (root / "briefs/topic-x/criteria.yaml").write_text(
        "schema_version: 1\n"
        "artifact: secret.txt\n"
        "criteria:\n"
        "  - id: synthesis\n"
        "    description: d\n"
    )
    (root / "secret.txt").write_text("outside reports/, must not be hashed")
    code = run_verify(root, root / "briefs/topic-x", root / "bench.config.yaml")
    assert code == 1  # deterministic FAIL: det/artifact-path
    [report_path] = _verdict_files(root)
    data = json.loads(report_path.read_text())
    assert data["artifact_sha256"] == ""
    assert report_path.parent.name == "no-artifact"


def test_critic_exception_reports_critic_stage(tmp_path: Path) -> None:
    root = _project(tmp_path)
    with (
        patch(
            "research_bench.cli.run_link_resolve",
            return_value=_stage("link-resolve", VerdictKind.PASS),
        ),
        patch(
            "research_bench.cli.run_critic",
            side_effect=RuntimeError("boom"),
        ),
    ):
        code = run_verify(root, root / "briefs/topic-x", root / "bench.config.yaml")
    assert code == 2
    [report_path] = _verdict_files(root)
    data = json.loads(report_path.read_text())
    assert data["verdict"] == "ERROR"
    assert data["stages"][-1]["stage"] == "critic"


def test_keyboard_interrupt_still_writes_error_verdict(tmp_path: Path) -> None:
    root = _project(tmp_path)
    with (
        patch(
            "research_bench.cli.run_deterministic",
            side_effect=KeyboardInterrupt,
        ),
        pytest.raises(KeyboardInterrupt),
    ):
        run_verify(root, root / "briefs/topic-x", root / "bench.config.yaml")
    [report_path] = _verdict_files(root)
    assert json.loads(report_path.read_text())["verdict"] == "ERROR"
