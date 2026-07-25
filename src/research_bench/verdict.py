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
    """Result and findings from one verification stage."""

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
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


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


def write_report(report: VerdictReport, reserved_json: Path, raw_output: str) -> None:
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


class FindingV2(BaseModel):
    """One criterion violation reported by the verifier (Maestro verdict v2).

    Mirrors the vendored schema's `Finding` def
    (`contracts/maestro-verdict-v2/verdict_v2.json`): unlike v1's `Finding`,
    `author_feedback` is required — the explicit declassification channel
    for the rework addendum.
    """

    model_config = ConfigDict(extra="forbid")

    criterion_id: str
    severity: Literal["info", "minor", "major"]
    evidence: str
    author_feedback: str


class VerdictIdentityV2(BaseModel):
    """Identity block binding an attempt to run, artifact, rubric, profile.

    Field set and names match the vendored `VerdictIdentity` def exactly
    (Task 1's `contracts/maestro-verdict-v2/verdict_v2.json`).
    """

    model_config = ConfigDict(extra="forbid")

    verification_run_id: str
    verification_attempt: int = Field(ge=1)
    rework_attempt: int = Field(ge=0)
    workstream_id: str
    artifact: str
    artifact_sha256: str
    criteria_sha256: str
    profile_sha256: str
    verified_source_commit: str
    verified_source_tree: str


class VerdictDocumentV2(BaseModel):
    """Canonical Maestro-owned verdict v2 document (`schema_version=2`).

    Written verbatim to `--out` in v2 invocation mode; no `allocate_attempt`
    self-numbering (Maestro owns addressing, §9 of the verifier contract).
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[2] = 2
    identity: VerdictIdentityV2
    verdict: VerdictKind
    findings: list[FindingV2] = Field(default_factory=list)


def write_v2_report(
    document: VerdictDocumentV2, out_path: Path, raw_output: str
) -> None:
    """Write v2 verdict files at EXACTLY `out_path` (Maestro-owned address).

    Sidecars `.md`/`.raw.txt` share `out_path`'s stem; all three files land
    under `out_path.parent` only (no writes anywhere else in the
    worktree). Same append-safe order as v1's `write_report` (raw, md, then
    atomic JSON last via `os.replace`): the canonical JSON's presence
    guarantees the complete attempt has landed.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    stem = out_path.stem
    (out_path.parent / f"{stem}.raw.txt").write_text(raw_output)
    (out_path.parent / f"{stem}.md").write_text(render_md_v2(document))
    tmp = out_path.with_name(out_path.name + ".tmp")
    tmp.write_text(document.model_dump_json(indent=2) + "\n")
    os.replace(tmp, out_path)


def render_md_v2(document: VerdictDocumentV2) -> str:
    """Render the human-readable summary strictly from the v2 document."""
    identity = document.identity
    lines = [
        f"# bench-verify verdict (v2): {document.verdict}",
        "",
        f"- artifact: `{identity.artifact}` (sha256 `{identity.artifact_sha256}`)",
        f"- criteria sha256: `{identity.criteria_sha256}`",
        f"- verification run: `{identity.verification_run_id}` "
        f"attempt {identity.verification_attempt} "
        f"(rework attempt {identity.rework_attempt})",
        f"- workstream: `{identity.workstream_id}`",
        f"- profile sha256: `{identity.profile_sha256}`",
        f"- verified source: commit `{identity.verified_source_commit}` "
        f"tree `{identity.verified_source_tree}`",
        "",
    ]
    for finding in document.findings:
        lines.append(
            f"- **{finding.severity}** `{finding.criterion_id}`: {finding.evidence}"
        )
        if finding.author_feedback:
            lines.append(f"  - feedback: {finding.author_feedback}")
    return "\n".join(lines)


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
            lines.append(f"- **{f.severity}** `{f.criterion_id}`: {f.evidence}")
        lines.append("")
    return "\n".join(lines)
