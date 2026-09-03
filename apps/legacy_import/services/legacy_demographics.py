"""Legacy demoqrafiya: ``sex`` → ``UserProfile.gender``, ``birthday`` → ``birth_date``.

Niyə ayrıca modul
-----------------
``students``/``workers`` üçün ``sex`` və ``birthday`` sütunları ARTIQ
``STUDENT_IDENTITY_FIELDS`` / ``WORKER_IDENTITY_FIELDS`` allowlist-indədir —
proyeksiya onları onsuz da gətirir, sadəcə heç kim oxumurdu.  Ona görə burada
HEÇ BİR kontrakt genişləndirilmir: kontrakt ``version``/``allowed_fields``
dəyərini yerində dəyişmək faza möhürlərini pozur (bax
``tests/test_contract_fingerprint_stability.py`` docstring-i).  Bu modul yalnız
mövcud proyeksiyanı oxuyur.

Cins uyğunlaşması (mənbədə ölçülüb, 2026-08-30)
-----------------------------------------------
``students.sex`` / ``workers.sex`` ``int(1)``-dir, default ``0``::

    0 → UNSPECIFIED   1 → MALE (kişi)   2 → FEMALE (qadın)

Sübut: ``students`` cədvəlində sex=1/2 olan 1 639 sətrin ad histoqramı
birmənalı Azərbaycan adları lüğəti ilə çarpazlaşdırıldı — sex=1 altında 265
kişi adı və SIFIR qadın adı, sex=2 altında 368 qadın adı və SIFIR kişi adı
(0 % çarpaz çirklənmə).  ``workers`` tərəfi eyni istiqaməti təsdiqləyir.
Mənbədəki ayrıca ``students.gender`` mətn sütunu QƏSDƏN istifadə olunmur: o,
``sex``-lə ziddiyyət təşkil edir (sex=2 ∧ gender='Kişi' → 29 sətir), yəni
etibarsız ikinci mənbədir.

Doğum tarixi
------------
Mənbə ``varchar``-dır və üç forma daşıyır: ``DD/MM/YYYY`` (üstünlük təşkil
edən), ISO ``YYYY-MM-DD`` və ``DD-MM-YYYY`` / ``DD.MM.YYYY`` variantları.
Fail-closed: təqvimə uyğun olmayan, kəsik (``20/05/79__``) və ya ağlabatan
pəncərədən kənar dəyər NULL qalır.  ``MM/DD/YYYY`` kimi görünən 19 sətir
(məs. ``12/16/2001``) QƏSDƏN rədd edilir — bir sətri MM/DD saymaq
``07/08/2022``-ni necə oxumaq lazım olduğuna dair təxminə çevrilərdi.

Hər funksiya öz girişinin təmiz funksiyasıdır; ``source_row_hash`` xam dəyəri
digest etməyə davam edir, ona görə buradakı qaydanın dəyişməsi mənbənin nə
saxladığına dair sübutu heç vaxt yenidən yaza bilməz.
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass

from django.apps import apps as django_apps
from django.utils import timezone

from .rehearsal_contracts import LegacyRehearsalEvidenceError

#: ``UserProfile.Gender`` dəyərləri.  Sətir sabitləri qəsdən təkrarlanır ki, bu
#: modul model importuna bağlanmasın; ``tests/test_legacy_demographics.py``
#: onların modellə eyniliyini qapı kimi yoxlayır.
GENDER_UNSPECIFIED = "unspecified"
GENDER_MALE = "male"
GENDER_FEMALE = "female"

#: ``sex`` sütununun təsdiqlənmiş kodları.  Cari dump-da BAŞQA dəyər yoxdur
#: (``students``: 0/1/2, ``workers``: 0/1/2 — mənbədə sayılıb).  Naməlum bir kod
#: peyda olarsa nə fərziyyə edilir, nə də run çökdürülür: sətir "təyin
#: edilməyib" qalır, yəni HEÇ BİR iddia yazılmır (bax ``legacy_gender``).
_SEX_CODES = {0: GENDER_UNSPECIFIED, 1: GENDER_MALE, 2: GENDER_FEMALE}
KNOWN_SEX_CODES = frozenset(_SEX_CODES)

_DMY_PATTERN = re.compile(r"(\d{2})([/.-])(\d{2})\2(\d{4})\Z")
_ISO_PATTERN = re.compile(r"(\d{4})-(\d{2})-(\d{2})\Z")

#: Ağlabatan doğum pəncərəsi.  Aşağı hədd yazı səhvlərini (``17/07/1487``),
#: yuxarı hədd isə "sətrin yaradıldığı tarix" sızmasını (``2026-02-17``) kəsir.
MIN_PLAUSIBLE_AGE = 14
MAX_PLAUSIBLE_AGE = 100

_TYPE_INVALID = "legacy_demographics_source_value_type_invalid"
_TARGET_MISSING = "legacy_rehearsal_resume_target_missing"

#: ``write_demographics`` vəziyyət nişanları — derivation hash-in bir hissəsi.
STATE_BLANK = "blank"  # mənbədə heç nə yoxdur
STATE_WRITTEN = "written"  # boş hədəf sahə dolduruldu
STATE_PRESERVED = "preserved"  # hədəfdə artıq dəyər var idi, toxunulmadı
STATE_UNWRITTEN = "unwritten"  # bu qərar yolunda yazı ümumiyyətlə baş vermir


@dataclass(frozen=True)
class Demographics:
    """Bir mənbə sətrindən çıxarılmış, hədəfə yazılmağa hazır demoqrafiya."""

    gender: str = GENDER_UNSPECIFIED
    birth_date: datetime.date | None = None

    @property
    def is_blank(self) -> bool:
        return self.gender == GENDER_UNSPECIFIED and self.birth_date is None


def legacy_gender(value: object) -> str:
    """``sex`` sütununu ``UserProfile.Gender`` dəyərinə çevir.

    ``None`` MySQL-in eyni sıfır sentinelidir.  ``bool`` üçün ``type() is int``
    onsuz da False-dur, ona görə bayraq sütunu fail-closed qalır.
    """

    if value is None:
        return GENDER_UNSPECIFIED
    if type(value) is not int:
        raise LegacyRehearsalEvidenceError(_TYPE_INVALID)
    # Təsdiqlənməmiş kod → "təyin edilməyib": bu bir təxmin DEYİL, iddianın
    # olmamasıdır.  Run-u çökdürmək bir kosmetik sütun üçün həddindən artıq
    # sərt olardı; uydurmaq isə qadağandır — sentinel hər iki tələni keçir.
    return _SEX_CODES.get(value, GENDER_UNSPECIFIED)


def _plausible_window(today: datetime.date) -> tuple[datetime.date, datetime.date]:
    return (
        datetime.date(today.year - MAX_PLAUSIBLE_AGE, 1, 1),
        datetime.date(today.year - MIN_PLAUSIBLE_AGE, 12, 31),
    )


def legacy_birth_date(value: object, *, today: datetime.date | None = None) -> datetime.date | None:
    """``birthday`` mətnini tarixə çevir; hər şübhəli dəyər ``None`` qaytarır.

    Qəbul edilən formalar: ``YYYY-MM-DD`` və eyni ayırıcılı ``DD/MM/YYYY``,
    ``DD-MM-YYYY``, ``DD.MM.YYYY``.  Ay/gün yerdəyişməsi TƏXMİN EDİLMİR.
    """

    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        value = value.date()
    if isinstance(value, datetime.date):
        parsed = value
    else:
        if type(value) is not str:
            raise LegacyRehearsalEvidenceError(_TYPE_INVALID)
        text = value.strip()
        if not text:
            return None
        iso = _ISO_PATTERN.fullmatch(text)
        if iso:
            year, month, day = (int(part) for part in iso.groups())
        else:
            dmy = _DMY_PATTERN.fullmatch(text)
            if dmy is None:
                return None
            day, month, year = (int(dmy.group(index)) for index in (1, 3, 4))
        try:
            parsed = datetime.date(year, month, day)
        except ValueError:
            # Təqvimə uyğun olmayan gün/ay (``12/16/2001`` kimi MM/DD sətirləri
            # də bura düşür) — düzəltmək təxmin olardı, ona görə NULL.
            return None
    floor, ceiling = _plausible_window(today or timezone.localdate())
    return parsed if floor <= parsed <= ceiling else None


def demographics_from_row(row) -> Demographics:
    """Proyeksiya olunmuş bir sətirdən demoqrafiyanı çıxar (təmiz funksiya)."""

    return Demographics(gender=legacy_gender(row["sex"]), birth_date=legacy_birth_date(row["birthday"]))


def write_demographics(context, *, user_pk: str, demographics: Demographics) -> str:
    """Yalnız BOŞ hədəf sahələri doldur; mövcud dəyər heç vaxt üzərinə yazılmır.

    ``student_placement._write_patronymic`` və ``write_worker_patronymic`` ilə
    eyni §4.5 müqaviləsi: idxal boşluğu doldurur, əl ilə düzəldilmiş dəyəri
    pozmur.  Profil tenant-a bağlı seçilir — RLS altında yalnız öz təşkilatının
    sətri görünür.  ``UserProfile``-ın yeganə trigger-i (0013) ``access_state``
    keçidinə baxır, bu iki sütuna deyil, ona görə servis qapısı tətbiq olunmur.
    """

    if not isinstance(demographics, Demographics):
        raise LegacyRehearsalEvidenceError(_TYPE_INVALID)
    if demographics.is_blank:
        return STATE_BLANK
    profiles = django_apps.get_model("accounts", "UserProfile").objects.filter(
        user_id=user_pk, organization=context.organization
    )
    row = profiles.values("gender", "birth_date").first()
    if row is None:
        raise LegacyRehearsalEvidenceError(_TARGET_MISSING)

    updates: dict[str, object] = {}
    guard: dict[str, object] = {}
    if demographics.gender != GENDER_UNSPECIFIED and row["gender"] == GENDER_UNSPECIFIED:
        updates["gender"] = demographics.gender
        guard["gender"] = GENDER_UNSPECIFIED
    if demographics.birth_date is not None and row["birth_date"] is None:
        updates["birth_date"] = demographics.birth_date
        guard["birth_date__isnull"] = True
    if not updates:
        return STATE_PRESERVED
    if profiles.filter(**guard).update(updated_at=timezone.now(), **updates) != 1:
        raise LegacyRehearsalEvidenceError(_TARGET_MISSING)
    return STATE_WRITTEN


__all__ = [
    "Demographics",
    "KNOWN_SEX_CODES",
    "GENDER_FEMALE",
    "GENDER_MALE",
    "GENDER_UNSPECIFIED",
    "MAX_PLAUSIBLE_AGE",
    "MIN_PLAUSIBLE_AGE",
    "STATE_BLANK",
    "STATE_PRESERVED",
    "STATE_UNWRITTEN",
    "STATE_WRITTEN",
    "demographics_from_row",
    "legacy_birth_date",
    "legacy_gender",
    "write_demographics",
]
