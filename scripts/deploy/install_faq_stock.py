"""Install the encrypted, release-pinned FAQ recordings before building the production image."""

import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tarfile
import tempfile
from http.client import HTTPException
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "apps/accounts/views/profile/faq_stock.json"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def github_asset_request(repo, asset, token):
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo) or type(asset) is not int or asset <= 0:
        raise ValueError("Invalid repository or asset")
    req = Request(
        f"https://api.github.com/repos/{repo}/releases/assets/{asset}?nonce={secrets.token_hex(16)}",
        headers={"Accept": "application/octet-stream", "Cache-Control": "no-cache"},
    )
    req.add_unredirected_header("Authorization", "Bearer " + token)
    return req


def release_asset_url(url):
    try:
        address = urlsplit(url) if isinstance(url, str) else None
    except ValueError:
        address = None
    hosts = {"release-assets.githubusercontent.com", "release-assets.githubusercontent.com:443"}
    if not address or address.scheme != "https" or address.netloc.lower() not in hosts:
        raise RuntimeError("Unexpected release download host")
    return url


def _open(opener, request, timeout):
    try:
        return opener.open(request, timeout=timeout)
    except HTTPError as exc:
        # HTTPError is also an HTTP response. Inspect its status and headers without logging its signed URL.
        return exc
    except (OSError, ValueError, HTTPException):
        raise RuntimeError("Could not reach the private FAQ download service.") from None


def _release_download(opener, url):
    for _ in range(4):
        # Create a new, unauthenticated request after validating each storage hop.
        url = release_asset_url(url)
        response = _open(opener, Request(url), timeout=90)
        if response.status not in {301, 302, 303, 307, 308}:
            return response
        with response:
            location = response.headers.get("Location")
        if not location:
            raise RuntimeError("Missing private FAQ download redirect.")
        try:
            url = urljoin(url, location)
        except ValueError:
            raise RuntimeError("Invalid private FAQ download redirect.") from None
    raise RuntimeError("Too many private FAQ download redirects.")


def signed_download(repo, asset, fallback_url=None):
    opener = build_opener(NoRedirect())
    # A cached redirect may carry an expired signature. Ask the API for a fresh one at most once.
    for _ in range(2):
        request = github_asset_request(repo, asset, os.environ["GH_TOKEN"])
        response = _open(opener, request, timeout=60)
        if response.status == 302:
            with response:
                location = response.headers.get("Location")
            response = _release_download(opener, location)
        elif response.status in {403, 404}:
            # This credential cannot resolve the asset. Use its production fallback once.
            with response:
                code = response.status
            break
        if response.status == 200:
            return response
        with response:
            code = response.status
        if code not in {403, 404, 618}:
            raise RuntimeError(f"Private FAQ download failed (HTTP {code}).")

    if fallback_url:
        response = _release_download(opener, fallback_url)
        if response.status == 200:
            return response
        with response:
            raise RuntimeError(
                f"Production FAQ fallback for asset {asset} was rejected (HTTP {response.status}). "
                "Refresh the signed URL with python3 -m scripts.deploy.refresh_faq_stock_urls."
            )
    raise RuntimeError(f"Private FAQ asset {asset} is unavailable (HTTP {code}). No production fallback is configured.")


def valid(path, entry):
    return (
        not path.is_symlink()
        and path.is_file()
        and path.stat().st_size == entry["size"]
        and digest(path) == entry["sha256"]
    )


def digest(path):
    with path.open("rb") as source:
        return (
            hashlib.file_digest(source, "sha256").hexdigest()
            if hasattr(hashlib, "file_digest")
            else stream_hash(source)
        )


def stream_hash(source):
    result = hashlib.sha256()
    for block in iter(lambda: source.read(1024 * 1024), b""):
        result.update(block)
    return result.hexdigest()


def unpack(archive, stage, expected):
    seen = set()
    with tarfile.open(archive, mode="r|") as stock:
        for item in stock:
            name = item.name
            if (
                name in seen
                or name not in expected
                or not item.isfile()
                or not re.fullmatch(r"[a-z0-9_-]+\.(mp4|vtt)", name)
                or item.size != expected[name]["size"]
            ):
                raise ValueError("Unexpected item in FAQ package")
            with stock.extractfile(item) as source, (stage / name).open("xb") as destination:
                shutil.copyfileobj(source, destination)
            if not valid(stage / name, expected[name]):
                raise ValueError("Invalid FAQ media digest")
            (stage / name).chmod(0o444)
            seen.add(name)
    if seen != set(expected):
        raise ValueError("Incomplete FAQ package")
    (stage / ".gitkeep").touch()


def fetch_package(package, work, stage, fallback):
    encrypted = work / "stock.gpg"
    archive = work / "stock.tar"
    with (
        signed_download(os.environ["GITHUB_REPOSITORY"], package["asset_id"], fallback) as response,
        encrypted.open("xb") as out,
    ):
        remaining = package["encrypted"]["size"]
        while remaining:
            block = response.read(min(remaining, 1024 * 1024))
            if not block:
                raise ValueError("Truncated FAQ release")
            out.write(block)
            remaining -= len(block)
        if response.read(1):
            raise ValueError("Oversized FAQ release")
    if not valid(encrypted, package["encrypted"]):
        raise ValueError("Wrong encrypted FAQ release")
    secret = os.environ["FAQ_STOCK_KEY"].encode()
    env = {
        key: val
        for key, val in os.environ.items()
        if key not in {"GH_TOKEN", "FAQ_STOCK_KEY", "FAQ_STOCK_DOWNLOAD_URL", "FAQ_STOCK_EXTRA_URLS"}
    }
    home = work / "gpg"
    home.mkdir(mode=0o700)
    subprocess.run(
        [
            "gpg",
            "--homedir",
            str(home),
            "--no-options",
            "--batch",
            "--pinentry-mode",
            "loopback",
            "--passphrase-fd",
            "0",
            "--output",
            str(archive),
            "--decrypt",
            str(encrypted),
        ],
        input=secret,
        env=env,
        check=True,
    )
    unpack(archive, stage, package["files"])


def install(app_dir):
    manifest = json.loads(MANIFEST.read_text())
    target = app_dir / "apps/accounts/guide_media"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        raise ValueError("Invalid FAQ media directory")
    packages = [manifest, *manifest.get("supplements", [])]
    expected_names = set()
    missing = []
    reusable = []
    for package in packages:
        files = package["files"]
        if expected_names.intersection(files) or not all(
            re.fullmatch(r"[a-z0-9_-]+\.(mp4|vtt)", name) for name in files
        ):
            raise ValueError("Invalid package inventory")
        expected_names.update(files)
        if all(valid(target / name, entry) for name, entry in files.items()):
            reusable.extend(files)
        else:
            missing.append(package)
    if not missing and target.is_dir() and {p.name for p in target.iterdir()} == expected_names | {".gitkeep"}:
        print(f"Verified {len(expected_names)} installed FAQ assets.")
        return
    # Intact bundles use hard links on the same filesystem. Only missing bundles need transfer space.
    new_bytes = sum(e["size"] for group in missing for e in group["files"].values())
    working_bytes = max((2 * group["encrypted"]["size"] for group in missing), default=0)
    if shutil.disk_usage(target.parent).free < new_bytes + working_bytes + 16 * 1024 * 1024:
        raise RuntimeError("Not enough disk space to stage the verified FAQ update")
    with tempfile.TemporaryDirectory(prefix=".faq-install-", dir=target.parent) as workdir:
        work = Path(workdir)
        stage = work / "ready"
        stage.mkdir()
        for name in reusable:
            os.link(target / name, stage / name)
        fallbacks = json.loads(os.environ.get("FAQ_STOCK_EXTRA_URLS") or "{}")
        for package in missing:
            fallback = (
                os.environ.get("FAQ_STOCK_DOWNLOAD_URL")
                if package is manifest
                else fallbacks.get(str(package["asset_id"]))
            )
            with tempfile.TemporaryDirectory(dir=work) as package_dir:
                fetch_package(package, Path(package_dir), stage, fallback)
        (stage / ".gitkeep").touch()
        previous = work / "previous"
        if target.exists():
            target.rename(previous)
        try:
            stage.rename(target)
        except OSError:
            if previous.exists():
                previous.rename(target)
            raise
    print(f"Installed and verified {len(expected_names)} private FAQ assets.")


if __name__ == "__main__":
    install(Path(sys.argv[1]).resolve(strict=True))
