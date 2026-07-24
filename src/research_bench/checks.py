"""Deterministic verification stage: everything checkable without an LLM."""

from __future__ import annotations

import re
from pathlib import Path

from .criteria import CriteriaManifest
from .verdict import Finding, StageResult, VerdictKind

CITATION = re.compile(r"\[S(\d+)\]")
SOURCE_LINE = re.compile(r"^-\s*\[S(\d+)\]\s*(\S+)", re.MULTILINE)
URL = re.compile(r"https?://\S+")
SECRETS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}"),
]


def extract_source_urls(artifact_text: str) -> list[str]:
    """URLs from the `## Sources` section, in order of appearance."""
    _, sources_block = _split_sources(artifact_text)
    return [m.group(0) for m in URL.finditer(sources_block)]


def _split_sources(text: str) -> tuple[str, str]:
    head, sep, tail = text.partition("## Sources")
    return head, tail if sep else ""


def run_deterministic(root: Path, manifest: CriteriaManifest) -> StageResult:
    """Run all deterministic checks; FAIL on the first class of violations."""
    findings: list[Finding] = []
    artifact = root / manifest.artifact

    if not str(Path(manifest.artifact)).startswith("reports/"):
        findings.append(
            Finding(
                criterion_id="det/artifact-path",
                severity="major",
                evidence=f"artifact `{manifest.artifact}` is outside reports/",
            )
        )
    if not artifact.is_file():
        findings.append(
            Finding(
                criterion_id="det/artifact-missing",
                severity="major",
                evidence=f"artifact `{manifest.artifact}` does not exist",
            )
        )
        return StageResult(
            stage="deterministic", verdict=VerdictKind.FAIL, findings=findings
        )

    text = artifact.read_text()
    body, sources_block = _split_sources(text)
    defined = {m.group(1) for m in SOURCE_LINE.finditer(sources_block)}
    used = set(CITATION.findall(body))

    for marker in sorted(used - defined):
        findings.append(
            Finding(
                criterion_id="det/citation-undefined",
                severity="major",
                evidence=f"[S{marker}] cited in text but missing in ## Sources",
            )
        )
    for marker in sorted(defined - used):
        findings.append(
            Finding(
                criterion_id="det/source-unused",
                severity="minor",
                evidence=f"[S{marker}] listed in ## Sources but never cited",
            )
        )
    for pattern in SECRETS:
        for m in pattern.finditer(text):
            findings.append(
                Finding(
                    criterion_id="det/secret",
                    severity="major",
                    evidence=f"possible secret: `{m.group(0)[:24]}…`",
                )
            )

    failed = any(f.severity == "major" for f in findings)
    return StageResult(
        stage="deterministic",
        verdict=VerdictKind.FAIL if failed else VerdictKind.PASS,
        findings=findings,
        detail=f"{len(findings)} finding(s)",
    )
