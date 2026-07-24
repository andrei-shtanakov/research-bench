"""Tests for the network link-resolve stage (ERROR vs FAIL semantics)."""

import httpx

from research_bench.links import run_link_resolve
from research_bench.verdict import VerdictKind


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_all_resolvable_passes() -> None:
    client = _client(lambda req: httpx.Response(200))
    result = run_link_resolve(["https://a.example/x"], client=client)
    assert result.verdict == VerdictKind.PASS


def test_http_404_is_content_fail() -> None:
    client = _client(lambda req: httpx.Response(404))
    result = run_link_resolve(["https://a.example/gone"], client=client)
    assert result.verdict == VerdictKind.FAIL
    assert result.findings[0].criterion_id == "det/link-dead"


def test_transport_error_is_error_not_fail() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("dns failure", request=req)

    result = run_link_resolve(["https://nope.invalid/"], client=_client(handler))
    assert result.verdict == VerdictKind.ERROR
    assert "nope.invalid" in result.detail


def test_no_urls_passes() -> None:
    result = run_link_resolve([], client=_client(lambda req: httpx.Response(200)))
    assert result.verdict == VerdictKind.PASS
