"""Tests for the deterministic verification stage."""

from pathlib import Path

from research_bench.checks import extract_source_urls, run_deterministic
from research_bench.criteria import CriteriaManifest
from research_bench.verdict import VerdictKind

GOOD = """\
# Report

SQLite WAL improves write concurrency [S1]. Checkpointing has costs [S2].

## Sources
- [S1] https://sqlite.org/wal.html
- [S2] https://example.com/wal-tradeoffs
"""


def _manifest(artifact: str = "reports/topic-x/result.md") -> CriteriaManifest:
    return CriteriaManifest.model_validate(
        {
            "schema_version": 1,
            "artifact": artifact,
            "criteria": [{"id": "synthesis", "description": "d"}],
        }
    )


def _write(root: Path, text: str, rel: str = "reports/topic-x/result.md") -> None:
    path = root / rel
    path.parent.mkdir(parents=True)
    path.write_text(text)


def test_good_artifact_passes(tmp_path: Path) -> None:
    _write(tmp_path, GOOD)
    result = run_deterministic(tmp_path, _manifest())
    assert result.verdict == VerdictKind.PASS


def test_missing_artifact_fails(tmp_path: Path) -> None:
    result = run_deterministic(tmp_path, _manifest())
    assert result.verdict == VerdictKind.FAIL
    assert result.findings[0].criterion_id == "det/artifact-missing"


def test_artifact_outside_reports_fails(tmp_path: Path) -> None:
    _write(tmp_path, GOOD, rel="briefs/evil.md")
    result = run_deterministic(tmp_path, _manifest(artifact="briefs/evil.md"))
    assert result.verdict == VerdictKind.FAIL
    assert any(f.criterion_id == "det/artifact-path" for f in result.findings)


def test_undefined_citation_fails(tmp_path: Path) -> None:
    _write(tmp_path, "Claim [S9].\n\n## Sources\n- [S1] https://a.example\n")
    result = run_deterministic(tmp_path, _manifest())
    assert result.verdict == VerdictKind.FAIL
    assert any(f.criterion_id == "det/citation-undefined" for f in result.findings)


def test_unused_source_is_minor_not_fail(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "Claim [S1].\n\n## Sources\n- [S1] https://a.example\n- [S2] https://b.example\n",
    )
    result = run_deterministic(tmp_path, _manifest())
    assert result.verdict == VerdictKind.PASS
    assert any(
        f.criterion_id == "det/source-unused" and f.severity == "minor"
        for f in result.findings
    )


def test_secret_fails(tmp_path: Path) -> None:
    _write(tmp_path, GOOD + "\nkey AKIAABCDEFGHIJKLMNOP leaked\n")
    result = run_deterministic(tmp_path, _manifest())
    assert result.verdict == VerdictKind.FAIL
    assert any(f.criterion_id == "det/secret" for f in result.findings)


def test_extract_source_urls() -> None:
    assert extract_source_urls(GOOD) == [
        "https://sqlite.org/wal.html",
        "https://example.com/wal-tradeoffs",
    ]


def test_dotdot_traversal_fails_without_read(tmp_path: Path) -> None:
    result = run_deterministic(tmp_path, _manifest(artifact="reports/../../outside.md"))
    assert result.verdict == VerdictKind.FAIL
    assert result.findings[0].criterion_id == "det/artifact-path"


def test_absolute_artifact_fails_without_read(tmp_path: Path) -> None:
    outside = tmp_path / "outside.md"
    outside.write_text("secret AKIAABCDEFGHIJKLMNOP")
    result = run_deterministic(tmp_path, _manifest(artifact=str(outside)))
    assert result.verdict == VerdictKind.FAIL
    assert result.findings[0].criterion_id == "det/artifact-path"
    assert all("AKIA" not in f.evidence for f in result.findings)


def test_indented_source_line_is_recognized(tmp_path: Path) -> None:
    _write(tmp_path, "Claim [S1].\n\n## Sources\n  - [S1] https://a.example\n")
    result = run_deterministic(tmp_path, _manifest())
    assert result.verdict == VerdictKind.PASS
