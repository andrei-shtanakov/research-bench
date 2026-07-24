"""Tests for verdict report, attempt allocation and atomic writes."""

import json
from pathlib import Path

from research_bench.verdict import (
    EXIT_CODES,
    Finding,
    StageResult,
    VerdictKind,
    VerdictReport,
    allocate_attempt,
    render_md,
    sha256_file,
    write_report,
)


def _report(attempt: int = 1) -> VerdictReport:
    return VerdictReport(
        verdict=VerdictKind.FAIL,
        stages=[
            StageResult(
                stage="critic",
                verdict=VerdictKind.FAIL,
                findings=[
                    Finding(
                        criterion_id="synthesis",
                        severity="major",
                        evidence="Conclusion X has no supporting source.",
                    )
                ],
                detail="1 of 2 criteria failed",
            )
        ],
        artifact="reports/topic-x/result.md",
        artifact_sha256="a" * 64,
        criteria_sha256="b" * 64,
        critic_version="0.1.0",
        model="claude-sonnet-5",
        prompt_version="v1",
        attempt=attempt,
        timestamp="2026-07-24T00:00:00+00:00",
    )


def test_exit_codes_contract() -> None:
    assert EXIT_CODES[VerdictKind.PASS] == 0
    assert EXIT_CODES[VerdictKind.FAIL] == 1
    assert EXIT_CODES[VerdictKind.ERROR] == 2


def test_allocate_attempt_is_monotonic(tmp_path: Path) -> None:
    n1, p1 = allocate_attempt(tmp_path)
    n2, p2 = allocate_attempt(tmp_path)
    assert (n1, n2) == (1, 2)
    assert p1.name == "attempt-001.json"
    assert p2.name == "attempt-002.json"
    assert p1.exists() and p2.exists()  # exclusive-create reserves the slot


def test_write_report_is_append_only(tmp_path: Path) -> None:
    n1, p1 = allocate_attempt(tmp_path)
    write_report(_report(n1), p1, raw_output="raw-1")
    first = p1.read_text()
    n2, p2 = allocate_attempt(tmp_path)
    write_report(_report(n2), p2, raw_output="raw-2")
    assert p1.read_text() == first  # retry never overwrites prior evidence
    assert (tmp_path / "attempt-001.raw.txt").read_text() == "raw-1"
    assert (tmp_path / "attempt-002.raw.txt").read_text() == "raw-2"


def test_written_json_is_valid_and_md_rendered(tmp_path: Path) -> None:
    n, p = allocate_attempt(tmp_path)
    write_report(_report(n), p, raw_output="raw")
    data = json.loads(p.read_text())
    assert data["verdict"] == "FAIL"
    assert data["artifact_sha256"] == "a" * 64
    md = (tmp_path / "attempt-001.md").read_text()
    assert "FAIL" in md and "synthesis" in md


def test_render_md_uses_model_only() -> None:
    md = render_md(_report())
    assert "attempt: 1" in md
    assert "Conclusion X has no supporting source." in md


def test_sha256_file_missing_returns_empty(tmp_path: Path) -> None:
    assert sha256_file(tmp_path / "nope.md") == ""
