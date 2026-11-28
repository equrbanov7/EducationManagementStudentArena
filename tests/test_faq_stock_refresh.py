import io
import json
from unittest.mock import Mock
from urllib.error import HTTPError

import pytest

from scripts.deploy import refresh_faq_stock_urls as refresh


@pytest.mark.parametrize("declared_size,valid", [(12, True), (13, False)])
def test_one_byte_probe_checks_pinned_size_without_forwarding_credentials(monkeypatch, declared_size, valid):
    location = "https://release-assets.githubusercontent.com/dummy?signature=fixture"
    redirect = HTTPError("https://api.github.com", 302, "", {"Location": location}, io.BytesIO())
    probe = io.BytesIO(b"x")
    probe.status = 206
    probe.headers = {"Content-Range": "bytes 0-0/12"}
    opener = Mock()
    opener.open.side_effect = [redirect, probe]
    monkeypatch.setattr(refresh, "build_opener", lambda handler: opener)
    package = {"asset_id": 21, "encrypted": {"size": declared_size}}
    if valid:
        assert refresh.verified_link("test/repo", "fixture", package) == location
    else:
        with pytest.raises(RuntimeError, match="did not serve"):
            refresh.verified_link("test/repo", "fixture", package)
    cdn = opener.open.call_args.args[0]
    assert cdn.full_url == location
    assert cdn.get_header("Range") == "bytes=0-0"
    assert not cdn.has_header("Authorization")


def test_supplement_failure_preserves_existing_environment_secrets(monkeypatch, tmp_path):
    manifest = tmp_path / "stock.json"
    manifest.write_text(json.dumps({"asset_id": 21, "supplements": [{"asset_id": 22}]}))
    monkeypatch.setattr(refresh, "MANIFEST", manifest)
    monkeypatch.setattr(refresh.subprocess, "check_output", Mock(side_effect=["test/repo", "fixture"]))
    write = Mock()
    monkeypatch.setattr(refresh.subprocess, "run", write)
    monkeypatch.setattr(refresh, "verified_link", Mock(side_effect=["base-dummy", RuntimeError("expired")]))
    with pytest.raises(RuntimeError, match="expired"):
        refresh.main()
    write.assert_not_called()
