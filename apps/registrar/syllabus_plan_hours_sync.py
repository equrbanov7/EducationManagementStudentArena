"""Sillabus versiyalarının PLAN SAATINI rəsmi saata gətirən ORTAQ qayda (sahib 2026-11-26).

Problem
-------
2026-11-26 prod: ``fix_syllabus_plan_hours`` 162 versiyanı (159-u təsdiqlənmiş) düzəltdi — dərs yükü sətrinin saatı
sonradan dəyişmişdi (məs. seminar 45 → 15), amma ``plan_hours_source.ensure_plan_hours`` yalnız müəllifin AÇIQ
qaralamasını yeniləyir; təsdiqlənmiş versiya köhnə saatla qalırdı.

İndi iki çağıran eyni qaydanı işlədir:

* ``fix_syllabus_plan_hours`` əmri — bütün təşkilat üzrə yoxlama / düzəliş (quru icra defolt);
* :func:`refresh_offering_syllabus_plan_hours` — açılışın rəsmi saatı DƏYİŞƏ BİLƏN yerdən (``workload`` açılış
  sinxronu: yük sətri yazılanda, təyinat, tapşırığın təsdiqi, ``resync``) dərhal, öz-özünə sağalma.

Qayda (əmrlə EYNİ)
------------------
* gözlənilən saat: dosyedə kafedranın əl ilə düzəlişi (``Syllabus.plan_hours_override``) — o üstündür; yoxdursa
  ``plan_hours_for_offering`` (qrupun planı → yükdə bir qrupun payı → istənilən plan);
* arxivdən başqa BÜTÜN versiyalar (təsdiqlənmiş DAXİL) — yalnız ``plan_hours`` sütunu
  (``services.write_version_plan_hours``); bölmələrə / həftəlik bölgüyə TOXUNULMUR;
* plan saatı BOŞ olan kilidli versiya (köçürülmüş/bağlı nüsxə) doldurulmur — yalnız əmrin ``--fill-empty``-si ilə;
* mənbə tapılmayan versiyaya toxunulmur; hər yazı ``audit_auditlog``-a düşür.

Sorğu büdcəsi: sinxronda versiyalar BİR toplu sorğu ilə oxunur — sillabusu olmayan açılış üçün başqa sorğu yoxdur;
gözlənilən saat yalnız sillabusu olan açılış üçün (açılış başına bir dəfə, memo) hesablanır.
"""

from __future__ import annotations

import logging
from collections import Counter

from django.db import transaction

from apps.syllabus.models import SyllabusVersion
from apps.syllabus.public import SyllabusStatus, services
from core.audit import log_action
from core.constants import AuditAction

from .plan_hours import plan_hours_for_offering

logger = logging.getLogger(__name__)

EDITABLE = frozenset({SyllabusStatus.DRAFT.value, SyllabusStatus.REVISION.value})

REASON_COMMAND = "fix_syllabus_plan_hours: sillabus BİR qrupun saatıdır, müəllimin yükü deyil (sahib 2026-10-25)"
REASON_SYNC = (
    "syllabus_plan_hours_sync: açılışın rəsmi saatı dəyişdi — sillabusun plan saatı yeniləndi (sahib 2026-11-26)"
)

_RELATED = (
    "organization",
    "syllabus",
    "syllabus__offering",
    "syllabus__offering__organization",
    "syllabus__offering__group",
)


def norm(hours) -> dict:
    return services.clean_override_hours(hours)


def expected_plan_hours(syllabus, memo: dict, *, resolve=None) -> dict:
    """Dosyenin gözlənilən plan saatı — düzəliş, yoxdursa açılışın rəsmi saatı (``memo``: açılış → saat).

    ``resolve`` — açılışın saat funksiyası (defolt ``plan_hours_for_offering``; əmr öz adını ötürür).
    """
    override = norm(syllabus.plan_hours_override)
    if override:
        return override
    offering = syllabus.offering if syllabus.offering_id else None
    if offering is None:
        return {}
    if offering.pk not in memo:
        memo[offering.pk] = norm((resolve or plan_hours_for_offering)(offering))
    return memo[offering.pk]


def classify(version, stored: dict, expected: dict, *, fill_empty: bool = False) -> tuple[str, bool]:
    """``(sayğac açarı, düzəldilsinmi)`` — əmrin hesabatı və sinxron eyni qərarı verir."""
    if not expected:
        return "no_source", False
    if stored == expected:
        return "ok", False
    if not stored and version.status not in EDITABLE and not fill_empty:
        return f"empty_locked_skipped:{version.status}", False
    kind = "fill" if not stored else ("lower" if sum(expected.values()) < sum(stored.values()) else "other")
    return f"fix:{version.status}:{kind}", True


def write_fix(version, stored: dict, expected: dict, *, reason: str, user=None, request=None) -> bool:
    """Versiyanı kilidli yenidən oxuyub (yarış: saat arada dəyişibsə yazılmır) yazır + audit → yazıldımı."""
    with transaction.atomic():
        fresh = SyllabusVersion.objects.select_related("organization", "syllabus").get(pk=version.pk)
        if norm(fresh.plan_hours) != stored or not services.write_version_plan_hours(fresh, expected):
            return False
        log_action(
            AuditAction.UPDATE,
            user=user,
            organization=fresh.organization,
            obj=fresh,
            request=request,
            old_values={"plan_hours": stored},
            new_values={"plan_hours": expected},
            reason=reason,
            resource_type="syllabus.version",
            resource_id=str(fresh.pk),
            resource_repr=f"{fresh.syllabus_id} {fresh.label}",
        )
    return True


def versions_queryset():
    """Arxivdən başqa bütün versiyalar — əmr və sinxron üçün eyni seçim."""
    return (
        SyllabusVersion.objects.exclude(status=SyllabusStatus.ARCHIVED.value)
        .select_related(*_RELATED)
        .order_by("organization_id", "syllabus_id", "created_at")
    )


def refresh_offering_syllabus_plan_hours(offering_ids, *, user=None, request=None) -> dict:
    """Bu açılışların sillabus versiyalarının plan saatını rəsmi saata gətirir → ``{"checked", "updated", …}``.

    Səssiz və ucuz: sillabusu olmayan açılışlar üçün TƏK sorğu; xəta əsas əməli (yük sətri, təyinat) geri
    qaytarmır — savepoint daxilində icra olunur, xəta loglanır və ``error=1`` qaytarılır.
    """
    ids = {offering_id for offering_id in (offering_ids or ()) if offering_id}
    if not ids:
        return {}
    try:
        with transaction.atomic():
            return _refresh(ids, user=user, request=request)
    except Exception:  # noqa: BLE001 — sinxronun əsas yazısı dayanmamalıdır
        logger.exception("syllabus plan hours refresh failed for %s offerings", len(ids))
        return {"error": 1}


def _refresh(ids, *, user, request) -> dict:
    counts: Counter = Counter()
    memo: dict = {}
    for version in versions_queryset().filter(syllabus__offering_id__in=list(ids)):
        counts["checked"] += 1
        stored = norm(version.plan_hours)
        expected = expected_plan_hours(version.syllabus, memo)
        key, fix = classify(version, stored, expected)
        if not fix:
            counts[key.split(":", 1)[0]] += 1
            continue
        if write_fix(version, stored, expected, reason=REASON_SYNC, user=user, request=request):
            counts["updated"] += 1
    return dict(counts)


__all__ = [
    "EDITABLE",
    "REASON_COMMAND",
    "REASON_SYNC",
    "classify",
    "expected_plan_hours",
    "norm",
    "refresh_offering_syllabus_plan_hours",
    "versions_queryset",
    "write_fix",
]
