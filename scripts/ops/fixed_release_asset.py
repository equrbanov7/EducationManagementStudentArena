"""Bounded encrypted release download using stdlib HTTPS, without a gh binary.

Tokens go only to api.github.com. Storage redirects are HTTPS allowlisted and
never receive Authorization; caller-pinned ciphertext SHA is checked before
an atomic private file becomes available to the decryptor.
"""

import hashlib
import json
import os
import re
import ssl
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener

API = "https://api.github.com"
REPOSITORY = "equrbanov7/EducationManagementStudentArena"
STORAGE_HOSTS = {"release-assets.githubusercontent.com", "objects.githubusercontent.com"}
MAX_METADATA = 1024 * 1024
TIMEOUT = 20
DEADLINE = 60


def _https(url, hosts):
    try:
        parts = urlsplit(url)
        valid = (
            parts.scheme == "https"
            and parts.hostname in hosts
            and parts.username is None
            and parts.password is None
            and parts.port in (None, 443)
            and not parts.fragment
        )
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("release_redirect_refused")


class _StorageRedirect(HTTPRedirectHandler):
    def __init__(self, storage):
        self.storage = storage
        self.count = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not self.storage or self.count >= 3:
            raise ValueError("release_redirect_refused")
        _https(newurl, STORAGE_HOSTS)
        self.count += 1
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is None:
            raise ValueError("release_redirect_refused")
        for mapping in (redirected.headers, redirected.unredirected_hdrs):
            for name in tuple(mapping):
                if name.lower() in {"authorization", "cookie", "proxy-authorization"}:
                    del mapping[name]
        return redirected


def _get(url, token, cap, *, storage, deadline):
    opener = build_opener(
        ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context()), _StorageRedirect(storage)
    )
    request = Request(
        url,
        headers={
            "Accept": "application/octet-stream" if storage else "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "EMSArena-fixed-encrypted-source",
        },
    )
    request.add_unredirected_header("Authorization", "Bearer " + token)
    try:
        with opener.open(request, timeout=TIMEOUT) as response:
            final = response.geturl()
            if final != url:
                if not storage:
                    raise ValueError("release_redirect_refused")
                _https(final, STORAGE_HOSTS)
            if response.status != 200:
                raise ValueError("release_http_refused")
            length = response.headers.get("Content-Length")
            if length is not None and (not re.fullmatch(r"[0-9]+", length) or int(length) > cap):
                raise ValueError("release_response_budget")
            chunks, total = [], 0
            while True:
                if time.monotonic() > deadline:
                    raise ValueError("release_transport_timeout")
                chunk = response.read(min(65536, cap + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > cap:
                    raise ValueError("release_response_budget")
            return b"".join(chunks)
    except HTTPError as exc:
        if exc.code in (401, 403):
            raise ValueError("release_access_denied") from None
        if exc.code == 404:
            raise ValueError("release_asset_missing") from None
        raise ValueError("release_http_refused") from None
    except (URLError, OSError):
        raise ValueError("release_transport_failed") from None


def download(*, repo, tag, asset, target, sha256, max_bytes, token):
    if (
        repo != REPOSITORY
        or not isinstance(tag, str)
        or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,100}", tag)
        or not isinstance(asset, str)
        or not re.fullmatch(r"[a-z0-9][a-z0-9.-]{0,120}\.enc", asset)
        or not isinstance(sha256, str)
        or not re.fullmatch(r"[a-f0-9]{64}", sha256)
        or type(max_bytes) is not int
        or not 0 < max_bytes <= 16 * 1024 * 1024
    ):
        raise ValueError("release_fixed_scope_required")
    # Installation/JWT credentials can contain punctuation; validate header safety,
    # not a particular GitHub token prefix. Never log or normalize the credential.
    if not isinstance(token, str) or not 1 <= len(token) <= 4096 or not re.fullmatch(r"[A-Za-z0-9._~+/-]+=*", token):
        raise ValueError("release_token_required")
    if target.exists() or target.is_symlink() or not target.parent.is_dir() or target.parent.stat().st_mode & 0o077:
        raise ValueError("release_private_target_required")
    deadline = time.monotonic() + DEADLINE
    raw = _get(
        f"{API}/repos/{repo}/releases/tags/{quote(tag, safe='')}", token, MAX_METADATA, storage=False, deadline=deadline
    )
    try:
        metadata = json.loads(raw)
    except ValueError:
        raise ValueError("release_metadata_invalid") from None
    if (
        not isinstance(metadata, dict)
        or metadata.get("tag_name") != tag
        or metadata.get("draft") is not False
        or not isinstance(metadata.get("assets"), list)
        or len(metadata["assets"]) > 200
    ):
        raise ValueError("release_metadata_invalid")
    selected = [row for row in metadata["assets"] if isinstance(row, dict) and row.get("name") == asset]
    if len(selected) != 1:
        raise ValueError("release_asset_missing")
    selected = selected[0]
    if (
        type(selected.get("id")) is not int
        or selected["id"] <= 0
        or type(selected.get("size")) is not int
        or not 0 < selected["size"] <= max_bytes
        or selected.get("state") != "uploaded"
    ):
        raise ValueError("release_metadata_invalid")
    # Ignore all metadata-supplied URLs: construct the numeric fixed-repo API URL.
    raw = _get(
        f"{API}/repos/{repo}/releases/assets/{selected['id']}", token, max_bytes, storage=True, deadline=deadline
    )
    if len(raw) != selected["size"] or hashlib.sha256(raw).hexdigest() != sha256:
        raise ValueError("release_ciphertext_changed")
    temporary = target.with_name(target.name + ".download")
    try:
        with temporary.open("xb") as stream:
            os.chmod(temporary, 0o600)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        directory = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)
    return target
