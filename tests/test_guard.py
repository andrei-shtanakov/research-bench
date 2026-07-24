"""Tests for the single-task-guard plugin entrypoint."""

from pathlib import Path

import pytest

from research_bench.guard import run_guard

ONE_TASK = """\
### TASK-001: Write the research report
🔴 P0 | ⬜ TODO | Est: 2h

**Description:**
Collect sources, synthesize, and write reports/topic-x/result.md.

**Checklist:**
- [ ] Collect sources
- [ ] Write report
"""

TWO_TASKS = (
    ONE_TASK
    + """
### TASK-002: Polish the report
🟡 P2 | ⬜ TODO | Est: 1h

**Description:**
Second task that must trip the guard.
"""
)

DONE_ONLY = """\
### TASK-001: Already finished
🔴 P0 | ✅ DONE | Est: 1h

**Description:**
Nothing executable here.
"""


def _project(
    tmp_path: Path, tasks_md: str | None, name: str = "maestro-tasks.md"
) -> Path:
    if tasks_md is not None:
        spec = tmp_path / "spec"
        spec.mkdir()
        (spec / name).write_text(tasks_md)
    return tmp_path


def test_exactly_one_task_passes(tmp_path: Path) -> None:
    assert run_guard(_project(tmp_path, ONE_TASK)) == 0


def test_two_tasks_exit_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run_guard(_project(tmp_path, TWO_TASKS)) == 1
    assert "found 2" in capsys.readouterr().err


def test_zero_executable_tasks_exit_1(tmp_path: Path) -> None:
    assert run_guard(_project(tmp_path, DONE_ONLY)) == 1


def test_missing_spec_file_exit_2(tmp_path: Path) -> None:
    assert run_guard(_project(tmp_path, None)) == 2


def test_fallback_to_plain_tasks_md(tmp_path: Path) -> None:
    assert run_guard(_project(tmp_path, ONE_TASK, name="tasks.md")) == 0


def test_missing_env_exit_2(monkeypatch: pytest.MonkeyPatch) -> None:
    from research_bench.guard import main

    monkeypatch.delenv("SR_PROJECT_ROOT", raising=False)
    assert main() == 2


def test_parse_tasks_systemexit_is_infra_exit_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import research_bench.guard as guard_mod

    def fake_parse_tasks(path: Path) -> list:
        raise SystemExit(1)

    monkeypatch.setattr(guard_mod, "parse_tasks", fake_parse_tasks)
    assert run_guard(_project(tmp_path, ONE_TASK)) == 2
