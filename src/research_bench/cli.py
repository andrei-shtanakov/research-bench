"""bench-verify: run verification stages and always persist the verdict."""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from .checks import extract_source_urls, run_deterministic
from .criteria import CriteriaManifest, load_criteria
from .critic import CriticConfig, load_critic_config, run_critic
from .links import run_link_resolve
from .verdict import (
    EXIT_CODES,
    StageResult,
    VerdictKind,
    VerdictReport,
    allocate_attempt,
    sha256_file,
    write_report,
)


def run_verify(root: Path, brief_dir: Path, config_path: Path) -> int:
    """Run deterministic -> link-resolve -> critic; write verdict, return exit."""
    topic = brief_dir.name
    stages: list[StageResult] = []
    raw_output = ""
    manifest: CriteriaManifest | None = None
    config: CriticConfig | None = None
    verdict: VerdictKind = VerdictKind.ERROR

    try:
        config = load_critic_config(config_path)
        manifest = load_criteria(brief_dir / "criteria.yaml")
        artifact = root / manifest.artifact

        stages.append(run_deterministic(root, manifest))
        if stages[-1].verdict is VerdictKind.PASS:
            urls = extract_source_urls(artifact.read_text())
            stages.append(run_link_resolve(urls))
        if stages[-1].verdict is VerdictKind.PASS:
            critic_result, raw_output = run_critic(
                config, root, manifest, artifact.read_text()
            )
            stages.append(critic_result)
        verdict = next(
            (s.verdict for s in stages if s.verdict is not VerdictKind.PASS),
            VerdictKind.PASS,
        )
    except Exception as exc:  # manifest/IO problems are infra, not content
        stages.append(
            StageResult(
                stage="deterministic",
                verdict=VerdictKind.ERROR,
                detail=f"unhandled failure: {exc}",
            )
        )
        verdict = VerdictKind.ERROR
    finally:
        artifact_rel = manifest.artifact if manifest else ""
        artifact_sha = sha256_file(root / artifact_rel) if artifact_rel else ""
        verdict_dir = root / "verdicts" / topic / (artifact_sha or "no-artifact")
        attempt, reserved = allocate_attempt(verdict_dir)
        report = VerdictReport(
            verdict=verdict,
            stages=stages,
            artifact=artifact_rel,
            artifact_sha256=artifact_sha,
            criteria_sha256=sha256_file(brief_dir / "criteria.yaml"),
            critic_version=config.critic_version if config else "unknown",
            model=config.model if config else "unknown",
            prompt_version=config.prompt_version if config else "unknown",
            attempt=attempt,
            timestamp=datetime.now(UTC).isoformat(),
        )
        write_report(report, reserved, raw_output)
        print(f"bench-verify: {verdict} -> {reserved}", file=sys.stderr)

    return EXIT_CODES[verdict]


def main() -> int:
    """Console entrypoint: bench-verify --brief briefs/<topic>."""
    parser = argparse.ArgumentParser(prog="bench-verify")
    parser.add_argument("--brief", required=True, help="path to briefs/<topic>")
    parser.add_argument("--config", default="bench.config.yaml")
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    return run_verify(root, root / args.brief, root / args.config)


if __name__ == "__main__":
    sys.exit(main())
