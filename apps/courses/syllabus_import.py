"""«Sillabusdan mövzuları götür» — sillabusun həftəlik planından kurs mövzuları (2026-10-18).

BAĞ: ``Course.syllabus`` (nullable FK → ``syllabus.Syllabus``, miqrasiya ``courses.0003``). Fənn sillabus
dosyesinin üzərindədir, ayrıca fənn sahəsi yoxdur. Bağ istəyə bağlıdır — idxal onsuz da işləyir.

OXU HÜQUQU sillabus modulunun öz qaydasıdır (``apps.syllabus.public.list_syllabi`` — fail-closed əhatə):
müəllif / açılışın müəllimi həmişə, digərləri ``syllabus.view`` + kafedra əhatəsi ilə. Dəstdən kənar
sillabus 404-dür. Mənbə versiya: qüvvədə olan TƏSDİQLƏNMİŞ versiya, yoxdursa cari (qaralama) versiya.

İDXAL (idempotent, bir tranzaksiya, kurs sətri kilidli):
* hər doldurulmuş həftə sətri → bir ``CourseTopic`` (başlıq = mövzu, təsvir = həftə + saatlar + təlim
  nəticələri), ``syllabus_week`` = həftə nömrəsi, sıra mövcud mövzuların SONUNA;
* mənbə ``CourseTopic.syllabus_source``-da saxlanılır (SET_NULL — sillabus silinsə mövzu qalır);
* atlanır: eyni adlı mövzu artıq varsa (böyük/kiçik hərf, boşluq, «İ/ı» fərqi nəzərə alınmır) və ya EYNİ
  sillabusun həmin həftəsi əvvəl idxal olunubsa (mövzu sonradan adlandırılsa belə təkrar yaradılmır).
  Başqa sillabusun eyni nömrəli həftəsi təkrar sayılmır — açar ``(sillabus, həftə)``-dür.
"""

from __future__ import annotations

import re
import uuid

from django.db import transaction
from django.db.models import Max
from django.utils.translation import pgettext

from apps.syllabus.public import (
    LESSON_HOUR_KINDS,
    has_broad_view_scope,
    list_syllabi,
    resolve_actor,
    section_data_map,
)
from core.ui import status_catalog

from .models import Course, CourseTopic

CTX = "courses.syllabus_import"
OPTION_LIMIT = 30
TITLE_MAX = 255
_OUTCOME_CODE = re.compile(r"TN\s*(\d+)", re.IGNORECASE)


def _kind_label(kind: str) -> str:
    return {
        "lecture": pgettext(CTX, "Mühazirə"),
        "seminar": pgettext(CTX, "Seminar"),
        "lab": pgettext(CTX, "Laboratoriya"),
    }.get(kind, kind)


def normalize_title(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:TITLE_MAX]


def title_key(value) -> str:
    # «İ».casefold() → «i̇» (i + U+0307): birləşən nöqtə atılır ki, «VBİS» ilə «vbis» eyni sayılsın;
    # nöqtəsiz «ı» (və «I».casefold() → «i») da «i»-yə endirilir — «Sınaq» ilə «SINAQ» eyni açardır.
    return normalize_title(value).casefold().replace("\u0307", "").replace("ı", "i")


def actor_for(request, course):
    return resolve_actor(request.user, course.organization, request=request)


def source_version(syllabus):
    """İdxalın mənbəyi: qüvvədə olan təsdiqlənmiş versiya, yoxdursa cari versiya."""
    return syllabus.approved_version or syllabus.current_version


def readable_syllabi(actor, organization):
    """Aktorun OXUYA BİLDİYİ aktiv sillabuslar (sillabus modulunun əhatə qaydası)."""
    return list_syllabi(organization=organization, actor=actor, sort="recent")


def get_readable_syllabus(actor, organization, syllabus_id):
    """Oxuna bilən sillabus və ya ``None`` (yanlış UUID də ``None`` — çağıran 404 qaytarır)."""
    try:
        pk = uuid.UUID(str(syllabus_id))
    except (TypeError, ValueError, AttributeError):
        return None
    return readable_syllabi(actor, organization).filter(pk=pk).first()


def describe(syllabus, *, user_id=None, linked_id=None) -> dict:
    version = source_version(syllabus)
    status = status_catalog.get("syllabus", version.status) if version is not None else None
    period = syllabus.period
    return {
        "id": str(syllabus.pk),
        "subject": syllabus.subject.name,
        "code": syllabus.subject.code,
        "period": period.name if period is not None else pgettext(CTX, "Baza sillabus (semestrsiz)"),
        "version": version.label if version is not None else "",
        "status": version.status if version is not None else "",
        "status_label": str(status.label) if status is not None else "",
        "status_class": status.css_class if status is not None else "ems-badge ems-badge--neutral",
        "is_approved": bool(syllabus.approved_version_id),
        "is_own": bool(
            user_id
            and (syllabus.author_id == user_id or (syllabus.offering_id and syllabus.offering.instructor_id == user_id))
        ),
        "is_linked": linked_id is not None and syllabus.pk == linked_id,
    }


def syllabus_options(actor, organization, *, search="", linked_id=None) -> list:
    """Seçici siyahısı: bağlı sillabus → öz sillabusları → digərləri (axtarışla bütün əhatə).

    Axtarış YOXDURSA və aktorun əhatəsi genişdirsə (kafedra müdiri, dekan) yalnız ÖZ sillabusları
    göstərilir — kafedranın yüzlərlə sillabusu ilk açılışda siyahını doldurmasın.
    """
    search = (search or "").strip()[:120]
    mine = not search and has_broad_view_scope(actor)
    queryset = list_syllabi(organization=organization, actor=actor, search=search, sort="recent", mine=mine)
    rows = [describe(item, user_id=actor.user_id, linked_id=linked_id) for item in queryset[:OPTION_LIMIT]]
    if linked_id is not None and not any(row["is_linked"] for row in rows):
        linked = readable_syllabi(actor, organization).filter(pk=linked_id).first()
        if linked is not None:
            rows.insert(0, describe(linked, user_id=actor.user_id, linked_id=linked_id))
    rows.sort(key=lambda row: (not row["is_linked"], not row["is_own"], not row["is_approved"]))
    return rows


def plan_rows(version) -> list:
    """Həftə sətirləri → ``[{"week", "title", "description", "hours"}]`` (boş mövzu sətri atlanır)."""
    if version is None:
        return []
    sections = section_data_map(version)
    week_rows = (sections.get("week") or {}).get("rows") or []
    outcomes = [normalize_title(text) for text in ((sections.get("out") or {}).get("outcomes") or [])]
    result = []
    for index, row in enumerate(week_rows, start=1):
        if not isinstance(row, dict):
            continue
        title = normalize_title(row.get("topic"))
        if not title:
            continue
        hours = []
        for kind in LESSON_HOUR_KINDS:
            try:
                value = int(row.get(kind) or 0)
            except (TypeError, ValueError):
                value = 0
            if value > 0:
                hours.append({"kind": kind, "label": _kind_label(kind), "hours": value})
        linked_outcomes = []
        for number in dict.fromkeys(_OUTCOME_CODE.findall(str(row.get("outcome") or ""))):
            position = int(number)
            if 1 <= position <= len(outcomes) and outcomes[position - 1]:
                linked_outcomes.append(f"TN{position} — {outcomes[position - 1]}")
        hours_text = " · ".join(
            pgettext(CTX, "%(kind)s: %(n)s saat") % {"kind": h["label"], "n": h["hours"]} for h in hours
        )
        # Həftə nömrəsi təsvirə yazılmır — `syllabus_week` mövzu sətrində «Həftə N» çipi kimi göstərilir.
        description = "\n".join(filter(None, [hours_text, *linked_outcomes]))
        result.append(
            {"week": index, "title": title, "description": description, "hours": hours, "hours_text": hours_text}
        )
    return result


def _existing(course, syllabus):
    """Kursun mövzu adları (hamısı) + YALNIZ bu sillabusdan əvvəl idxal olunmuş həftələr."""
    titles, weeks = set(), set()
    rows = CourseTopic.objects.filter(course=course).values_list("title", "syllabus_week", "syllabus_source_id")
    for title, week, source_id in rows:
        titles.add(title_key(title))
        if week and source_id == syllabus.pk:
            weeks.add(week)
    return titles, weeks


def _mark(rows, titles, weeks):
    for row in rows:
        row["exists"] = title_key(row["title"]) in titles or row["week"] in weeks
    return rows


def build_preview(course, syllabus, *, user_id=None) -> dict:
    rows = plan_rows(source_version(syllabus))
    titles, weeks = _existing(course, syllabus)
    _mark(rows, titles, weeks)
    new = sum(1 for row in rows if not row["exists"])
    return {
        "syllabus": describe(syllabus, user_id=user_id, linked_id=course.syllabus_id),
        "rows": rows,
        "counts": {"total": len(rows), "new": new, "existing": len(rows) - new},
    }


def apply_import(course, syllabus, *, link: bool) -> dict:
    """Yeni həftələri mövzu kimi yaradır; ``{"created", "skipped", "linked"}``. Bir tranzaksiyadır."""
    rows = plan_rows(source_version(syllabus))
    with transaction.atomic():
        locked = Course.objects.select_for_update().get(pk=course.pk)
        titles, weeks = _existing(locked, syllabus)
        order = CourseTopic.objects.filter(course=locked).aggregate(top=Max("order"))["top"] or 0
        to_create = []
        for row in _mark(rows, titles, weeks):
            if row["exists"]:
                continue
            order += 1
            titles.add(title_key(row["title"]))
            weeks.add(row["week"])
            to_create.append(
                CourseTopic(
                    course=locked,
                    title=row["title"],
                    description=row["description"],
                    order=order,
                    syllabus_week=row["week"],
                    syllabus_source=syllabus,
                )
            )
        CourseTopic.objects.bulk_create(to_create)
        linked = False
        if link and locked.syllabus_id != syllabus.pk:
            locked.syllabus = syllabus
            locked.save(update_fields=["syllabus", "updated_at"])
            linked = True
        elif to_create:
            locked.save(update_fields=["updated_at"])
    course.syllabus_id = locked.syllabus_id
    return {"created": len(to_create), "skipped": len(rows) - len(to_create), "linked": linked}


__all__ = [
    "actor_for",
    "apply_import",
    "build_preview",
    "get_readable_syllabus",
    "plan_rows",
    "readable_syllabi",
    "source_version",
    "syllabus_options",
]
