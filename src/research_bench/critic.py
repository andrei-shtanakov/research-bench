"""LLM critic stage: separate agent invocation with pinned identity."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

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
    findings: list[Finding] = []


class _CriticOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criteria: list[_CriterionVerdict]


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
        output = _CriticOutput.model_validate(json.loads(envelope["result"]))
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
