"""Criteria manifest: the machine-readable acceptance-criteria contract."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class Criterion(BaseModel):
    """One acceptance criterion referenced by critic findings."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9-]*$")
    description: str = Field(min_length=1)


class CriteriaManifest(BaseModel):
    """Versioned bench-local contract next to a brief."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(ge=1)
    artifact: str = Field(min_length=1)
    criteria: list[Criterion] = Field(min_length=1)


def load_criteria(path: Path) -> CriteriaManifest:
    """Load and validate a criteria.yaml manifest."""
    data = yaml.safe_load(path.read_text())
    return CriteriaManifest.model_validate(data)
