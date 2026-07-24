"""Verdict report: canonical JSON output, append-only attempts, MD render."""

from __future__ import annotations

import hashlib
import os
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class VerdictKind(StrEnum):
    """Verdict outcome: pass, fail, or error."""

    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"


EXIT_CODES: dict[VerdictKind, int] = {
    VerdictKind.PASS: 0,
    VerdictKind.FAIL: 1,
    VerdictKind.ERROR: 2,
}

Stage = Literal["deterministic", "link-resolve", "critic"]


class Finding(BaseModel):
    """A single finding from the critic referencing a criterion."""

    model_config = ConfigDict(extra="forbid")

    criterion_id: str
    severity: Literal["info", "minor", "major"]
    evidence: str


class StageResult(BaseModel):
    """Result and findings from one critic stage."""

    model_config = ConfigDict(extra="forbid")

    stage: Stage
    verdict: VerdictKind
    findings: list[Finding] = Field(default_factory=list)
    detail: str = ""


class VerdictReport(BaseModel):
    """Canonical machine output; the MD file is a render of this model."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    verdict: VerdictKind
    stages: list[StageResult]
    artifact: str
    artifact_sha256: str
    criteria_sha256: str
    critic_version: str
    model: str
    prompt_version: str
    attempt: int
    timestamp: str


def sha256_file(path: Path) -> str:
    """Hex sha256 of a file, or "" when the file does not exist."""
    if not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def allocate_attempt(verdict_dir: Path) -> tuple[int, Path]:
    """Reserve the next attempt slot via exclusive create (append-only)."""
    verdict_dir.mkdir(parents=True, exist_ok=True)
    existing = [
        int(p.stem.split("-")[1])
        for p in verdict_dir.glob("attempt-*.json")
        if p.stem.split("-")[1].isdigit()
    ]
    n = max(existing, default=0) + 1
    while True:
        path = verdict_dir / f"attempt-{n:03d}.json"
        try:
            path.open("x").close()
            # Reserved slot is an empty file; intentionally skipped if never written.
            return n, path
        except FileExistsError:
            n += 1


def write_report(
    report: VerdictReport, reserved_json: Path, raw_output: str
) -> None:
    """Write report files in append-safe order: raw, md, then atomic JSON last.

    The canonical JSON is written last via os.replace, so its presence
    guarantees the complete attempt (md + raw) has landed.
    """
    stem = reserved_json.stem  # attempt-NNN
    (reserved_json.parent / f"{stem}.raw.txt").write_text(raw_output)
    (reserved_json.parent / f"{stem}.md").write_text(render_md(report))
    tmp = reserved_json.with_name(reserved_json.name + ".tmp")
    tmp.write_text(report.model_dump_json(indent=2) + "\n")
    os.replace(tmp, reserved_json)


def render_md(report: VerdictReport) -> str:
    """Render the human-readable summary strictly from the JSON model."""
    lines = [
        f"# bench-verify verdict: {report.verdict}",
        "",
        f"- artifact: `{report.artifact}` (sha256 `{report.artifact_sha256}`)",
        f"- criteria sha256: `{report.criteria_sha256}`",
        f"- critic: {report.critic_version}, model {report.model}, "
        f"prompt {report.prompt_version}",
        f"- attempt: {report.attempt}",
        f"- timestamp: {report.timestamp}",
        "",
    ]
    for stage in report.stages:
        lines.append(f"## {stage.stage}: {stage.verdict}")
        if stage.detail:
            lines.append(f"{stage.detail}")
        for f in stage.findings:
            lines.append(
                f"- **{f.severity}** `{f.criterion_id}`: {f.evidence}"
            )
        lines.append("")
    return "\n".join(lines)
