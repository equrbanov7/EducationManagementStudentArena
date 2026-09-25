"""Təmir PLAN faylı — ağır mənbə oxunuşu LOKALDA, serverə yalnız yığcam plan gedir.

Niyə var (2026-09-25)
---------------------
Bəzi təmirlər (ilk növbədə J12 dərs bərpası) köhnə MyEdu MariaDB mənbəsini
oxumalıdır.  Production serverdə mənbə YOXDUR və production settings
``LEGACY_MARIADB_SOURCE_LOCAL_DISPOSABLE``-ı qəsdən ``False`` saxlayır — yəni
serverdə mənbə yalnız TLS-li, sertifikatı yoxlanan MariaDB ilə mümkün olardı
(2.1 GB dump-u serverə daşımaq, konteyner qurmaq, sertifikat buraxmaq).  Bunun
əvəzinə iş iki yerə bölünür:

1. **Plan (lokal)** — mənbə + production-un bərpa olunmuş ATILABİLƏN nüsxəsi
   üzərində fazanın ÖZ kodu işləyir; hədəfə düşən sətirlər plan faylına çıxarılır;
2. **Tətbiq (server)** — plan faylı sha256 ilə yoxlanılır, hər sətir CANLI
   bazaya qarşı yenidən yoxlanılır, yalnız çatışmayan sətir əlavə olunur.

Format
------
``.jsonl.gz``: hər sətir bir JSON obyektidir; birinci sətir ``header``,
sonuncu ``footer`` (növ üzrə sətir sayları).  Bayt-bəbayt deterministikdir
(``gzip`` ``mtime=0``, açarlar sıralı), ona görə eyni giriş eyni sha256 verir.
Yanında ``<fayl>.manifest.json`` yazılır (sha256 + saylar + başlıq) — operator
serverdə ``--plan-sha256`` kimi MƏHZ bu dəyəri verir.

⚠️ Fayl şəxsi akademik məlumat daşıyır (qeydiyyat UUID-ləri + ballar, ad YOX):
repoya DÜŞMÜR, ``0600`` icazə ilə yazılır, yalnız bağlı kanalla ötürülür və
tətbiqdən sonra serverdəki ehtiyat nüsxəsi ilə birlikdə saxlanılır.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Iterator

PLAN_FORMAT = "emsarena-legacy-repair-plan"
PLAN_FORMAT_VERSION = 1
_HEADER = "header"
_FOOTER = "footer"
_CHUNK = 1 << 20


class RepairPlanError(Exception):
    """Plan faylı qüsurlu və ya gözləniləndən fərqlidir — yalnız sabit kod daşıyır."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class PlanManifest:
    path: str
    sha256: str
    size_bytes: int
    counts: dict
    header: dict

    def as_dict(self) -> dict:
        return {
            "format": PLAN_FORMAT,
            "format_version": PLAN_FORMAT_VERSION,
            "plan_file": os.path.basename(self.path),
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "counts": dict(sorted(self.counts.items())),
            "header": self.header,
        }


def _line(payload: dict) -> bytes:
    return (json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_plan(path: str, *, header: dict, records: Iterable[dict]) -> PlanManifest:
    """Planı deterministik ``.jsonl.gz`` kimi yaz (0600) və manifesti yanında saxla."""

    if os.path.exists(path):
        # Köhnə planın səssiz əvəzlənməsi sha256 zəncirini qırardı.
        raise RepairPlanError("legacy_repair_plan_exists")
    counts: Counter = Counter()
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as stream:
        stream.write(_line({"kind": _HEADER, "format": PLAN_FORMAT, "format_version": PLAN_FORMAT_VERSION, **header}))
        for record in records:
            kind = record.get("kind")
            if kind in (None, _HEADER, _FOOTER):
                raise RepairPlanError("legacy_repair_plan_record_kind_invalid")
            counts[kind] += 1
            stream.write(_line(record))
        stream.write(_line({"kind": _FOOTER, "counts": dict(sorted(counts.items()))}))
    manifest = PlanManifest(
        path=path,
        sha256=file_sha256(path),
        size_bytes=os.path.getsize(path),
        counts=dict(counts),
        header=dict(header),
    )
    manifest_path = f"{path}.manifest.json"
    descriptor = os.open(manifest_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(manifest.as_dict(), handle, sort_keys=True, ensure_ascii=False, indent=2)
        handle.write("\n")
    return manifest


def _records(path: str) -> Iterator[dict]:
    with gzip.open(path, "rb") as stream:
        for raw in stream:
            try:
                payload = json.loads(raw)
            except ValueError:
                raise RepairPlanError("legacy_repair_plan_line_invalid") from None
            if not isinstance(payload, dict):
                raise RepairPlanError("legacy_repair_plan_line_invalid")
            yield payload


def _verified_sha256(path: str, expected_sha256: str) -> str:
    """Faylın sha256-sı operatorun verdiyi (manifestdəki) dəyərlə EYNİdirmi?"""

    expected = str(expected_sha256 or "").strip().lower()
    if len(expected) != 64 or any(ch not in "0123456789abcdef" for ch in expected):
        raise RepairPlanError("legacy_repair_plan_sha256_required")
    try:
        actual = file_sha256(path)
    except OSError:
        raise RepairPlanError("legacy_repair_plan_unreadable") from None
    if actual != expected:
        raise RepairPlanError("legacy_repair_plan_sha256_mismatch")
    return actual


@dataclass(frozen=True)
class LoadedPlan:
    header: dict
    records: dict  # növ → sətir siyahısı (fayl sırası)
    sha256: str

    def of(self, kind: str) -> list:
        return self.records.get(kind, [])


def read_plan(path: str, *, expected_sha256: str, repair: str) -> LoadedPlan:
    """Planı oxu: ƏVVƏL sha256, sonra format/versiya/təmir növü, sonda footer sayları."""

    actual = _verified_sha256(path, expected_sha256)
    header = None
    footer = None
    grouped: dict[str, list] = {}
    try:
        for payload in _records(path):
            kind = payload.get("kind")
            if header is None:
                if kind != _HEADER:
                    raise RepairPlanError("legacy_repair_plan_header_missing")
                header = payload
                continue
            if footer is not None:
                raise RepairPlanError("legacy_repair_plan_trailing_data")
            if kind == _FOOTER:
                footer = payload
                continue
            grouped.setdefault(str(kind), []).append(payload)
    except (OSError, EOFError, gzip.BadGzipFile):
        raise RepairPlanError("legacy_repair_plan_unreadable") from None
    if header is None or footer is None:
        raise RepairPlanError("legacy_repair_plan_truncated")
    if header.get("format") != PLAN_FORMAT or header.get("format_version") != PLAN_FORMAT_VERSION:
        raise RepairPlanError("legacy_repair_plan_format_unsupported")
    if header.get("repair") != repair:
        raise RepairPlanError("legacy_repair_plan_repair_mismatch")
    observed = {kind: len(rows) for kind, rows in grouped.items()}
    if observed != dict(footer.get("counts") or {}):
        raise RepairPlanError("legacy_repair_plan_count_mismatch")
    return LoadedPlan(header=header, records=grouped, sha256=actual)


def read_plan_header(path: str, *, expected_sha256: str, repair: str) -> dict:
    """Yalnız BAŞLIQ — sha256 bütün fayl üzrə yoxlanılır (bütövlük), sətirlər yüklənmir.

    Başqa təmirin planın möhürlənmiş başlığındakı siyahıya (məs. hazırda oxuyanlar)
    istinad etməsi üçün.
    """

    _verified_sha256(path, expected_sha256)
    try:
        header = next(iter(_records(path)), None)
    except (OSError, EOFError, gzip.BadGzipFile):
        raise RepairPlanError("legacy_repair_plan_unreadable") from None
    if header is None or header.get("kind") != _HEADER:
        raise RepairPlanError("legacy_repair_plan_header_missing")
    if header.get("format") != PLAN_FORMAT or header.get("format_version") != PLAN_FORMAT_VERSION:
        raise RepairPlanError("legacy_repair_plan_format_unsupported")
    if header.get("repair") != repair:
        raise RepairPlanError("legacy_repair_plan_repair_mismatch")
    return header


__all__ = [
    "PLAN_FORMAT",
    "PLAN_FORMAT_VERSION",
    "LoadedPlan",
    "PlanManifest",
    "RepairPlanError",
    "file_sha256",
    "read_plan",
    "read_plan_header",
    "write_plan",
]
