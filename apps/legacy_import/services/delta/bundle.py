"""Delta paketi — ``legacy_delta_extract`` çıxışı, ``legacy_delta_apply`` girişi (JSON + gzip).

Paket ŞƏXSİ məlumat daşıyır (ad, ata adı, FİN, doğum tarixi) — ona görə:

* fayl HƏMİŞƏ 0600 yazılır (mövcud faylın rejimi də daraldılır);
* parol, telefon, e-poçt, kart, telegram sütunları paketə ümumiyyətlə DÜŞMÜR (çıxarışda seçilmir);
* serverə yalnız şifrəli release asset kimi gedir (``openssl enc -aes-256-cbc -pbkdf2``) — bax
  ``docs/migration/LEGACY_DELTA_2026_10.md``.

Format versiyası paketlə birlikdə yoxlanılır: naməlum versiya fail-closed rədd edilir.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os

FORMAT = "ems-legacy-delta/1"

#: Paketin MƏCBURİ bölmələri (boş siyahı ola bilər, açar olmalıdır).
SECTIONS = (
    "periods",
    "departments",
    "specialities",
    "groups",
    "subjects",
    "workers",
    "students",
    "journals",
    "lesson_dates",
    "points",
    "excuse_windows",
    "syllabi",
)


class BundleError(ValueError):
    """Paket oxuna bilmir və ya formatı tanınmır."""


def write_bundle(path: str, data: dict) -> str:
    """Paketi 0600 rejimində yaz; faylın sha256-sını qaytar."""

    missing = [name for name in SECTIONS if name not in data]
    if missing:
        raise BundleError(f"legacy_delta_bundle_sections_missing: {', '.join(missing)}")
    payload = json.dumps({"format": FORMAT, **data}, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    target = os.path.expanduser(path)
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as handle:
        handle.write(payload)
    return file_sha256(target)


def read_bundle(path: str) -> dict:
    target = os.path.expanduser(path)
    try:
        with gzip.open(target, "rb") as handle:
            data = json.loads(handle.read().decode("utf-8"))
    except (OSError, ValueError) as error:
        raise BundleError(f"legacy_delta_bundle_unreadable: {error.__class__.__name__}") from None
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise BundleError("legacy_delta_bundle_format_unknown")
    missing = [name for name in SECTIONS if not isinstance(data.get(name), list)]
    if missing:
        raise BundleError(f"legacy_delta_bundle_sections_missing: {', '.join(missing)}")
    return data


def file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(os.path.expanduser(path), "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = ["FORMAT", "SECTIONS", "BundleError", "file_sha256", "read_bundle", "write_bundle"]
