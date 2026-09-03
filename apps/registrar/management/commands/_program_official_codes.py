"""Rəsmi ixtisas şifrləri — KATALOQ-ƏSASLI data qatı.

Nə dəyişdi (2026-08-31) və NİYƏ
-------------------------------
Bu modul əvvəl **əl ilə yığılmış 5 sətirlik cədvəl** idi. Rəsmi mənbələr
(e-qanun) endirilib parse olunandan sonra məlum oldu ki, həmin 5 sətrin
**2-si SƏHVDİR**::

    MYEDU-40 «İqtisadiyyat» → 050405   ✗  050405 = «Sənayenin təşkili və idarə olunması»
    MYEDU-43 «Maliyyə»      → 050406   ✗  050406 = «Statistika»

Hər ikisi «iki müstəqil mənbə + düşmən doğrulayıcısının TƏTBİQ ET hökmü» kimi
qeyd olunmuşdu. Yəni PROSES səhv deyildi — MƏNBƏ səhv idi: heç kim şifri
təsnifatın ÖZÜ ilə tutuşdurmamışdı. Ona görə indi cədvəl əl ilə yığılmır:
rəsmi kataloqlar repoya köçürülüb və emissiya olunan HƏR şifr icra anında
həmin kataloqa qarşı yoxlanılır (:func:`load_catalogs`, :func:`validate`).

Mənbə sənədlər (``apps/registrar/data/ixtisas/`` — bax oradakı ``README.md``)
----------------------------------------------------------------------------
``catalog_2024.tsv``
    NK **503**, 02.12.2024 (NK 109, 17.04.2026 düzəlişi daxil) — CARİ təsnifat.
    329 ixtisas: bakalavr 154 · baza ali tibb 3 · magistratura 129 · rezidentura 43.
``catalog_legacy_bachelor.tsv``
    e-qanun 16051 — əvvəlki nəsil bakalavr (``050XXX``), 169 ixtisas.
``catalog_legacy_master.tsv``
    e-qanun 21781 — əvvəlki nəsil magistratura (``060XXX``), 202 ixtisas.
``program_codes.tsv``
    WCU-nun 101 proqramının hər iki nəslə uyğunlaşdırılması + əminlik dərəcəsi.

Əminlik dərəcələri
------------------
``dəqiq``
    Ad rəsmi kataloqda hərfi (və ya yalnız hal/orfoqrafiya fərqi ilə) var.
``yüksək``
    İxtisas eynidir, amma **ad rəsmən dəyişib** (``050624`` «Cihazqayırma
    mühəndisliyi» → ``6006004`` «Cihaz mühəndisliyi»). Yazılır.
``şübhəli``
    Bir neçə real namizəd var, seçim SAHİBİNDİR — **yazılmır**.
``tapılmadı``
    Sətir ixtisas DEYİL («Level», «aaa», «Kollec», «Lifelong» …) — şifr
    verilmir, silinmə də olmur.

Qırmızı xətt
------------
UYDURMA ŞİFR YOXDUR. :func:`validate` emissiya olunan hər şifr üçün tələb edir:

1. şifr rəsmi kataloqda **mövcuddur**;
2. kataloqdakı adı fayldakı adla **eynidir**;
3. şifrin nəsli/pilləsi sətrin pilləsi ilə **uyğundur**
   (``05``↔bachelor, ``06``↔master; ``6``↔bachelor, ``7``↔master).

Pozuntu olarsa komanda HEÇ NƏ yazmadan dayanır (fail-closed).
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

#: Data qovluğu — ``apps/registrar/data/ixtisas/``.
DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "ixtisas"

CATALOG_CURRENT = DATA_DIR / "catalog_2024.tsv"
CATALOG_LEGACY_BACHELOR = DATA_DIR / "catalog_legacy_bachelor.tsv"
CATALOG_LEGACY_MASTER = DATA_DIR / "catalog_legacy_master.tsv"
MAPPING_FILE = DATA_DIR / "program_codes.tsv"

#: Əvvəlki nəsil təsnifatda pillə → şifr prefiksi.
LEGACY_LEVEL_PREFIXES: dict[str, str] = {"bachelor": "05", "master": "06"}
#: CARİ (NK 503/2024) təsnifatda pillə → şifr prefiksi.
CURRENT_LEVEL_PREFIXES: dict[str, str] = {"bachelor": "6", "master": "7"}

#: Əvvəlki nəsil şifr formatı.
LEGACY_CODE_RE = re.compile(r"^0[56]\d{4}$")
#: CARİ təsnifatın şifr formatı.
CURRENT_CODE_RE = re.compile(r"^[67]\d{6}$")

#: Şifr YAZILAN əminlik dərəcələri.
WRITABLE = ("dəqiq", "yüksək")
#: Sahibin qərarını gözləyən dərəcə.
NEEDS_OWNER = "şübhəli"
#: İxtisas olmayan sətirlər.
NOT_A_PROGRAM = "tapılmadı"


@dataclass(frozen=True)
class CodeRow:
    """Bir proqramın hər iki nəsildəki rəsmi şifri + əminlik dərəcəsi."""

    #: Hədəf sətri tapmaq üçün DAXİLİ kod — heç vaxt dəyişdirilmir.
    internal_code: str
    #: Gözlənilən ad — kor-koranə UPDATE-in qarşısını alır.
    expected_name: str
    degree_level: str
    #: Əvvəlki nəsil şifr (``050XXX``/``060XXX``); yoxdursa boş.
    legacy_code: str
    legacy_name: str
    #: CARİ (NK 503/2024) şifr (``6XXXXXX``/``7XXXXXX``); ləğv olunubsa boş.
    current_code: str
    current_name: str
    confidence: str
    note: str

    @property
    def is_writable(self) -> bool:
        """Şifr yazılırmı — yalnız ``dəqiq``/``yüksək`` və ən azı bir şifr varsa."""
        return self.confidence in WRITABLE and bool(self.legacy_code or self.current_code)

    @property
    def is_not_a_program(self) -> bool:
        return self.confidence == NOT_A_PROGRAM


@dataclass(frozen=True)
class HeldBack:
    """Yazılmayan sətir — sahibin qərarını gözləyir və ya ixtisas deyil."""

    internal_code: str
    name: str
    reason: str


@dataclass
class WritePlan:
    """Bir icranın planı — nə yazılacaq, nə keçilir, nə bloklayır."""

    pending: list = field(default_factory=list)  # (Program, CodeRow, {sahə: (köhnə, yeni)})
    already_done: list = field(default_factory=list)  # (Program, CodeRow)
    held: list = field(default_factory=list)  # (Program, CodeRow)
    missing: list = field(default_factory=list)  # CodeRow — bazada tapılmadı
    blocked: list = field(default_factory=list)  # (CodeRow, səbəb)


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return [{k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(handle, delimiter="\t")]


@lru_cache(maxsize=1)
def load_catalogs() -> tuple[dict[str, str], dict[str, str]]:
    """Rəsmi kataloqlar: ``(cari_şifr→ad, köhnə_şifr→ad)``.

    Köhnə bakalavr (``05``) və magistr (``06``) şifr fəzaları kəsişmir, ona
    görə tək lüğətdə birləşdirilir.
    """
    current = {row["kod"]: row["ad"] for row in _read_tsv(CATALOG_CURRENT)}
    legacy = {row["kod"]: row["ad"] for row in _read_tsv(CATALOG_LEGACY_BACHELOR)}
    legacy.update({row["kod"]: row["ad"] for row in _read_tsv(CATALOG_LEGACY_MASTER)})
    return current, legacy


@lru_cache(maxsize=1)
def load_rows() -> tuple[CodeRow, ...]:
    """``program_codes.tsv`` → :class:`CodeRow` sırası."""
    return tuple(
        CodeRow(
            internal_code=row["daxili_kod"],
            expected_name=row["ad"],
            degree_level=row["seviyye"],
            legacy_code=row["kohne_kod"],
            legacy_name=row["kohne_ad"],
            current_code=row["cari_kod"],
            current_name=row["cari_ad"],
            confidence=row["eminlik"],
            note=row["qeyd"],
        )
        for row in _read_tsv(MAPPING_FILE)
    )


def _check_code(
    *,
    code: str,
    name: str,
    catalog: dict[str, str],
    prefix: str | None,
    pattern: re.Pattern[str],
    kind: str,
    row: CodeRow,
) -> list[str]:
    problems: list[str] = []
    where = f"{row.internal_code} «{row.expected_name}»"
    if not pattern.match(code):
        problems.append(f"{where}: {kind} şifr «{code}» format qaydasına uyğun deyil")
        return problems
    if code not in catalog:
        problems.append(f"{where}: {kind} şifr «{code}» RƏSMİ KATALOQDA YOXDUR — uydurma şifr")
        return problems
    if catalog[code] != name:
        problems.append(f"{where}: {kind} şifr «{code}» kataloqda «{catalog[code]}», faylda «{name}»")
    if prefix and not code.startswith(prefix):
        problems.append(
            f"{where}: {kind} şifr «{code}» «{row.degree_level}» pilləsinə uyğun deyil (gözlənilən {prefix}…)"
        )
    return problems


def validate() -> list[str]:
    """Bütün fayl datasını rəsmi kataloqlara qarşı yoxla; problem siyahısı qaytar.

    BOŞ siyahı = fayldakı hər şifr rəsmi kataloqda MÖVCUDDUR, adı üst-üstə
    düşür və pilləsi uyğundur. Boş deyilsə komanda heç nə yazmır.
    """
    current_catalog, legacy_catalog = load_catalogs()
    problems: list[str] = []
    seen: set[str] = set()

    for row in load_rows():
        if row.internal_code in seen:
            problems.append(f"{row.internal_code}: daxili kod faylda TƏKRARLANIR")
        seen.add(row.internal_code)

        if row.degree_level not in LEGACY_LEVEL_PREFIXES:
            problems.append(f"{row.internal_code}: tanınmayan pillə «{row.degree_level}»")
            continue
        if row.confidence not in (*WRITABLE, NEEDS_OWNER, NOT_A_PROGRAM):
            problems.append(f"{row.internal_code}: tanınmayan əminlik «{row.confidence}»")
        if row.is_not_a_program and (row.legacy_code or row.current_code):
            problems.append(f"{row.internal_code}: «tapılmadı» sətrinə şifr verilib — ola bilməz")

        if row.legacy_code:
            problems += _check_code(
                code=row.legacy_code,
                name=row.legacy_name,
                catalog=legacy_catalog,
                prefix=LEGACY_LEVEL_PREFIXES[row.degree_level],
                pattern=LEGACY_CODE_RE,
                kind="köhnə",
                row=row,
            )
        if row.current_code:
            problems += _check_code(
                code=row.current_code,
                name=row.current_name,
                catalog=current_catalog,
                prefix=CURRENT_LEVEL_PREFIXES[row.degree_level],
                pattern=CURRENT_CODE_RE,
                kind="cari",
                row=row,
            )
    return problems


def writable_rows() -> tuple[CodeRow, ...]:
    return tuple(row for row in load_rows() if row.is_writable)


def owner_decision_rows() -> tuple[CodeRow, ...]:
    """«şübhəli» — namizədləri var, seçim sahibindir."""
    return tuple(row for row in load_rows() if row.confidence == NEEDS_OWNER)


def non_program_rows() -> tuple[HeldBack, ...]:
    """İxtisas OLMAYAN sətirlər — ``archive_non_program_rows`` bunu işlədir."""
    return tuple(
        HeldBack(internal_code=row.internal_code, name=row.expected_name, reason=row.note)
        for row in load_rows()
        if row.is_not_a_program
    )


#: Geriyə uyğunluq: ``archive_non_program_rows`` modul səviyyəsində import edir.
NON_PROGRAM_ROWS: tuple[HeldBack, ...] = non_program_rows()


__all__ = [
    "CURRENT_CODE_RE",
    "CURRENT_LEVEL_PREFIXES",
    "DATA_DIR",
    "LEGACY_CODE_RE",
    "LEGACY_LEVEL_PREFIXES",
    "MAPPING_FILE",
    "NEEDS_OWNER",
    "NON_PROGRAM_ROWS",
    "NOT_A_PROGRAM",
    "WRITABLE",
    "CodeRow",
    "HeldBack",
    "WritePlan",
    "load_catalogs",
    "load_rows",
    "non_program_rows",
    "owner_decision_rows",
    "validate",
    "writable_rows",
]
