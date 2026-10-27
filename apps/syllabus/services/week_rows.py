"""Bir çox açılışın TƏSDİQLƏNMİŞ həftəlik planı — TOPLU (sabit sayda sorğu).

Jurnalın mövzu göstərişi (``Lesson.syllabus_week`` → sətrin mövzusu) bir neçə açılışın dərslərini eyni
anda göstərən səthlərdə («Keçilmiş dərslər», CSV ixracı, backfill əmri) lazımdır. ``syllabus_for_offering``
hər açılış üçün ayrıca sorğudur; burada eyni pilləli seçim (açılış → paylaşım (sahib 2026-10-27) →
fənn+semestr → fənn+müəllim «baza») namizədlərdən Python-da həll olunur, sonra təsdiqlənmiş versiyalar və
onların ``week`` bölmələri toplu oxunur — açılış sayından asılı olmayaraq ≤ 4 sorğu.

Sətir nömrəsi (``week``) ``week.rows`` siyahısındakı lüğət sətirlərinin 1-dən sırasıdır — boş mövzulu
sətirlər də sayılır (sənəddəki «1. Mövzu …» nömrəsi ilə eyni, bax ``document._week_line``).

⚠️ Modul-sərhəd: ``apps.registrar`` İDXAL EDİLMİR — açılış obyektindən yalnız ``id``, ``organization_id``,
``subject_id``, ``period_id``, ``instructor_id`` oxunur.
"""

from __future__ import annotations

from django.db.models import Q

from ..constants import SectionKey, SyllabusStatus
from ..models import Syllabus, SyllabusSection, SyllabusVersion


def plan_rows(data) -> list[dict]:
    """``week`` bölməsinin ``data``-sından lüğət sətirləri (sıra saxlanılır)."""
    rows = (data or {}).get("rows") if isinstance(data, dict) else None
    return [row for row in (rows or []) if isinstance(row, dict)]


def _pick(offering, candidates, shared=None) -> int | None:
    """``syllabus_for_offering`` pillə sırası: açılış → paylaşım → fənn+semestr → fənn+müəllim (baza)."""
    tiers = ([], [], [], [])
    for row in candidates:
        if row["organization_id"] != offering.organization_id:
            continue
        if row["offering_id"] is not None:
            if row["offering_id"] == offering.id:
                tiers[0].append(row)
            elif shared is not None and row["id"] == shared:
                tiers[1].append(row)
            continue
        if row["subject_id"] != offering.subject_id:
            continue
        if offering.period_id is not None and row["period_id"] == offering.period_id:
            tiers[2].append(row)
        elif (
            row["period_id"] is None
            and offering.instructor_id is not None
            and row["author_id"] == offering.instructor_id
        ):
            tiers[3].append(row)
    for tier in tiers:
        if tier:
            return tier[0]["id"]  # namizədlər artıq (fənn kodu, pk) sırası ilə gəlir
    return None


def approved_week_rows_for_offerings(offerings) -> dict:
    """``{offering_id: [sətir lüğəti, …]}`` — yalnız TƏSDİQLƏNMİŞ versiyası olan açılışlar daxildir."""
    offerings = [item for item in offerings if item is not None and getattr(item, "id", None) is not None]
    if not offerings:
        return {}
    from .sharing import shared_syllabus_ids

    org_ids = {item.organization_id for item in offerings}
    subject_ids = {item.subject_id for item in offerings if item.subject_id is not None}
    shared = shared_syllabus_ids([item.id for item in offerings])
    candidates = list(
        Syllabus.objects.filter(organization_id__in=org_ids, is_active=True)
        .filter(
            Q(offering_id__in=[item.id for item in offerings])
            | Q(offering__isnull=True, subject_id__in=subject_ids)
            | Q(pk__in=set(shared.values()))
        )
        .order_by("subject__code", "pk")
        .values(
            "id",
            "organization_id",
            "offering_id",
            "subject_id",
            "period_id",
            "author_id",
            "approved_version_id",
            "approved_version__status",
        )
    )
    by_id = {row["id"]: row for row in candidates}
    chosen = {item.id: _pick(item, candidates, shared.get(item.id)) for item in offerings}
    version_of: dict = {}
    stale = set()
    for syllabus_id in {value for value in chosen.values() if value is not None}:
        row = by_id[syllabus_id]
        if row["approved_version_id"] and row["approved_version__status"] == SyllabusStatus.APPROVED.value:
            version_of[syllabus_id] = row["approved_version_id"]
        else:
            stale.add(syllabus_id)
    if stale:
        # ``approved_version_for`` ilə eyni geri çəkilmə: göstərici köhnəlibsə statusa görə ən yeni təsdiqlənmiş.
        for syllabus_id, version_id in (
            SyllabusVersion.objects.filter(syllabus_id__in=stale, status=SyllabusStatus.APPROVED.value)
            .order_by("-major", "-minor")
            .values_list("syllabus_id", "id")
        ):
            version_of.setdefault(syllabus_id, version_id)
    if not version_of:
        return {}
    week_data = dict(
        SyllabusSection.objects.filter(
            version_id__in=set(version_of.values()), section_id=SectionKey.WEEK.value
        ).values_list("version_id", "data")
    )
    out = {}
    for offering_id, syllabus_id in chosen.items():
        version_id = version_of.get(syllabus_id)
        if version_id is not None:
            out[offering_id] = plan_rows(week_data.get(version_id))
    return out


__all__ = ["approved_week_rows_for_offerings", "plan_rows"]
