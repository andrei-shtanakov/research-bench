"""Integration: a failing blocking pre_start guard prevents agent invocation."""

import subprocess
import sys
from pathlib import Path

import pytest

TWO_TASKS = """\
### TASK-001: First
🔴 P0 | ⬜ TODO | Est: 1h

**Description:**
First task.

### TASK-002: Second
🟡 P2 | ⬜ TODO | Est: 1h

**Description:**
Second task that must trip the guard.
"""


@pytest.mark.slow
def test_failing_guard_means_zero_agent_invocations(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    (project / "spec" / "plugins" / "single-task-guard").mkdir(parents=True)
    (project / "spec" / "tasks.md").write_text(TWO_TASKS)

    invocations = tmp_path / "invocations.log"
    fake_agent = tmp_path / "fake_agent.sh"
    fake_agent.write_text(
        f"#!/bin/sh\necho invoked >> {invocations}\necho TASK_COMPLETE\n"
    )
    fake_agent.chmod(0o755)

    (project / "spec" / "plugins" / "single-task-guard" / "plugin.yaml").write_text(
        "name: single-task-guard\n"
        "version: '0.1.0'\n"
        "hooks:\n"
        "  pre_start:\n"
        "    command: SR_PROJECT_ROOT="
        f"{project} {sys.executable} -m research_bench.guard\n"
        "    run_on: always\n"
        "    blocking: true\n"
    )
    (project / "spec-runner.config.yaml").write_text(
        f"claude_command: {fake_agent}\n"
        # NB: max_retries must be >= 1, not 0. spec-runner's retry loop is
        # `range(attempt_count, max_retries)`, so max_retries=0 makes the
        # loop body -- which runs pre_start hooks and invokes the agent --
        # never execute at all. With 0 the assertion below would pass
        # vacuously (zero attempts of anything, not "guard blocked the
        # agent"), defeating the point of the test. Confirmed via manual
        # repro: max_retries=0 produces zero "Plugin hook failed"/"Pre-start
        # hook failed" log lines, while max_retries=1 produces them and
        # still yields zero agent invocations.
        "max_retries: 1\n"
        "hooks:\n"
        "  pre_start:\n"
        "    create_git_branch: false\n"
        "    sync_deps: false\n"
        "  post_done:\n"
        "    run_tests: false\n"
        "    run_lint: false\n"
        "    auto_commit: false\n"
        "    run_review: false\n"
        "paths:\n"
        "  plugins: spec/plugins\n"
    )

    result = subprocess.run(
        ["spec-runner", "run", "--all"],
        cwd=project,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert not invocations.exists(), (
        f"agent was invoked despite failing guard:\n{result.stdout}\n{result.stderr}"
    )
