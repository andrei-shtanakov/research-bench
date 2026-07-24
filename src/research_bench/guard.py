"""single-task-guard: pre_start assertion for the Stage A pilot.

Blocks execution (blocking pre_start plugin hook) unless the generated
spec contains exactly one executable task. Uses spec-runner's canonical
parser — never a Markdown heuristic of our own.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from spec_runner.task import parse_tasks

EXECUTABLE_STATUSES = {"todo", "in_progress", "blocked"}
SPEC_CANDIDATES = ("spec/maestro-tasks.md", "spec/tasks.md")


def run_guard(project_root: Path) -> int:
    """Return 0 for exactly one executable task, 1 otherwise, 2 on infra."""
    spec = next(
        (project_root / c for c in SPEC_CANDIDATES if (project_root / c).exists()),
        None,
    )
    if spec is None:
        print(
            f"single-task-guard: no spec file under {project_root} "
            f"(tried {', '.join(SPEC_CANDIDATES)})",
            file=sys.stderr,
        )
        return 2
    try:
        tasks = parse_tasks(spec)
    except (Exception, SystemExit) as exc:
        print(f"single-task-guard: cannot parse {spec}: {exc}", file=sys.stderr)
        return 2
    count = sum(1 for t in tasks if t.status in EXECUTABLE_STATUSES)
    if count == 1:
        return 0
    print(
        f"single-task-guard: expected exactly 1 executable task, "
        f"found {count} in {spec}",
        file=sys.stderr,
    )
    return 1


def main() -> int:
    """Console entrypoint; project root comes from SR_PROJECT_ROOT."""
    root = os.environ.get("SR_PROJECT_ROOT")
    if not root:
        print("single-task-guard: SR_PROJECT_ROOT not set", file=sys.stderr)
        return 2
    return run_guard(Path(root))


if __name__ == "__main__":
    sys.exit(main())
