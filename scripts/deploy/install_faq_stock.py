"""Install the encrypted, release-pinned FAQ recordings before building the production image."""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "apps/accounts/views/profile/faq_stock.json"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def signed_download(repo, asset):
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo) or not isinstance(asset, int) or asset <= 0:
        raise ValueError("Invalid repository or asset")
    req = Request(
        f"https://api.github.com/repos/{repo}/releases/assets/{asset}",
        headers={"Authorization": "Bearer " + os.environ["GH_TOKEN"], "Accept": "application/octet-stream"},
    )
    try:
        return build_opener(NoRedirect()).open(req, timeout=60)
    except HTTPError as exc:
        if exc.code == 302:
            url = exc.headers["Location"]
        elif exc.code in {403, 404} and os.environ.get("FAQ_STOCK_DOWNLOAD_URL"):
            url = os.environ["FAQ_STOCK_DOWNLOAD_URL"]
        else:
            raise RuntimeError(f"GitHub declined the private stock download (HTTP {exc.code})") from None
    address = urlsplit(url)
    if address.scheme != "https" or address.hostname != "release-assets.githubusercontent.com":
        raise RuntimeError("Unexpected release download host")
    # Signed URL only. Never forward the API token to a storage host.
    return urlopen(url, timeout=90)


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


def install(app_dir):
    manifest = json.loads(MANIFEST.read_text())
    target = app_dir / "apps/accounts/guide_media"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        raise ValueError("Invalid FAQ media directory")
    expected = manifest["files"]
    if target.exists() and {p.name for p in target.iterdir() if p.name != ".gitkeep"} == set(expected):
        if all(valid(target / name, entry) for name, entry in expected.items()):
            print(f"Verified {len(expected)} installed FAQ assets.")
            return
    media_bytes = sum(entry["size"] for entry in expected.values())
    # Keep room for the downloaded package, its tar and the checked staging tree.
    required = manifest["encrypted"]["size"] + 2 * media_bytes + 16 * 1024 * 1024
    if shutil.disk_usage(target.parent).free < required:
        raise RuntimeError("Not enough disk space to stage the verified FAQ update")
    with tempfile.TemporaryDirectory(prefix=".faq-install-", dir=target.parent) as workdir:
        work = Path(workdir)
        encrypted, archive, stage = work / "stock.gpg", work / "stock.tar", work / "ready"
        stage.mkdir()
        with (
            signed_download(os.environ["GITHUB_REPOSITORY"], manifest["asset_id"]) as response,
            encrypted.open("xb") as out,
        ):
            remaining = manifest["encrypted"]["size"]
            while remaining:
                block = response.read(min(remaining, 1024 * 1024))
                if not block:
                    raise ValueError("Truncated FAQ release")
                out.write(block)
                remaining -= len(block)
            if response.read(1):
                raise ValueError("Oversized FAQ release")
        if not valid(encrypted, manifest["encrypted"]):
            raise ValueError("Wrong encrypted FAQ release")
        secret = os.environ["FAQ_STOCK_KEY"].encode()
        env = {
            key: val
            for key, val in os.environ.items()
            if key not in {"GH_TOKEN", "FAQ_STOCK_KEY", "FAQ_STOCK_DOWNLOAD_URL"}
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
        unpack(archive, stage, expected)
        previous = work / "previous"
        if target.exists():
            target.rename(previous)
        try:
            stage.rename(target)
        except OSError:
            if previous.exists():
                previous.rename(target)
            raise
    print(f"Installed and verified {len(expected)} private FAQ assets.")


if __name__ == "__main__":
    install(Path(sys.argv[1]).resolve(strict=True))
