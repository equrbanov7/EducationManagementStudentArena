"""İdxal stash-ının storage qatı — token, bundle adları, oxuma/silmə, scope.

W3 2026-09-14: ``import_media.py`` 600 sətir tavanında idi; DOCX bundle
dispatch-i üçün yer açmaq məqsədilə storage köməkçiləri bura köçürüldü.
``import_media`` bunları re-export edir (mövcud import yolları və testlərin
``patch("apps.exams.services.import_media.…")`` hədəfləri dəyişmir).
"""

from __future__ import annotations

import hmac
import json
import logging
import posixpath
import re
from collections.abc import Mapping

from django.core.exceptions import PermissionDenied
from django.core.files.storage import default_storage

logger = logging.getLogger(__name__)

IMPORT_SUBDIR = "question_imports"
SOURCE_NAME = "source.pdf"
MANIFEST_NAME = "manifest.json"
_TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")


def valid_token(token: object) -> bool:
    return isinstance(token, str) and bool(_TOKEN_RE.fullmatch(token))


def prefix(token: str) -> str:
    if not valid_token(token):
        raise ValueError("İdxal token-i yanlışdır")
    return posixpath.join(IMPORT_SUBDIR, token)


def bundle_name(token: str, filename: str) -> str:
    return posixpath.join(prefix(token), filename)


def read_upload(uploaded_file) -> bytes:
    try:
        original_position = uploaded_file.tell()
    except (AttributeError, OSError):
        original_position = None
    try:
        try:
            uploaded_file.seek(0)
        except (AttributeError, OSError):
            pass
        data = uploaded_file.read()
    finally:
        if original_position is not None:
            try:
                uploaded_file.seek(original_position)
            except (AttributeError, OSError):
                pass
    if not isinstance(data, bytes) or not data:
        raise ValueError("Vizual mənbə məlumatı boşdur")
    return data


def metadata_id(value: object) -> int | str | None:
    if value is None:
        return None
    value = getattr(value, "pk", value)
    if isinstance(value, (int, str)):
        return value
    return str(value)


def read_storage(name: str) -> bytes:
    with default_storage.open(name, "rb") as handle:
        data = handle.read()
    if not isinstance(data, bytes):
        raise ValueError(f"Storage binary məlumat qaytarmadı: {name}")
    return data


def load_raw_manifest(token: str) -> dict[str, object]:
    """``manifest.json``-u növ yoxlamasız oxu (dispatch üçün ``kind`` lazımdır)."""

    raw = read_storage(bundle_name(token, MANIFEST_NAME))
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("İdxal manifesti oxunmur") from exc
    if not isinstance(manifest, dict):
        raise ValueError("İdxal manifesti obyekt deyil")
    return manifest


def assert_manifest_scope(
    manifest: Mapping[str, object],
    *,
    owner_id: object = None,
    organization_id: object = None,
) -> None:
    source = manifest.get("source")
    if not isinstance(source, Mapping):
        raise ValueError("İdxal source metadata-sı yanlışdır")
    for key, expected in (
        ("owner_id", metadata_id(owner_id)),
        ("organization_id", metadata_id(organization_id)),
    ):
        if expected is None:
            continue
        actual = source.get(key)
        if actual is None or not hmac.compare_digest(str(actual), str(expected)):
            raise PermissionDenied(f"İdxal manifestinin {key} scope-u uyğun deyil")


def delete_name(name: str) -> None:
    try:
        default_storage.delete(name)
    except Exception as exc:  # pragma: no cover - backend outage
        logger.warning("İdxal stash obyekti silinmədi (%s): %s", name, exc)


def delete_tree(prefix_name: str, *, suppress_errors: bool) -> None:
    try:
        directories, files = default_storage.listdir(prefix_name)
    except (FileNotFoundError, NotImplementedError):
        directories, files = (), ()
    except Exception:
        if not suppress_errors:
            raise
        directories, files = (), ()

    for filename in files:
        delete_name(posixpath.join(prefix_name, filename))
    for directory in directories:
        delete_tree(posixpath.join(prefix_name, directory), suppress_errors=suppress_errors)
    delete_name(prefix_name)


def clear_stash(token: str) -> None:
    """İdxal bundle-ını storage backend-dən asılı olmadan rekursiv təmizlə."""

    if not valid_token(token):
        return
    delete_name(bundle_name(token, SOURCE_NAME))
    delete_name(bundle_name(token, MANIFEST_NAME))
    delete_tree(prefix(token), suppress_errors=True)


__all__ = [
    "IMPORT_SUBDIR",
    "MANIFEST_NAME",
    "SOURCE_NAME",
    "assert_manifest_scope",
    "bundle_name",
    "clear_stash",
    "delete_name",
    "delete_tree",
    "load_raw_manifest",
    "metadata_id",
    "prefix",
    "read_storage",
    "read_upload",
    "valid_token",
]
