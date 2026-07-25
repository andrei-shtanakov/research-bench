"""bench-verify: run verification stages and always persist the verdict."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from .checks import extract_source_urls, run_deterministic
from .criteria import CriteriaManifest, load_criteria
from .critic import CriticConfig, load_critic_config, run_critic
from .links import run_link_resolve
from .verdict import (
    EXIT_CODES,
    Finding,
    Stage,
    StageResult,
    VerdictDocumentV2,
    VerdictIdentityV2,
    VerdictKind,
    VerdictReport,
    allocate_attempt,
    finding_to_v2,
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


# The five Maestro echo-env vars a v2 invocation MUST supply. The
# workstream_id/rework_attempt pair shipped in Maestro PR #106 (merged);
# fail-closed identity, never guessed.
ECHO_ENV_VARS: tuple[str, ...] = (
    "MAESTRO_PROFILE_SHA256",
    "MAESTRO_VERIFIED_SOURCE_COMMIT",
    "MAESTRO_VERIFIED_SOURCE_TREE",
    "MAESTRO_WORKSTREAM_ID",
    "MAESTRO_REWORK_ATTEMPT",
)


def _read_echo_env() -> tuple[dict[str, str], list[str]]:
    """Read the five Maestro echo-env vars; report which are missing/blank.

    Returns the raw string values (keyed by var name) plus the list of var
    names that are absent or empty/whitespace-only. Fail-closed: every var
    is required, no defaults.
    """
    values = {name: os.environ.get(name, "") for name in ECHO_ENV_VARS}
    missing = [name for name in ECHO_ENV_VARS if not values[name].strip()]
    return values, missing


def _build_v2_document(
    *,
    verification_run_id: str,
    attempt: int,
    rework_attempt: int,
    workstream_id: str,
    artifact_rel: str,
    artifact_sha256: str,
    criteria_sha256: str,
    profile_sha256: str,
    verified_source_commit: str,
    verified_source_tree: str,
    verdict: VerdictKind,
    findings: list[Finding],
) -> tuple[VerdictDocumentV2, str]:
    """Build a `VerdictDocumentV2`; degrade instead of raising when invalid.

    Guards against a construction-time `ValidationError` so the
    always-write guarantee can never be skipped by a crash from a
    malformed CLI arg. The vendored schema is the contract, not our
    pydantic mirror: its
    `verification_attempt.minimum` is `1` (checked directly against
    `contracts/maestro-verdict-v2/verdict_v2.json`), matching this
    model's `ge=1` -- an out-of-range `--attempt` (e.g. `0` or negative)
    is clamped to `1` on a retry, and the real value is named in the
    returned reason string (empty if no degradation was needed). If the
    retry itself still fails, the `ValidationError` propagates to the
    caller's own try/except, whose "failed to write verdict" branch is
    the absolute last resort.

    `findings` are the stage-collected v1-shaped `Finding`s (deterministic +
    link-resolve + critic), translated to the v2 shape via `finding_to_v2`
    -- this is what closes Task 3's `findings=[]` deferral: a FAIL verdict
    now always carries the findings that produced it.
    """
    findings_v2 = [finding_to_v2(f) for f in findings]

    def _identity(resolved_attempt: int) -> VerdictIdentityV2:
        return VerdictIdentityV2(
            verification_run_id=verification_run_id,
            verification_attempt=resolved_attempt,
            rework_attempt=rework_attempt,
            workstream_id=workstream_id,
            artifact=artifact_rel,
            artifact_sha256=artifact_sha256,
            criteria_sha256=criteria_sha256,
            profile_sha256=profile_sha256,
            verified_source_commit=verified_source_commit,
            verified_source_tree=verified_source_tree,
        )

    try:
        document = VerdictDocumentV2(
            identity=_identity(attempt), verdict=verdict, findings=findings_v2
        )
        return document, ""
    except ValidationError:
        clamped = max(attempt, 1)
        reason = f"verification_attempt={attempt} clamped to {clamped} (schema minimum)"
        document = VerdictDocumentV2(
            identity=_identity(clamped), verdict=verdict, findings=findings_v2
        )
        return document, reason


def _write_v2_identity_error(
    *,
    root: Path,
    artifact_rel: str,
    criteria_path: Path,
    out_path: Path,
    verification_run_id: str,
    attempt: int,
    reasons: list[str],
) -> int:
    """Fail-closed ERROR document: a Maestro echo-env var is absent/invalid.

    Never guesses identity: echo-env-sourced fields (profile/commit/tree/
    workstream/rework_attempt) are left at their safe zero value, but
    independently-derivable fields (run id, attempt, artifact path, its
    sha256, criteria sha256) stay real -- they are not fabricated, and
    keeping them aids debugging. The vendored schema has no free-text
    reason field, so the reason naming the missing/invalid var(s) is
    surfaced on stderr only; `findings` and `.raw.txt` stay empty (no
    critic ran), consistent with v1's "critic didn't run" semantics.
    Document construction happens inside this function's own try, so a
    construction-time crash (see `_build_v2_document`) can never leave
    `--out` without a document.
    """
    try:
        document, degrade_reason = _build_v2_document(
            verification_run_id=verification_run_id,
            attempt=attempt,
            rework_attempt=0,
            workstream_id="",
            artifact_rel=artifact_rel,
            artifact_sha256=sha256_file(root / artifact_rel),
            criteria_sha256=sha256_file(criteria_path),
            profile_sha256="",
            verified_source_commit="",
            verified_source_tree="",
            verdict=VerdictKind.ERROR,
            findings=[],
        )
        all_reasons = [*reasons, *([degrade_reason] if degrade_reason else [])]
        reason = "; ".join(all_reasons)
        write_v2_report(document, out_path, raw_output="")
        print(f"bench-verify: ERROR -> {out_path} ({reason})", file=sys.stderr)
    except Exception as exc:  # writing the verdict itself failed
        print(f"bench-verify: failed to write verdict: {exc}", file=sys.stderr)
    return EXIT_CODES[VerdictKind.ERROR]


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

    Fail-closed identity (five-var echo-env contract, controller decision
    superseding Task 2's stubs): `workstream_id` and `rework_attempt` are
    now sourced from `MAESTRO_WORKSTREAM_ID`/`MAESTRO_REWORK_ATTEMPT`
    (mirroring `profile_sha256`/`verified_source_commit`/
    `verified_source_tree`'s existing `MAESTRO_*` echo vars). If ANY of
    the five is missing/blank, or `rework_attempt` fails to parse as an
    int, the pipeline never runs -- an ERROR document is written
    immediately and this returns exit 2 with `findings=[]` (no stage ran).
    Otherwise `findings` is the deterministic + link-resolve + critic
    stages' findings, translated v1 `Finding` -> v2 `Finding` via
    `finding_to_v2` (Task 4: the critic now authors `author_feedback` on
    every finding; deterministic/link findings carry machine-authored
    `author_feedback` text from their own call sites).
    """
    env_values, missing = _read_echo_env()
    rework_attempt = 0
    if not missing:
        try:
            rework_attempt = int(env_values["MAESTRO_REWORK_ATTEMPT"])
        except ValueError:
            missing = ["MAESTRO_REWORK_ATTEMPT"]
        else:
            if rework_attempt < 0:
                missing = ["MAESTRO_REWORK_ATTEMPT"]
                rework_attempt = 0

    if missing:
        reasons = [f"{name} missing/invalid" for name in missing]
        return _write_v2_identity_error(
            root=root,
            artifact_rel=artifact_rel,
            criteria_path=criteria_path,
            out_path=out_path,
            verification_run_id=verification_run_id,
            attempt=attempt,
            reasons=reasons,
        )

    workstream_id = env_values["MAESTRO_WORKSTREAM_ID"]
    profile_sha256 = env_values["MAESTRO_PROFILE_SHA256"]
    verified_source_commit = env_values["MAESTRO_VERIFIED_SOURCE_COMMIT"]
    verified_source_tree = env_values["MAESTRO_VERIFIED_SOURCE_TREE"]

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
            document, degrade_reason = _build_v2_document(
                verification_run_id=verification_run_id,
                attempt=attempt,
                rework_attempt=rework_attempt,
                workstream_id=workstream_id,
                artifact_rel=artifact_rel,
                artifact_sha256=sha256_file(root / artifact_rel),
                criteria_sha256=sha256_file(criteria_path),
                profile_sha256=profile_sha256,
                verified_source_commit=verified_source_commit,
                verified_source_tree=verified_source_tree,
                verdict=verdict,
                findings=[f for s in stages for f in s.findings],
            )
            write_v2_report(document, out_path, raw_output)
            suffix = f" ({degrade_reason})" if degrade_reason else ""
            print(f"bench-verify: {verdict} -> {out_path}{suffix}", file=sys.stderr)
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
