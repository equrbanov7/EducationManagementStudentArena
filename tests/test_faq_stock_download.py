"""Exercise the private FAQ asset handshake with urllib redirect handling and a fake TLS transport."""

import io
import socket
import traceback
from email.message import Message
from urllib.parse import parse_qs, urlsplit
from urllib.request import HTTPSHandler, ProxyHandler, build_opener
from urllib.response import addinfourl

import pytest

from scripts.deploy import install_faq_stock as installer

CDN = "https://release-assets.githubusercontent.com"
FIRST = CDN + "/first?sig=synthetic-sensitive-value"
FRESH = CDN + "/fresh?sig=fresh-synthetic-value"
FALLBACK = CDN + "/fallback?sig=fallback-synthetic-value"
TOKEN = "synthetic-api-token"


class FakeHTTPS(HTTPSHandler):
    def __init__(self):
        super().__init__()
        self.replies = []
        self.requests = []

    def https_open(self, request):
        self.requests.append(request)
        code, location = self.replies.pop(0)
        headers = Message()
        if location:
            headers["Location"] = location
        response = addinfourl(io.BytesIO(b"package"), headers, request.full_url, code)
        response.msg = "mock response"
        return response


@pytest.fixture
def https(monkeypatch):
    transport = FakeHTTPS()
    monkeypatch.setattr(socket, "create_connection", lambda *args, **kwargs: pytest.fail("Unexpected network access"))
    monkeypatch.setenv("GH_TOKEN", TOKEN)
    monkeypatch.setattr(installer, "build_opener", lambda redirect: build_opener(ProxyHandler({}), redirect, transport))
    return transport


def api_requests(transport):
    return [request for request in transport.requests if urlsplit(request.full_url).hostname == "api.github.com"]


def test_api_can_stream_without_a_redirect(https):
    https.replies = [(200, None)]
    with installer.signed_download("org/repo", 7, FALLBACK) as response:
        assert response.read() == b"package"
    (request,) = https.requests
    assert request.get_header("Authorization") == "Bearer " + TOKEN
    assert "Authorization" not in request.headers
    assert urlsplit(request.full_url).path == "/repos/org/repo/releases/assets/7"


@pytest.mark.parametrize("stale_status", [403, 404, 618])
def test_cached_storage_redirect_is_refreshed_once(https, stale_status):
    https.replies = [(302, FIRST), (stale_status, None), (302, FRESH), (302, "/final"), (200, None)]
    with installer.signed_download("org/repo", 7, FALLBACK) as response:
        assert response.read() == b"package"
    api = api_requests(https)
    assert len(api) == 2
    assert len({parse_qs(urlsplit(request.full_url).query)["nonce"][0] for request in api}) == 2
    assert all(request.get_header("Authorization") == "Bearer " + TOKEN for request in api)
    storage = [request for request in https.requests if request not in api]
    assert [request.full_url for request in storage] == [FIRST, FRESH, CDN + "/final"]
    assert all(request.get_header("Authorization") is None for request in storage)


@pytest.mark.parametrize("api_status", [403, 404])
def test_unavailable_api_uses_only_this_assets_production_fallback(https, api_status, monkeypatch):
    monkeypatch.setenv("FAQ_STOCK_DOWNLOAD_URL", FIRST)
    https.replies = [(api_status, None), (200, None)]
    with installer.signed_download("org/repo", 7, FALLBACK) as response:
        assert response.read() == b"package"
    assert len(https.requests) == 2
    assert https.requests[1].full_url == FALLBACK
    assert https.requests[1].get_header("Authorization") is None


def test_expired_api_response_retries_with_new_query_then_uses_fallback(https):
    https.replies = [(618, None), (618, None), (200, None)]
    with installer.signed_download("org/repo", 7, FALLBACK) as response:
        assert response.read() == b"package"
    first, second = api_requests(https)
    assert first.full_url != second.full_url
    assert https.requests[-1].full_url == FALLBACK


@pytest.mark.parametrize("status", [403, 404, 618])
def test_expired_production_fallback_gives_operator_action_without_disclosing_urls(https, status):
    https.replies = [(403, None), (status, None)]
    with pytest.raises(RuntimeError, match=rf"asset 7.*HTTP {status}.*refresh_faq_stock_urls") as error:
        installer.signed_download("org/repo", 7, FALLBACK)
    assert [request.full_url for request in https.requests[1:]] == [FALLBACK]
    report = "".join(traceback.format_exception(error.value))
    for sensitive in (FALLBACK, "fallback-synthetic-value", TOKEN):
        assert sensitive not in report


def test_retry_is_bounded_if_both_api_signatures_have_expired(https):
    https.replies = [(302, FIRST), (618, None), (302, FRESH), (618, None)]
    with pytest.raises(RuntimeError, match="HTTP 618.*No production fallback"):
        installer.signed_download("org/repo", 7)
    assert len(api_requests(https)) == 2
    assert not https.replies


def test_fallback_can_rescue_two_stale_api_signatures(https):
    https.replies = [(302, FIRST), (618, None), (302, FRESH), (618, None), (200, None)]
    with installer.signed_download("org/repo", 7, FALLBACK) as response:
        assert response.read() == b"package"
    assert [request.full_url for request in https.requests[1::2]] == [FIRST, FRESH]
    assert https.requests[-1].full_url == FALLBACK
    assert https.requests[-1].get_header("Authorization") is None


@pytest.mark.parametrize("status", [403, 404])
def test_unavailable_asset_without_fallback_reports_api_status(https, status):
    https.replies = [(status, None)]
    with pytest.raises(RuntimeError, match=rf"HTTP {status}.*No production fallback"):
        installer.signed_download("org/repo", 7)
    assert len(https.requests) == 1


@pytest.mark.parametrize(
    "unexpected", ["https://other.example.invalid/file", "http://release-assets.githubusercontent.com/file"]
)
def test_storage_redirect_chain_enforces_https_allowlist(https, unexpected):
    https.replies = [(302, FIRST), (302, unexpected)]
    with pytest.raises(RuntimeError, match="Unexpected release download host"):
        installer.signed_download("org/repo", 7)
    assert len(https.requests) == 2
    assert https.requests[1].get_header("Authorization") is None


def test_fallback_and_api_locations_are_validated_before_fetch(https):
    unexpected = "https://other.example.invalid/file"
    https.replies = [(302, unexpected), (404, None)]
    with pytest.raises(RuntimeError, match="Unexpected release download host"):
        installer.signed_download("org/repo", 7)
    with pytest.raises(RuntimeError, match="Unexpected release download host"):
        installer.signed_download("org/repo", 7, unexpected)
    assert len(https.requests) == len(api_requests(https)) == 2
