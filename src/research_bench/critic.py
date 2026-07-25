"""LLM critic stage: separate agent invocation with pinned identity."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .criteria import CriteriaManifest
from .verdict import Finding, StageResult, VerdictKind

Runner = Callable[..., "subprocess.CompletedProcess[str]"]


class CriticConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claude_command: str
    model: str
    prompt_path: str
    prompt_version: str
    cost_cap_usd: float
    timeout_seconds: int
    critic_version: str


class _CriterionVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion_id: str
    passed: bool
    findings: list[Finding] = Field(default_factory=list)


class _CriticOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criteria: list[_CriterionVerdict]


class _StrictFinding(BaseModel):
    """Same shape as `Finding`, but `author_feedback` is required.

    Used ONLY to build the `--json-schema` string passed to the pinned
    `claude` CLI (native structured-output enforcement, §4 of the task
    brief) so the model is forced to emit `author_feedback` on every
    finding. Parsing/validation of whatever comes back still goes through
    the lenient `_CriticOutput`/`Finding` (default `author_feedback=""`),
    so a fence-backstop response that happens to omit it still parses.
    """

    model_config = ConfigDict(extra="forbid")

    criterion_id: str
    severity: Literal["info", "minor", "major"]
    evidence: str
    author_feedback: str


class _StrictCriterionVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion_id: str
    passed: bool
    findings: list[_StrictFinding] = Field(default_factory=list)


class _StrictCriticOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criteria: list[_StrictCriterionVerdict]


CRITIC_OUTPUT_JSON_SCHEMA: str = json.dumps(_StrictCriticOutput.model_json_schema())
"""JSON Schema (as a string) passed to `claude --json-schema` for native
structured-output enforcement. Requires `author_feedback` on every finding."""


def load_critic_config(path: Path) -> CriticConfig:
    """Load the pinned critic identity from bench.config.yaml."""
    data = yaml.safe_load(path.read_text())
    return CriticConfig.model_validate(data["critic"])


def build_prompt(template: str, manifest: CriteriaManifest, artifact_text: str) -> str:
    """Fill the prompt template; the artifact is wrapped as data.

    Placeholders (``{criteria_block}`` and ``{artifact}``) are replaced
    literally via ``str.replace``, not ``str.format``, so any other braces
    in the template or artifact text (e.g. JSON examples) are left intact.
    """
    criteria_block = "\n".join(f"- {c.id}: {c.description}" for c in manifest.criteria)
    return template.replace("{criteria_block}", criteria_block).replace(
        "{artifact}", artifact_text
    )


def _error(detail: str) -> StageResult:
    return StageResult(stage="critic", verdict=VerdictKind.ERROR, detail=detail)


def _strip_fences(text: str) -> str:
    """Strip a single leading/trailing markdown code fence if present."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 2 and lines[-1].strip() == "```":
            return "\n".join(lines[1:-1])
    return stripped


def run_critic(
    config: CriticConfig,
    root: Path,
    manifest: CriteriaManifest,
    artifact_text: str,
    runner: Runner = subprocess.run,
) -> tuple[StageResult, str]:
    """Invoke the pinned critic CLI; infra problems are ERROR, never FAIL."""
    template = (root / config.prompt_path).read_text()
    prompt = build_prompt(template, manifest, artifact_text)
    try:
        proc = runner(
            [
                config.claude_command,
                "-p",
                prompt,
                "--output-format",
                "json",
                "--model",
                config.model,
                "--json-schema",
                CRITIC_OUTPUT_JSON_SCHEMA,
            ],
            capture_output=True,
            text=True,
            timeout=config.timeout_seconds,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return _error(f"critic invocation failed: {exc}"), ""

    raw = proc.stdout
    if proc.returncode != 0:
        return _error(f"critic CLI exit {proc.returncode}"), raw

    try:
        envelope = json.loads(raw)
        if not isinstance(envelope, dict):
            raise TypeError("envelope is not an object")
        cost = float(envelope.get("total_cost_usd", 0.0))
        # Native structured output (`--json-schema`) is authoritative when the
        # CLI provides it: `structured_output` is already schema-validated by
        # the CLI itself. Otherwise fall back to the fence-tolerant parse of
        # `result` (PR #4 backstop) -- belt and suspenders, both tested.
        structured = envelope.get("structured_output")
        if isinstance(structured, dict):
            output = _CriticOutput.model_validate(structured)
        else:
            result_text = envelope["result"]
            if not isinstance(result_text, str):
                raise TypeError("result is not a string")
            output = _CriticOutput.model_validate(
                json.loads(_strip_fences(result_text))
            )
    except (
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
        ValidationError,
    ) as exc:
        return _error(f"invalid critic output: {exc}"), raw

    if cost > config.cost_cap_usd:
        return _error(f"cost {cost} exceeds cap {config.cost_cap_usd}"), raw

    known_ids = {c.id for c in manifest.criteria}
    seen_ids = {c.criterion_id for c in output.criteria}
    if seen_ids != known_ids:
        return _error(
            f"criterion ids mismatch: got {sorted(seen_ids)}, "
            f"expected {sorted(known_ids)}"
        ), raw

    findings = [f for c in output.criteria for f in c.findings]
    failed = [c.criterion_id for c in output.criteria if not c.passed]
    return (
        StageResult(
            stage="critic",
            verdict=VerdictKind.FAIL if failed else VerdictKind.PASS,
            findings=findings,
            detail=(
                f"{len(failed)} of {len(output.criteria)} criteria failed"
                if failed
                else f"all {len(output.criteria)} criteria passed"
            ),
        ),
        raw,
    )
