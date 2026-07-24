"""Network link-resolve stage — isolated so its ERROR never masks content."""

from __future__ import annotations

import httpx

from .verdict import Finding, StageResult, VerdictKind


def run_link_resolve(
    urls: list[str],
    timeout_seconds: float = 10.0,
    client: httpx.Client | None = None,
) -> StageResult:
    """Resolve source URLs. Transport failure -> ERROR; HTTP>=400 -> FAIL."""
    findings: list[Finding] = []
    own_client = client or httpx.Client(timeout=timeout_seconds, follow_redirects=True)
    try:
        for url in urls:
            try:
                response = own_client.head(
                    url, timeout=timeout_seconds, follow_redirects=True
                )
                if response.status_code >= 400:
                    # Real hosts often reject HEAD (403/404/405/501) while
                    # GET works fine; only the GET verdict is authoritative.
                    response = own_client.get(
                        url, timeout=timeout_seconds, follow_redirects=True
                    )
            except httpx.HTTPError as exc:
                return StageResult(
                    stage="link-resolve",
                    verdict=VerdictKind.ERROR,
                    detail=f"transport failure resolving {url}: {exc}",
                )
            if response.status_code >= 400:
                findings.append(
                    Finding(
                        criterion_id="det/link-dead",
                        severity="major",
                        evidence=f"{url} -> HTTP {response.status_code}",
                    )
                )
    finally:
        if client is None:
            own_client.close()

    return StageResult(
        stage="link-resolve",
        verdict=VerdictKind.FAIL if findings else VerdictKind.PASS,
        findings=findings,
        detail=f"{len(urls)} url(s) checked",
    )
