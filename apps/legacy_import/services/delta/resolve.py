"""Legacy açarı → hədəf obyekti: ledger, təbii açar və ad tutuşdurması (YAZMIR).

Ardıcıllıq hər növdə eynidir — ən güclü sübut birinci:

1. cutover ledger-i (``LegacyEntityMap``, ``state=migrated``);
2. delta-nın öz deterministik açarı (qrup slug-ı ``myedu-grp-<id>``, fənn kodu ``QKU-<id>``,
   tələbənin ``institutional_identifier``-ı = legacy id) — təkrar qaçışda əvvəlki delta-nın
   yaratdığını tapır;
3. ad tutuşdurması — YALNIZ tək namizəd olduqda (çox namizəd = «ambiqü», heç vaxt təxmin edilmir).
"""

from __future__ import annotations

import datetime
import re
import unicodedata
from collections import defaultdict

from django.apps import apps as django_apps

from ..legacy_text import clean_text
from ..rehearsal_contracts import SOURCE_SYSTEM

GROUP_SLUG_PREFIX = "myedu-grp-"
SUBJECT_CODE_PREFIX = "QKU-"
SEASON_BY_TYPE = {"autumn": "Payız", "spring": "Yaz", "summer": "Yay"}
_FOLD = str.maketrans({"ı": "i", "ə": "e", "ö": "o", "ü": "u", "ş": "s", "ç": "c", "ğ": "g"})
_NOISE = re.compile(r"[\s\-_./]+")


def text(value, *, limit: int = 255) -> str:
    """Legacy mətni (HTML entity açılmış, boşluqları sıxılmış)."""

    if value is None:
        return ""
    return clean_text(str(value), max_length=limit)[0]


def _fold(value: str) -> str:
    folded = unicodedata.normalize("NFC", value).replace("İ", "i").replace("I", "i").casefold().translate(_FOLD)
    return "".join(ch for ch in unicodedata.normalize("NFKD", folded) if not unicodedata.combining(ch))


def group_key(name) -> str:
    """Qrup adı açarı: hərf/rəqəm, böyük-kiçik, İ/I/ı və ayırıcılar fərqi atılır («236 İT» = «236it»)."""

    return _NOISE.sub("", _fold(text(name)))


def group_key_variants(name) -> tuple[str, ...]:
    """Əsas açar + «az» dil şəkilçisi atılmış forma («236 BİO az» → «236bio»)."""

    key = group_key(name)
    variants = [key]
    if key.endswith("az") and len(key) > 4:
        variants.append(key[:-2])
    return tuple(variants)


def subject_key(name) -> str:
    return " ".join(_fold(text(name)).split())


def person_key(value) -> str:
    return re.sub(r"[^a-z]", "", _fold(text(value, limit=100)))


def period_year(name: str) -> str:
    match = re.search(r"(\d{4})\s*/\s*(\d{4})", name or "")
    return f"{match.group(1)}/{match.group(2)}" if match else ""


def ledger_map(organization, entity_type: str, legacy_pks=None) -> dict:
    """``legacy_pk → target_pk`` (yalnız ``migrated``); ``legacy_pks`` verilibsə yalnız onlar."""

    model = django_apps.get_model("legacy_import", "LegacyEntityMap")
    queryset = model.objects.filter(
        organization=organization, source_system=SOURCE_SYSTEM, entity_type=entity_type, state="migrated"
    )
    if legacy_pks is None:
        return dict(queryset.values_list("legacy_pk", "target_pk"))
    keys = sorted({str(key) for key in legacy_pks})
    found: dict = {}
    for start in range(0, len(keys), 5000):
        found.update(queryset.filter(legacy_pk__in=keys[start : start + 5000]).values_list("legacy_pk", "target_pk"))
    return found


class Catalog:
    """Hədəf təşkilatın tutuşdurma indeksləri (bir dəfə qurulur, yazılarla yenilənir)."""

    def __init__(self, organization):
        self.organization = organization
        OrgUnit = django_apps.get_model("organizations", "OrgUnit")
        Subject = django_apps.get_model("registrar", "Subject")
        self.units = {unit.pk: unit for unit in OrgUnit.objects.filter(organization=organization)}
        self.groups_by_key: dict = defaultdict(list)
        self.group_by_slug: dict = {}
        for unit in self.units.values():
            if unit.unit_type == "group":
                self.index_group(unit)
        self.subjects = {subject.pk: subject for subject in Subject.objects.filter(organization=organization)}
        self.subject_by_code = {subject.code.upper(): subject for subject in self.subjects.values()}
        self.subjects_by_key: dict = defaultdict(list)
        for subject in self.subjects.values():
            self.subjects_by_key[subject_key(subject.name)].append(subject)
        self.led_group = ledger_map(organization, "group_unit")
        self.led_subject = ledger_map(organization, "lesson_subject")
        self.led_speciality = ledger_map(organization, "speciality_unit")
        self.led_department = ledger_map(organization, "department_unit")
        self.led_period = ledger_map(organization, "academic_period")

    def index_group(self, unit) -> None:
        self.units[unit.pk] = unit
        self.group_by_slug[unit.slug] = unit
        for variant in group_key_variants(unit.name):
            if unit not in self.groups_by_key[variant]:
                self.groups_by_key[variant].append(unit)

    def index_subject(self, subject) -> None:
        self.subjects[subject.pk] = subject
        self.subject_by_code[subject.code.upper()] = subject
        self.subjects_by_key[subject_key(subject.name)].append(subject)

    # ── qrup ──────────────────────────────────────────────────────────────
    def group_for(self, legacy: dict):
        """``(unit | None, üsul)`` — üsul: ledger / slug / name / ambiguous / missing."""

        target = self.led_group.get(str(legacy["id"]))
        if target:
            unit = self.units.get(_uuid(target))
            if unit is not None:
                return unit, "ledger"
        unit = self.group_by_slug.get(f"{GROUP_SLUG_PREFIX}{legacy['id']}")
        if unit is not None:
            return unit, "slug"
        for variant in group_key_variants(legacy.get("name")):
            found = [unit for unit in self.groups_by_key.get(variant, []) if unit.is_active]
            if len(found) == 1:
                return found[0], "name"
            if len(found) > 1:
                return None, "ambiguous"
        return None, "missing"

    def unit_for_speciality(self, speciality_id):
        target = self.led_speciality.get(str(speciality_id))
        return self.units.get(_uuid(target)) if target else None

    def unit_for_department(self, department_id):
        target = self.led_department.get(str(department_id))
        return self.units.get(_uuid(target)) if target else None

    # ── fənn ──────────────────────────────────────────────────────────────
    def subject_for(self, legacy: dict):
        target = self.led_subject.get(str(legacy["id"]))
        if target and _uuid(target) in self.subjects:
            return self.subjects[_uuid(target)], "ledger"
        subject = self.subject_by_code.get(f"{SUBJECT_CODE_PREFIX}{legacy['id']}")
        if subject is not None:
            return subject, "code"
        found = [subject for subject in self.subjects_by_key.get(subject_key(legacy.get("name")), [])]
        active = [subject for subject in found if subject.is_active] or found
        if len(active) == 1:
            return active[0], "name"
        return None, "ambiguous" if active else "missing"

    # ── dövr ──────────────────────────────────────────────────────────────
    def period_for(self, legacy: dict):
        AcademicPeriod = django_apps.get_model("organizations", "AcademicPeriod")
        target = self.led_period.get(str(legacy["id"]))
        if target:
            period = AcademicPeriod.objects.filter(pk=target, organization=self.organization).first()
            if period is not None:
                return period
        season = SEASON_BY_TYPE.get(str(legacy.get("type") or ""))
        name = str(legacy.get("name") or "")
        for label in SEASON_BY_TYPE.values():
            if label in name:
                season = label  # ad tipdən güclüdür («2026/2027 Yaz» tipi səhvən autumn yazılıb)
        year = period_year(name)
        if not season or not year:
            return None
        return AcademicPeriod.objects.filter(organization=self.organization, name=season, academic_year=year).first()


def _uuid(value):
    import uuid

    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return value


def lesson_date(period, month: int, day: int):
    """Ay/gün + semestr → tarix; semestrin [başlanğıc−45 gün, son+60 gün] pəncərəsindən kənarsa ``None``."""

    start, end = period.start_date, period.end_date
    if not start or not end:
        return None
    for year in (start.year, start.year + 1, end.year):
        try:
            candidate = datetime.date(year, month, day)
        except ValueError:
            continue
        if start - datetime.timedelta(days=45) <= candidate <= end + datetime.timedelta(days=60):
            return candidate
    return None


__all__ = [
    "GROUP_SLUG_PREFIX",
    "SUBJECT_CODE_PREFIX",
    "Catalog",
    "group_key",
    "group_key_variants",
    "ledger_map",
    "lesson_date",
    "period_year",
    "person_key",
    "subject_key",
    "text",
]
