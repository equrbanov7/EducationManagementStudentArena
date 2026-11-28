"""Refresh production fallback links for the private, manifest-pinned FAQ archives."""

import json
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener

from .install_faq_stock import MANIFEST, NoRedirect, github_asset_request, release_asset_url


def verified_link(repo, token, package):
    asset = int(package["asset_id"])
    metadata = github_asset_request(repo, asset, token)
    opener = build_opener(NoRedirect())
    try:
        with opener.open(metadata, timeout=30):
            raise RuntimeError("GitHub did not supply a signed download link.")
    except HTTPError as exc:
        with exc:
            if exc.code != 302:
                raise RuntimeError(f"GitHub declined access to archive {asset} (HTTP {exc.code}).") from None
            link = exc.headers.get("Location", "")
    link = release_asset_url(link)
    request = Request(link, headers={"Range": "bytes=0-0", "Accept-Encoding": "identity"})
    with opener.open(request, timeout=30) as reply:
        expected = f"bytes 0-0/{package['encrypted']['size']}"
        if reply.status != 206 or reply.headers.get("Content-Range") != expected or len(reply.read(2)) != 1:
            raise RuntimeError(f"GitHub did not serve the pinned archive {asset}.")
    return link


def main():
    repo = subprocess.check_output(
        ["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"], text=True
    ).strip()
    token = subprocess.check_output(["gh", "auth", "token", "--hostname", "github.com"], text=True).strip()
    manifest = json.loads(MANIFEST.read_text())
    base = verified_link(repo, token, manifest)
    extras = {item["asset_id"]: verified_link(repo, token, item) for item in manifest.get("supplements", [])}
    for name, value in [("FAQ_STOCK_DOWNLOAD_URL", base), ("FAQ_STOCK_EXTRA_URLS", json.dumps(extras))]:
        subprocess.run(
            ["gh", "secret", "set", name, "--env", "production", "--repo", repo], input=value, text=True, check=True
        )
    print(f"Refreshed and range-checked {len(extras) + 1} archive links for production.")


if __name__ == "__main__":
    try:
        main()
    except HTTPError as error:
        # Some errors carry the signed URL. Report the status only.
        sys.exit(f"GitHub archive validation failed (HTTP {error.code}).")
    except URLError:
        sys.exit("The GitHub archive service could not be reached.")
    except RuntimeError as error:
        sys.exit(str(error))
