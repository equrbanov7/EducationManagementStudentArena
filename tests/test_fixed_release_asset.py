"""Fixed private release sources: no gh process and no bearer token on redirects."""

import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.request import Request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/ops"))
import fixed_release_asset as asset  # noqa: E402
import reviewed_followup  # noqa: E402


class Response(io.BytesIO):
    status = 200

    def __init__(self, raw, url, *, length=None):
        super().__init__(raw)
        self.url = url
        self.headers = {} if length is None else {"Content-Length": length}

    def geturl(self):
        return self.url


class FixedReleaseTests(unittest.TestCase):
    def metadata(self, raw=b"cipher"):
        return {
            "tag_name": "fixed-source-20261101",
            "draft": False,
            "assets": [
                {
                    "id": 12,
                    "name": "source.json.enc",
                    "state": "uploaded",
                    "size": len(raw),
                    "url": "http://untrusted.invalid/ignored",
                    "browser_download_url": "ignored",
                }
            ],
        }

    def kwargs(self, folder, raw=b"cipher"):
        return dict(
            repo=asset.REPOSITORY,
            tag="fixed-source-20261101",
            asset="source.json.enc",
            target=Path(folder) / "source.json.enc",
            sha256=hashlib.sha256(raw).hexdigest(),
            max_bytes=1024,
            token="synthetic_token_DO_NOT_LOG",
        )

    def test_exact_api_download_private_atomic_file_no_gh_or_metadata_url(self):
        requests = []
        raw = b"cipher"

        def open(request, **kwargs):
            requests.append(request)
            self.assertEqual(kwargs["timeout"], 20)
            self.assertEqual(request.get_header("Authorization"), "Bearer synthetic_token_DO_NOT_LOG")
            body = json.dumps(self.metadata()).encode() if len(requests) == 1 else raw
            return Response(body, request.full_url)

        with (
            tempfile.TemporaryDirectory() as folder,
            patch.object(asset, "build_opener", return_value=SimpleNamespace(open=open)),
        ):
            path = asset.download(**self.kwargs(folder))
            self.assertEqual(path.read_bytes(), raw)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(list(path.parent.iterdir()), [path])
        self.assertEqual(
            [r.full_url for r in requests],
            [
                f"{asset.API}/repos/{asset.REPOSITORY}/releases/tags/fixed-source-20261101",
                f"{asset.API}/repos/{asset.REPOSITORY}/releases/assets/12",
            ],
        )
        self.assertEqual(requests[1].get_header("Accept"), "application/octet-stream")

    def test_storage_redirect_removes_all_sensitive_headers_in_both_maps(self):
        request = Request(
            asset.API + "/asset",
            headers={
                "Authorization": "SECRET",
                "Cookie": "PRIVATE",
                "Proxy-Authorization": "PRIVATE",
                "Accept": "application/octet-stream",
            },
        )
        request.add_unredirected_header("Authorization", "SECRET")
        redirect = asset._StorageRedirect(True)
        redirected = redirect.redirect_request(
            request, None, 302, "Found", {}, "https://release-assets.githubusercontent.com/id?signature=opaque"
        )
        self.assertEqual(redirected.get_header("Accept"), "application/octet-stream")
        self.assertFalse(
            {name.lower() for name in dict(redirected.header_items())}
            & {"authorization", "cookie", "proxy-authorization"}
        )
        for url in (
            "http://release-assets.githubusercontent.com/id",
            "https://evil.invalid/id",
            "https://api.github.com@evil.invalid/id",
            "https://user@release-assets.githubusercontent.com/id",
            "https://release-assets.githubusercontent.com:444/id",
        ):
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, "release_redirect_refused"):
                asset._StorageRedirect(True).redirect_request(request, None, 302, "Found", {}, url)
        with self.assertRaisesRegex(ValueError, "release_redirect_refused"):
            asset._StorageRedirect(False).redirect_request(
                request, None, 302, "Found", {}, "https://objects.githubusercontent.com/id"
            )
        redirect.count = 3
        with self.assertRaisesRegex(ValueError, "release_redirect_refused"):
            redirect.redirect_request(request, None, 302, "Found", {}, "https://objects.githubusercontent.com/id")

    def test_wrong_hash_duplicate_asset_wrong_tag_or_size_never_creates_cipher(self):
        for variant in ("hash", "duplicate", "tag", "oversize", "draft", "badid"):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as folder:
                metadata = self.metadata()
                if variant == "duplicate":
                    metadata["assets"] *= 2
                elif variant == "tag":
                    metadata["tag_name"] = "other"
                elif variant == "oversize":
                    metadata["assets"][0]["size"] = 1025
                elif variant == "draft":
                    metadata["draft"] = True
                elif variant == "badid":
                    metadata["assets"][0]["id"] = "12?injection"
                responses = [json.dumps(metadata).encode(), b"wrong!"]
                with patch.object(asset, "_get", side_effect=responses):
                    with self.assertRaises(ValueError):
                        asset.download(**self.kwargs(folder))
                self.assertEqual(list(Path(folder).iterdir()), [])

    def test_response_cap_and_transport_errors_never_expose_auth_or_url(self):
        for response in (Response(b"TOO-LARGE", asset.API, length="100"), Response(b"TOO-LARGE", asset.API)):
            with patch.object(
                asset, "build_opener", return_value=SimpleNamespace(open=lambda *a, selected=response, **k: selected)
            ):
                with self.assertRaisesRegex(ValueError, "release_response_budget"):
                    asset._get(asset.API, "secret", 3, storage=False, deadline=float("inf"))
        for exc in (URLError("PRIVATE_URL_TOKEN"), HTTPError("PRIVATE_URL", 403, "SECRET", {}, None)):
            with patch.object(
                asset, "build_opener", return_value=SimpleNamespace(open=unittest.mock.Mock(side_effect=exc))
            ):
                with self.assertRaises(ValueError) as caught:
                    asset._get(asset.API, "SECRET", 3, storage=False, deadline=float("inf"))
                self.assertNotIn("PRIVATE", str(caught.exception))
                self.assertNotIn("SECRET", str(caught.exception))

    def test_missing_token_or_bad_repo_stops_before_network(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(asset, "_get") as get:
            for changed in ({"token": None}, {"token": "secret\nheader"}, {"repo": "other/repo"}, {"tag": "../escape"}):
                args = self.kwargs(folder)
                args.update(changed)
                with self.assertRaises(ValueError):
                    asset.download(**args)
            get.assert_not_called()

    def test_missing_executable_has_finite_distinct_diagnostic(self):
        with patch.object(reviewed_followup.subprocess, "run", side_effect=FileNotFoundError("private executable")):
            with self.assertRaisesRegex(ValueError, "^followup_executable_missing$") as caught:
                reviewed_followup.command(["not-installed"])
        fields = reviewed_followup.closed_diagnostics().describe(caught.exception, "capture")
        self.assertEqual(fields["guard"], "followup_executable_missing")
        self.assertNotIn("private", str(fields))


if __name__ == "__main__":
    unittest.main()


class OpaqueBearerCredentialTests(unittest.TestCase):
    def test_installation_and_jwt_punctuation_are_sent_only_to_fixed_api(self):
        fixture = FixedReleaseTests()
        for token in ("v1.synthetic-installation.token", "eyJ.synthetic_payload.signature-part", "abc+/._~-=="):
            with self.subTest(token_format="synthetic"), tempfile.TemporaryDirectory() as folder:
                received = []

                def fake_get(url, credential, cap, *, received=received, **kwargs):
                    received.append((url, credential))
                    return json.dumps(fixture.metadata()).encode() if len(received) == 1 else b"cipher"

                args = fixture.kwargs(folder)
                args["token"] = token
                with patch.object(asset, "_get", side_effect=fake_get):
                    path = asset.download(**args)
                self.assertEqual(path.read_bytes(), b"cipher")
                self.assertTrue(
                    all(url.startswith(asset.API + "/repos/" + asset.REPOSITORY + "/") for url, _ in received)
                )
                self.assertTrue(all(credential == token for _, credential in received))

    def test_header_injection_whitespace_unicode_and_unbounded_credentials_refused_before_network(self):
        fixture = FixedReleaseTests()
        for token in (None, "", "a b", "a\rb", "a\nb", "a\tb", "Bearer abc", "gizliə", "a=b", "=", "a" * 4097):
            with self.subTest(invalid_format=True), tempfile.TemporaryDirectory() as folder:
                args = fixture.kwargs(folder)
                args["token"] = token
                with (
                    patch.object(asset, "_get") as transport,
                    self.assertRaisesRegex(ValueError, "release_token_required"),
                ):
                    asset.download(**args)
                transport.assert_not_called()
