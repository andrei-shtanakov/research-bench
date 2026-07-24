"""Tests for the criteria.yaml manifest loader."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from research_bench.criteria import load_criteria

VALID = """\
schema_version: 1
artifact: reports/topic-x/result.md
criteria:
  - id: source-coverage
    description: Every material claim has a cited source
  - id: synthesis
    description: Conclusions distinguish evidence from inference
"""


def test_load_valid_manifest(tmp_path: Path) -> None:
    path = tmp_path / "criteria.yaml"
    path.write_text(VALID)
    manifest = load_criteria(path)
    assert manifest.schema_version == 1
    assert manifest.artifact == "reports/topic-x/result.md"
    assert [c.id for c in manifest.criteria] == ["source-coverage", "synthesis"]


def test_schema_version_is_required(tmp_path: Path) -> None:
    path = tmp_path / "criteria.yaml"
    path.write_text("artifact: r.md\ncriteria:\n  - id: a\n    description: d\n")
    with pytest.raises(ValidationError):
        load_criteria(path)


def test_empty_criteria_rejected(tmp_path: Path) -> None:
    path = tmp_path / "criteria.yaml"
    path.write_text("schema_version: 1\nartifact: r.md\ncriteria: []\n")
    with pytest.raises(ValidationError):
        load_criteria(path)


def test_bad_criterion_id_rejected(tmp_path: Path) -> None:
    path = tmp_path / "criteria.yaml"
    path.write_text(
        "schema_version: 1\nartifact: r.md\n"
        "criteria:\n  - id: 'Bad ID!'\n    description: d\n"
    )
    with pytest.raises(ValidationError):
        load_criteria(path)
