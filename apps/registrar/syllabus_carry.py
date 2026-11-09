"""Təsdiqlənmiş sillabus müəllimin başqa qrupunda da (sahib 2026-11-08).

Sahib: «müəllimin bir fənn üzrə sillabusu bir qrupda təsdiqlənibsə və həmin müəllim o fənni başqa qrupda da
keçirsə, o sillabus orada da təsdiqlənmiş sayılsın».

Yazı mövcud «bir sillabus — bir neçə jurnal» modelidir (``SyllabusShare``, mənbə ``carry``): surət yoxdur, təsdiq
BİRDİR.  Paylaşım qaydaları (eyni fənn + semestr, kök dosye, yalnız boş jurnal, açılışın müəllimi dosyenin sahibidir)
``apps.syllabus.services.sharing``-dədir; burada açılış tərəfinin əlavə QORUYUCULARI var:

* **Hədəf boşdur** — jurnal heç bir sillabus göstərmir (öz / paylaşılan / semestr / baza pilləsi, istənilən status).
  Qaralaması və ya baxışda olan sillabusu olan jurnala toxunulmur.
* **Namizəd** — eyni təşkilat, eyni fənn kartı (``subject_id``) və eyni semestr, aktiv kök dosye, öz açılışı aktivdir
  və hədəf deyil, hədəfin müəllimi dosyenin müəllifi və ya öz açılışının müəllimidir (jurnal sillabus siyahısının
  — ``syllabus_peers`` / ``sibling_queryset`` — «eyni fənn» qaydası) və QÜVVƏDƏ təsdiqlənmiş versiyası var.
* **Tədris dili** eynidir — qrupun ``language_sector`` / ``sector`` dəyəri, yoxsa adın sonluğu (``az|ing|en|ru``,
  sonluqsuz ad = az); ``en/eng → ing``, ``ru → rus``.  «ing» qrupuna «az» sillabusu getmir.
* **Saat bölgüsü** eynidir — hədəfin mühazirə/seminar/lab saatı (``plan_hours_for_offering``) mənbə qrupun saatı ilə
  (dosyedə kafedranın əl düzəlişi varsa onunla) üst-üstə düşür; fərqlidirsə həftəlik plan səhv olardı.
* **Birmənalılıq** — qoruyuculardan keçən namizəd TƏKDİRSƏ paylaşılır; bir neçə fərqli dosye — toxunulmur.
* **Görünürlük** — yazıdan sonra jurnal həlli (``syllabus_for_offering``) məhz bu dosyeni qaytarmırsa (məs. dil
  səviyyə kohortu) yazı geri alınır.
"""

from __future__ import annotations

import logging
import re

from django.apps import apps as django_apps
from django.db import transaction
from django.db.models import Q

logger = logging.getLogger(__name__)

SHARED = "shared"
HAS_SYLLABUS = "has_syllabus"
NO_INSTRUCTOR = "no_instructor"
NO_CANDIDATE = "no_candidate"
UNAPPROVED = "skipped_unapproved"
LANGUAGE = "skipped_language"
HOURS = "skipped_hours"
AMBIGUOUS = "ambiguous"
INVISIBLE = "skipped_invisible"
TAKEN = "taken"

#: Xülasə sətrində həmişə görünən açarlar (sıfır olsa belə).
SUMMARY_KEYS = (SHARED, AMBIGUOUS, LANGUAGE, HOURS, UNAPPROVED, HAS_SYLLABUS, INVISIBLE)

_SUFFIX = re.compile(r"\s+(az|ing|en|eng|ru|rus)$", re.IGNORECASE)
_ALIASES = {"en": "ing", "eng": "ing", "english": "ing", "ru": "rus", "aze": "az"}
_HOUR_KINDS = ("lecture", "seminar", "lab")


class _Invisible(Exception):
    """Yazı jurnal həllində görünmür — savepoint geri alınır."""


def group_language(group) -> str:
    """Qrupun tədris dili (normallaşdırılmış); qrup yoxdursa ``""``."""
    if group is None:
        return ""
    raw = group.settings if isinstance(group.settings, dict) else {}
    value = str(raw.get("language_sector") or raw.get("sector") or "").strip().casefold()
    if not value:
        match = _SUFFIX.search(" ".join(str(group.name or "").split()))
        value = match[1].casefold() if match else "az"
    return _ALIASES.get(value, value)


def _clean_hours(value) -> dict:
    hours = {}
    for kind in _HOUR_KINDS:
        try:
            number = int((value or {}).get(kind) or 0)
        except (AttributeError, TypeError, ValueError):
            number = 0
        if number > 0:
            hours[kind] = number
    return hours


def _offering_hours(offering, memo) -> dict:
    if offering.pk not in memo:
        from .plan_hours import plan_hours_for_offering

        memo[offering.pk] = _clean_hours(plan_hours_for_offering(offering))
    return memo[offering.pk]


def _reference_hours(syllabus, memo) -> dict:
    """Mənbənin saatı — kafedranın əl düzəlişi (bir qrup üçün) varsa o, yoxsa mənbə qrupun plan saatı."""
    override = _clean_hours(syllabus.plan_hours_override if isinstance(syllabus.plan_hours_override, dict) else {})
    return override or _offering_hours(syllabus.offering, memo)


def _resolved(offering):
    from apps.syllabus.public import syllabus_for_offering

    return syllabus_for_offering(
        organization=offering.organization,
        offering_id=offering.pk,
        subject_id=offering.subject_id,
        period_id=offering.period_id,
        instructor_id=offering.instructor_id,
    )


def _candidates(offering) -> list:
    Syllabus = django_apps.get_model("syllabus", "Syllabus")
    teacher = offering.instructor_id
    return list(
        Syllabus.objects.filter(
            organization_id=offering.organization_id,
            is_active=True,
            reused_from__isnull=True,
            subject_id=offering.subject_id,
            period_id=offering.period_id,
            offering__isnull=False,
            offering__is_active=True,
        )
        .exclude(offering_id=offering.pk)
        .filter(Q(author_id=teacher) | Q(offering__instructor_id=teacher))
        .select_related(
            "offering", "offering__group", "offering__organization", "offering__subject", "approved_version"
        )
        .order_by("pk")
    )


def _is_approved(syllabus) -> bool:
    from apps.syllabus.public import SyllabusStatus

    version = syllabus.approved_version if syllabus.approved_version_id else None
    return version is not None and version.status == SyllabusStatus.APPROVED.value


def choose_source(offering, *, hours_memo=None, allow_existing=False) -> tuple:
    """``(kod, dosye|None)`` — yazmadan, yalnız seçim (qaydalar modul docstring-indədir)."""
    if offering is None or not offering.is_active or offering.instructor_id is None or offering.period_id is None:
        return NO_INSTRUCTOR, None
    # Completion may inspect the same guarded donor for an occupied dossier.
    # The carry writer never opts in and retains its empty-target requirement.
    if not allow_existing and _resolved(offering) is not None:
        return HAS_SYLLABUS, None
    candidates = _candidates(offering)
    approved = [row for row in candidates if _is_approved(row)]
    if not approved:
        return (UNAPPROVED if candidates else NO_CANDIDATE), None
    language = group_language(offering.group if offering.group_id else None)
    same_language = [
        row
        for row in approved
        if language and group_language(row.offering.group if row.offering.group_id else None) == language
    ]
    if not same_language:
        return LANGUAGE, None
    memo = {} if hours_memo is None else hours_memo
    target_hours = _offering_hours(offering, memo)
    fitting = [row for row in same_language if _reference_hours(row, memo) == target_hours]
    if not fitting:
        return HOURS, None
    if len({row.pk for row in fitting}) > 1:
        return AMBIGUOUS, None
    return SHARED, fitting[0]


def carry_approved(offering, *, user=None, hours_memo=None) -> tuple:
    """Hədəf jurnala müəllimin təsdiqlənmiş sillabusunu bağla (idempotent). ``(kod, SyllabusShare|None)``."""
    code, source = choose_source(offering, hours_memo=hours_memo)
    if source is None:
        return code, None
    from apps.syllabus.public import link_carry_share

    try:
        with transaction.atomic():
            outcome, row = link_carry_share(syllabus=source, offering=offering, user=user)
            if outcome != "linked":
                return (HAS_SYLLABUS if outcome in {"has_own", "already"} else TAKEN), None
            found = _resolved(offering)
            if found is None or found.pk != source.pk:
                raise _Invisible
    except _Invisible:
        return INVISIBLE, None
    return SHARED, row


def carry_for_syllabus(*, syllabus_id, user=None) -> dict:
    """Təsdiq qarmağı: dosyenin sahibinin eyni fənn + semestr üzrə BAŞQA (boş) jurnalları."""
    Syllabus = django_apps.get_model("syllabus", "Syllabus")
    CourseOffering = django_apps.get_model("registrar", "CourseOffering")
    source = (
        Syllabus.objects.select_related("offering")
        .filter(pk=syllabus_id, is_active=True, reused_from__isnull=True, offering__isnull=False, period__isnull=False)
        .first()
    )
    counts: dict = {}
    if source is None:
        return counts
    owners = {source.author_id, source.offering.instructor_id} - {None}
    targets = (
        CourseOffering.objects.filter(
            organization_id=source.organization_id,
            subject_id=source.subject_id,
            period_id=source.period_id,
            is_active=True,
            instructor_id__in=owners,
        )
        .exclude(pk=source.offering_id)
        .select_related("organization", "subject", "group")
        .order_by("pk")
    )
    memo: dict = {}
    for offering in targets:
        code, _row = carry_approved(offering, user=user, hours_memo=memo)
        counts[code] = counts.get(code, 0) + 1
    return counts


def carry_for_offering_id(offering_id) -> str:
    """Müəllim təyini qarmağı: bir jurnal üçün."""
    CourseOffering = django_apps.get_model("registrar", "CourseOffering")
    offering = CourseOffering.objects.select_related("organization", "subject", "group").filter(pk=offering_id).first()
    if offering is None:
        return NO_INSTRUCTOR
    return carry_approved(offering)[0]


def _run_offering(offering_id) -> None:
    try:
        with transaction.atomic():
            carry_for_offering_id(offering_id)
    except Exception:  # noqa: BLE001 — müəllim təyinini heç vaxt pozmur
        logger.exception("syllabus carry failed for offering %s", offering_id)


def offering_saved(sender, instance, created=False, update_fields=None, raw=False, **kwargs) -> None:
    """``post_save(CourseOffering)``: müəllim təyin olunanda (yeni jurnal və ya ``instructor`` dəyişib) — commit-dən sonra."""
    if raw or instance.instructor_id is None or not instance.is_active:
        return
    if not created and not (update_fields and {"instructor", "instructor_id"} & set(update_fields)):
        return
    offering_id = instance.pk
    transaction.on_commit(lambda: _run_offering(offering_id))


__all__ = [
    "AMBIGUOUS",
    "HAS_SYLLABUS",
    "HOURS",
    "INVISIBLE",
    "LANGUAGE",
    "NO_CANDIDATE",
    "SHARED",
    "SUMMARY_KEYS",
    "UNAPPROVED",
    "carry_approved",
    "carry_for_offering_id",
    "carry_for_syllabus",
    "choose_source",
    "group_language",
    "offering_saved",
]
