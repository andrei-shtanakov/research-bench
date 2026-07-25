"""bench-verify: run verification stages and always persist the verdict."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from .checks import extract_source_urls, run_deterministic
from .criteria import CriteriaManifest, load_criteria
from .critic import CriticConfig, load_critic_config, run_critic
from .links import run_link_resolve
from .verdict import (
    EXIT_CODES,
    Stage,
    StageResult,
    VerdictDocumentV2,
    VerdictIdentityV2,
    VerdictKind,
    VerdictReport,
    allocate_attempt,
    sha256_file,
    write_report,
    write_v2_report,
)


def run_verify(root: Path, brief_dir: Path, config_path: Path) -> int:
    """Run deterministic -> link-resolve -> critic; write verdict, return exit."""
    topic = brief_dir.name
    stages: list[StageResult] = []
    raw_output = ""
    manifest: CriteriaManifest | None = None
    config: CriticConfig | None = None
    verdict: VerdictKind = VerdictKind.ERROR
    write_failed = False
    current_stage: Stage = "deterministic"

    try:
        config = load_critic_config(config_path)
        manifest = load_criteria(brief_dir / "criteria.yaml")
        artifact = root / manifest.artifact

        stages.append(run_deterministic(root, manifest))
        if stages[-1].verdict is VerdictKind.PASS:
            current_stage = "link-resolve"
            urls = extract_source_urls(artifact.read_text())
            stages.append(run_link_resolve(urls))
        if stages[-1].verdict is VerdictKind.PASS:
            current_stage = "critic"
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
                stage=current_stage,
                verdict=VerdictKind.ERROR,
                detail=f"unhandled failure: {exc}",
            )
        )
        verdict = VerdictKind.ERROR
    finally:
        try:
            artifact_rel = manifest.artifact if manifest else ""
            artifact_sha = ""
            if (
                artifact_rel
                and not Path(artifact_rel).is_absolute()
                and (root / artifact_rel)
                .resolve()
                .is_relative_to((root / "reports").resolve())
            ):
                artifact_sha = sha256_file(root / artifact_rel)
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
        except Exception as exc:  # writing the verdict itself failed
            write_failed = True
            print(f"bench-verify: failed to write verdict: {exc}", file=sys.stderr)

    if write_failed:
        return EXIT_CODES[VerdictKind.ERROR]
    return EXIT_CODES[verdict]


def run_verify_v2(
    root: Path,
    config_path: Path,
    artifact_rel: str,
    criteria_path: Path,
    out_path: Path,
    verification_run_id: str,
    attempt: int,
) -> int:
    """Run verification stages and emit a Maestro verdict-v2 document.

    Maestro owns addressing in this mode (§9 of the vendored verifier
    contract): the canonical JSON lands at EXACTLY `out_path` (atomic
    tmp+rename), with `.md`/`.raw.txt` sidecars at the same stem, all under
    `out_path.parent` only — `allocate_attempt` self-numbering is
    legacy-mode-only from now on. `criteria_path` is read verbatim (no
    `briefs/` assumption; Maestro may stage an ephemeral copy). `artifact`
    is the Maestro-authoritative, worktree-relative artifact path passed
    via `--artifact`; the loaded criteria manifest's own `artifact` field
    (a `briefs/`-era artifact) is overridden with it so the existing
    deterministic/critic stages check the same file Maestro is verifying.

    Two identity fields are stubbed pending Task 3, matching what
    Maestro's own `tests/fakes/stub_verifier.py` reference verifier does
    for fields outside the closed argv placeholder set:
    `workstream_id=""` (not one of `--artifact/--criteria/--out/
    --verification-run-id/--attempt`; a real per-workstream verifier would
    hardcode its own topic, per stub_verifier.py's comment) and
    `rework_attempt=0` (stub_verifier.py hardcodes the same). `findings` is
    always `[]`: translating v1 `Finding` -> v2 `Finding` (which requires
    `author_feedback`) is Task 3's job.
    """
    stages: list[StageResult] = []
    raw_output = ""
    verdict: VerdictKind = VerdictKind.ERROR
    current_stage: Stage = "deterministic"
    write_failed = False

    try:
        config = load_critic_config(config_path)
        manifest = load_criteria(criteria_path).model_copy(
            update={"artifact": artifact_rel}
        )
        artifact = root / artifact_rel
        stages.append(run_deterministic(root, manifest))
        if stages[-1].verdict is VerdictKind.PASS:
            current_stage = "link-resolve"
            urls = extract_source_urls(artifact.read_text())
            stages.append(run_link_resolve(urls))
        if stages[-1].verdict is VerdictKind.PASS:
            current_stage = "critic"
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
                stage=current_stage,
                verdict=VerdictKind.ERROR,
                detail=f"unhandled failure: {exc}",
            )
        )
        verdict = VerdictKind.ERROR
    finally:
        try:
            document = VerdictDocumentV2(
                identity=VerdictIdentityV2(
                    verification_run_id=verification_run_id,
                    verification_attempt=attempt,
                    rework_attempt=0,
                    workstream_id="",
                    artifact=artifact_rel,
                    artifact_sha256=sha256_file(root / artifact_rel),
                    criteria_sha256=sha256_file(criteria_path),
                    profile_sha256=os.environ.get("MAESTRO_PROFILE_SHA256", ""),
                    verified_source_commit=os.environ.get(
                        "MAESTRO_VERIFIED_SOURCE_COMMIT", ""
                    ),
                    verified_source_tree=os.environ.get(
                        "MAESTRO_VERIFIED_SOURCE_TREE", ""
                    ),
                ),
                verdict=verdict,
                findings=[],
            )
            write_v2_report(document, out_path, raw_output)
            print(f"bench-verify: {verdict} -> {out_path}", file=sys.stderr)
        except Exception as exc:  # writing the verdict itself failed
            write_failed = True
            print(f"bench-verify: failed to write verdict: {exc}", file=sys.stderr)

    if write_failed:
        return EXIT_CODES[VerdictKind.ERROR]
    return EXIT_CODES[verdict]


def main(argv: list[str] | None = None) -> int:
    """Console entrypoint.

    Legacy mode: `bench-verify --brief briefs/<topic>` (unchanged).
    v2 mode: active iff `--out` is given; Maestro then also requires
    `--artifact`, `--criteria`, `--verification-run-id`, and `--attempt` —
    a missing one is an argparse usage error (`parser.error`, exit 2). That
    exit code coincidentally equals `EXIT_CODES[VerdictKind.ERROR]`, but no
    verdict file is written in this case: it is a CLI-usage error, not a
    written ERROR verdict, and Maestro treats "no verdict file at --out" as
    its own protocol error regardless of why nothing landed.
    """
    parser = argparse.ArgumentParser(prog="bench-verify")
    parser.add_argument("--brief", help="path to briefs/<topic> (legacy mode)")
    parser.add_argument("--config", default="bench.config.yaml")
    parser.add_argument("--root", default=".")
    parser.add_argument("--artifact", help="v2: worktree-relative artifact path")
    parser.add_argument("--criteria", help="v2: explicit criteria manifest path")
    parser.add_argument(
        "--out", help="v2: exact verdict JSON path (Maestro-owned addressing)"
    )
    parser.add_argument("--verification-run-id", help="v2: Maestro verification run id")
    parser.add_argument("--attempt", type=int, help="v2: verification attempt number")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()

    if args.out is not None:
        required = {
            "--artifact": args.artifact,
            "--criteria": args.criteria,
            "--verification-run-id": args.verification_run_id,
            "--attempt": args.attempt,
        }
        missing = [name for name, value in required.items() if value is None]
        if missing:
            parser.error(
                "--out requires " + ", ".join(missing) + " (v2 invocation mode)"
            )
        return run_verify_v2(
            root=root,
            config_path=root / args.config,
            artifact_rel=args.artifact,
            criteria_path=Path(args.criteria),
            out_path=Path(args.out),
            verification_run_id=args.verification_run_id,
            attempt=args.attempt,
        )

    if args.brief is None:
        parser.error("--brief is required (legacy mode), or pass --out (v2 mode)")
    return run_verify(root, root / args.brief, root / args.config)


if __name__ == "__main__":
    sys.exit(main())
