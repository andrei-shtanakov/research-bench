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
    """Load and validate a criteria manifest from `path`, verbatim.

    `path` is read exactly as given: no `briefs/<topic>/criteria.yaml`
    assumption, no extension requirement. Legacy (`--brief`) callers pass
    `briefs/<topic>/criteria.yaml`; v2 (`--out`) callers pass Maestro's
    `--criteria` value directly, which may be an ephemeral staged copy
    (e.g. `attempt-001.criteria`, no `.yaml` suffix) rather than a file
    under `briefs/`.
    """
    data = yaml.safe_load(path.read_text())
    return CriteriaManifest.model_validate(data)
