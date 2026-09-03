"""Ekran 21 «Keçilmiş dərslər» — müəllimin (və nəzarətçinin) dərs izi.

Dizayn: ``docs/design/handoff_full/design/21 Muellim - Kecilmish dersler.dc.html``
+ ``README.md`` §5/21. Bu OXU-ONLY səthdir: model dəyişikliyi YOXDUR, bütün
məlumat mövcud ``Lesson`` / ``LessonMark`` sətirlərindən hesablanır.

ƏSAS QAYDALAR
-------------
* **Əhatə (README §8/8):** müəllim YALNIZ öz dərslərini görür. ``journal.roster``
  daşıyan aktor (kafedra müdiri / dekanlıq / RİM) öz struktur alt-ağacını görür
  və ``teacher`` filtrini aça bilir. Əhatəsiz aktor BOŞ nəticə alır — bütün
  universitet AÇILMIR.
* **Aqreqasiya aşağıdan yuxarı (§8/13):** heç bir yekun rəqəm SAXLANILMIR.
* **Sorğu büdcəsi:** dövr üzrə 4 sorğu (aqreqat sətirlər, davamiyyət aqreqatı,
  səhifə sətirləri, səhifənin xana aqreqatı) + filtr seçiciləri. Sətir-sətir
  sorğu YOXDUR (test ``CaptureQueriesContext`` ilə kilidləyir).
* **«Gec yazılıb» tərifi:** dərsin İLK xanası dərs tarixindən
  :data:`LATE_AFTER_HOURS` saat sonra yazılıbsa. Model dəyişikliyi tələb
  etmir — ``LessonMark.created_at`` vs ``Lesson.date``.

Modul sərhədi: ``apps.organizations`` statik İMPORT EDİLMİR (``module_deps``
qapısı) — struktur əhatəsi ``journal_scope.permission_scope_q`` üzərindən gəlir.
"""

from __future__ import annotations

import datetime as _dt

from django.db.models import Count, Min, Q, Sum
from django.utils import timezone
from django.utils.translation import pgettext, pgettext_lazy

from apps.registrar.journal_scope import permission_scope_q
from apps.registrar.models import AttendanceStatus, Lesson, LessonKind, LessonMark

_CTX = "registrar.lessons_log"

#: Nəzarət görünüşünün icazə açarı (mövcud — yeni açar YARADILMIR).
SUPERVISOR_PERMISSION = "journal.roster"

#: «Gec yazılıb» həddi — dizayn: «dərsdən 48 saat sonra».
LATE_AFTER_HOURS = 48

#: Bir səhifədə göstərilən maksimum dərs (dizayn: «İlk 90 dərs göstərilir»).
ROW_CAP = 90

#: Dövr çipləri (dizayn `RANGES`).
RANGE_TODAY = "today"
RANGE_WEEK = "week"
RANGE_MONTH = "month"
RANGE_SEMESTER = "semester"
RANGE_YEAR = "year"
RANGE_CUSTOM = "custom"

RANGE_LABELS = (
    (RANGE_TODAY, pgettext_lazy(_CTX, "Bu gün")),
    (RANGE_WEEK, pgettext_lazy(_CTX, "Bu həftə")),
    (RANGE_MONTH, pgettext_lazy(_CTX, "Bu ay")),
    (RANGE_SEMESTER, pgettext_lazy(_CTX, "Semestr")),
    (RANGE_YEAR, pgettext_lazy(_CTX, "İl")),
    (RANGE_CUSTOM, pgettext_lazy(_CTX, "Seçilmiş aralıq")),
)

#: Jurnal qeydinin vəziyyəti — `core.ui.status_catalog` `journal_note` ailəsi.
NOTE_ON_TIME = "on_time"
NOTE_LATE = "late"
NOTE_EMPTY = "empty"


# --------------------------------------------------------------------------- #
# Əhatə
# --------------------------------------------------------------------------- #


def is_supervisor(user, organization) -> bool:
    """``journal.roster`` aktora struktur əhatəsi verirmi (nəzarət görünüşü)."""
    from django.apps import apps as django_apps

    org_unit_model = django_apps.get_model("organizations", "OrgUnit")
    scope = org_unit_model.user_permission_scope(user, organization, SUPERVISOR_PERMISSION)
    return bool(scope.has_structure_access)


def scoped_lessons(user, organization, *, supervisor: bool):
    """Aktorun görə biləcəyi dərslərin queryset-i (fail-closed).

    Müəllim: ``instructor=user`` VƏ YA açılışın müəllimi özüdür (dərsin öz
    ``instructor``-u boş ola bilər — o zaman açılışınkı sayılır).
    Nəzarətçi: ``journal.roster`` alt-ağacı.
    """
    queryset = Lesson.objects.filter(organization=organization)
    if not supervisor:
        return queryset.filter(Q(instructor=user) | Q(instructor__isnull=True, offering__instructor=user))
    return queryset.filter(
        permission_scope_q(
            user,
            organization,
            SUPERVISOR_PERMISSION,
            path_field="offering__group__path",
            id_field="offering__group__id",
        )
    )


# --------------------------------------------------------------------------- #
# Dövr
# --------------------------------------------------------------------------- #


def _parse_date(value):
    try:
        return _dt.date.fromisoformat((value or "").strip())
    except (TypeError, ValueError):
        return None


def resolve_range(*, key: str, start_raw: str = "", end_raw: str = "", period=None, today=None) -> dict:
    """Seçilmiş dövr → ``{"key", "start", "end"}`` (hər ikisi daxil olmaqla)."""
    today = today or timezone.localdate()
    key = key if key in dict(RANGE_LABELS) else RANGE_SEMESTER
    if key == RANGE_CUSTOM:
        start = _parse_date(start_raw) or today - _dt.timedelta(days=30)
        end = _parse_date(end_raw) or today
        if end < start:
            start, end = end, start
        return {"key": key, "start": start, "end": end}
    if key == RANGE_TODAY:
        return {"key": key, "start": today, "end": today}
    if key == RANGE_WEEK:
        monday = today - _dt.timedelta(days=today.weekday())
        return {"key": key, "start": monday, "end": monday + _dt.timedelta(days=6)}
    if key == RANGE_MONTH:
        first = today.replace(day=1)
        return {"key": key, "start": first, "end": today}
    if key == RANGE_YEAR:
        # Akademik il: sentyabrdan başlayır (payız semestri) — təqvim ili deyil.
        year = today.year if today.month >= 9 else today.year - 1
        return {"key": key, "start": _dt.date(year, 9, 1), "end": _dt.date(year + 1, 8, 31)}
    start = getattr(period, "start_date", None) or today - _dt.timedelta(days=120)
    end = getattr(period, "end_date", None) or today
    return {"key": key, "start": start, "end": max(end, start)}


# --------------------------------------------------------------------------- #
# Qeyd statusu
# --------------------------------------------------------------------------- #


def note_state(*, lesson_date, marks_count: int, first_mark) -> str:
    """`on_time` / `late` / `empty` — dizayn §21 «Jurnal qeydi» sütunu."""
    if not marks_count:
        return NOTE_EMPTY
    if first_mark is None:
        return NOTE_ON_TIME
    written = timezone.localtime(first_mark).date() if timezone.is_aware(first_mark) else first_mark.date()
    if (written - lesson_date) > _dt.timedelta(hours=LATE_AFTER_HOURS):
        return NOTE_LATE
    return NOTE_ON_TIME


# --------------------------------------------------------------------------- #
# Aqreqatlar (KPI) — SAXLANILMIR, hər dəfə hesablanır
# --------------------------------------------------------------------------- #


def range_totals(lessons_qs) -> dict:
    """Dövr üzrə KPI-lar — İKİ sorğu (dərs sətirləri + xana aqreqatı)."""
    rows = list(
        lessons_qs.annotate(marks_count=Count("marks"), first_mark=Min("marks__created_at")).values_list(
            "id", "date", "hours", "marks_count", "first_mark"
        )
    )
    total = len(rows)
    hours = sum(int(row[2] or 0) for row in rows)
    empty = 0
    late = 0
    for _pk, lesson_date, _hours, marks_count, first_mark in rows:
        state = note_state(lesson_date=lesson_date, marks_count=marks_count, first_mark=first_mark)
        if state == NOTE_EMPTY:
            empty += 1
        elif state == NOTE_LATE:
            late += 1

    attendance = LessonMark.objects.filter(lesson__in=lessons_qs.values("id")).aggregate(
        present=Count("id", filter=Q(status=AttendanceStatus.PRESENT)),
        absent=Count("id", filter=Q(status=AttendanceStatus.ABSENT)),
        excused=Count("id", filter=Q(status=AttendanceStatus.EXCUSED)),
        graded=Count("id", filter=Q(score__isnull=False)),
    )
    marked = int(attendance["present"] or 0) + int(attendance["absent"] or 0) + int(attendance["excused"] or 0)
    rate = int(round(int(attendance["present"] or 0) * 100 / marked)) if marked else 0
    return {
        "lessons": total,
        "hours": hours,
        "empty": empty,
        "late": late,
        "present": int(attendance["present"] or 0),
        "absent": int(attendance["absent"] or 0),
        "excused": int(attendance["excused"] or 0),
        "graded": int(attendance["graded"] or 0),
        "attendance_rate": rate,
    }


def marks_by_lesson(lesson_ids) -> dict:
    """``{lesson_id: {present, absent, excused, graded, total, first_mark}}`` — TƏK sorğu."""
    if not lesson_ids:
        return {}
    rows = (
        LessonMark.objects.filter(lesson_id__in=lesson_ids)
        .values("lesson_id")
        .annotate(
            present=Count("id", filter=Q(status=AttendanceStatus.PRESENT)),
            absent=Count("id", filter=Q(status=AttendanceStatus.ABSENT)),
            excused=Count("id", filter=Q(status=AttendanceStatus.EXCUSED)),
            graded=Count("id", filter=Q(score__isnull=False)),
            total=Count("id"),
            first_mark=Min("created_at"),
        )
    )
    return {row["lesson_id"]: row for row in rows}


# --------------------------------------------------------------------------- #
# Sillabus əhatəsi (mövzu planı ↔ keçilən mövzu)
# --------------------------------------------------------------------------- #


def _approved_week_topics(offering) -> list:
    """Təsdiqlənmiş sillabusun həftəlik mövzuları (yoxdursa boş siyahı).

    README §8/9: yalnız APPROVED versiya — baxışdakı yeni versiya SAYILMIR.
    """
    from apps.syllabus import services as syllabus_services
    from apps.syllabus.constants import SectionKey

    syllabus = syllabus_services.syllabus_for_offering(
        organization=offering.organization,
        offering_id=offering.id,
        subject_id=offering.subject_id,
        period_id=offering.period_id,
        instructor_id=offering.instructor_id,
    )
    if syllabus is None:
        return []
    version = syllabus_services.approved_version_for(syllabus)
    if version is None:
        return []
    data = syllabus_services.section_data_map(version).get(SectionKey.WEEK.value) or {}
    topics = []
    for row in data.get("rows") or []:
        if not isinstance(row, dict):
            continue
        topic = (row.get("topic") or "").strip()
        if topic:
            topics.append(topic)
    return topics


def coverage_for_offering(offering, *, held_topics) -> dict:
    """«Sillabus mövzu əhatəsi» zolağı — planlaşdırılan ↔ keçilən.

    Sillabus yoxdursa ``planned=0`` və ``has_syllabus=False`` qaytarılır: ekran
    zolağı gizlədir və «təsdiqlənmiş sillabus yoxdur» qeydini göstərir.
    """
    planned = _approved_week_topics(offering)
    normalised = {topic.casefold() for topic in held_topics if topic}
    covered = [topic for topic in planned if topic.casefold() in normalised]
    percent = int(round(len(covered) * 100 / len(planned))) if planned else 0
    return {
        "has_syllabus": bool(planned),
        "planned": len(planned),
        "covered": len(covered),
        "percent": percent,
        "remaining": [topic for topic in planned if topic.casefold() not in normalised],
    }


# --------------------------------------------------------------------------- #
# Sətirlər
# --------------------------------------------------------------------------- #


def _room_label(room) -> str:
    if room is None:
        return ""
    name = (getattr(room, "name", "") or "").strip()
    building = (getattr(room, "building", "") or "").strip()
    if name and building:
        return f"{name} ({building})"
    return name or building


def build_rows(lessons_qs, *, limit=ROW_CAP) -> list:
    """Səhifə sətirləri — İKİ sorğu (dərslər + xana aqreqatı)."""
    lessons = list(
        lessons_qs.select_related(
            "offering",
            "offering__subject",
            "offering__group",
            "offering__period",
            "instructor",
            "room",
        ).order_by("-date", "-start_time", "-created_at")[:limit]
    )
    stats = marks_by_lesson([lesson.id for lesson in lessons])
    kind_labels = dict(LessonKind.choices)
    rows = []
    for lesson in lessons:
        bucket = stats.get(lesson.id, {})
        marks_total = int(bucket.get("total") or 0)
        teacher = lesson.instructor or getattr(lesson.offering, "instructor", None)
        rows.append(
            {
                "id": str(lesson.id),
                "offering_id": str(lesson.offering_id),
                "date": lesson.date,
                "start_time": lesson.start_time,
                "end_time": lesson.end_time,
                "kind": lesson.kind,
                "kind_label": kind_labels.get(lesson.kind, lesson.kind),
                "topic": lesson.topic or "",
                "has_topic": bool(lesson.topic),
                "hours": int(lesson.hours or 0),
                "room": _room_label(lesson.room),
                "subject_code": getattr(lesson.offering.subject, "code", "") or "",
                "subject_name": getattr(lesson.offering.subject, "name", "") or "",
                "group": getattr(getattr(lesson.offering, "group", None), "name", "") or "",
                "teacher": (teacher.get_full_name() or teacher.username) if teacher else "",
                "teacher_id": str(getattr(teacher, "id", "") or ""),
                "present": int(bucket.get("present") or 0),
                "absent": int(bucket.get("absent") or 0),
                "excused": int(bucket.get("excused") or 0),
                "graded": int(bucket.get("graded") or 0),
                "marks_total": marks_total,
                "attendance_label": "%s / %s" % (int(bucket.get("present") or 0), marks_total),
                "note": note_state(
                    lesson_date=lesson.date,
                    marks_count=marks_total,
                    first_mark=bucket.get("first_mark"),
                ),
                "is_legacy": bool(lesson.is_legacy_synthesised),
            }
        )
    return rows


def csv_rows(rows) -> list:
    """CSV ixracının sətirləri (başlıq daxil) — Excel üçün ; ayırıcı yox, ',' ."""
    header = [
        pgettext(_CTX, "Tarix"),
        pgettext(_CTX, "Saat"),
        pgettext(_CTX, "Müəllim"),
        pgettext(_CTX, "Fənn kodu"),
        pgettext(_CTX, "Fənn"),
        pgettext(_CTX, "Qrup"),
        pgettext(_CTX, "Mövzu"),
        pgettext(_CTX, "Dərsin tipi"),
        pgettext(_CTX, "Otaq"),
        pgettext(_CTX, "İştirak"),
        pgettext(_CTX, "Qayıb"),
        pgettext(_CTX, "Üzrlü"),
        pgettext(_CTX, "Qiymətləndirilib"),
        pgettext(_CTX, "Akademik saat"),
        pgettext(_CTX, "Jurnal qeydi"),
    ]
    note_labels = {
        NOTE_ON_TIME: pgettext(_CTX, "Vaxtında yazılıb"),
        NOTE_LATE: pgettext(_CTX, "Gec yazılıb"),
        NOTE_EMPTY: pgettext(_CTX, "Jurnal boşdur"),
    }
    out = [header]
    for row in rows:
        out.append(
            [
                row["date"].isoformat(),
                row["start_time"].strftime("%H:%M") if row["start_time"] else "",
                row["teacher"],
                row["subject_code"],
                row["subject_name"],
                row["group"],
                row["topic"],
                str(row["kind_label"]),
                row["room"],
                row["present"],
                row["absent"],
                row["excused"],
                row["graded"],
                row["hours"],
                note_labels.get(row["note"], row["note"]),
            ]
        )
    return out


def offering_totals(lessons_qs) -> list:
    """Açılış üzrə xülasə — TƏK sorğu (aqreqat), saxlanılmır."""
    return list(
        lessons_qs.values("offering_id", "offering__subject__code", "offering__subject__name", "offering__group__name")
        .annotate(lessons=Count("id"), hours=Sum("hours"))
        .order_by("offering__subject__name")
    )


__all__ = [
    "LATE_AFTER_HOURS",
    "NOTE_EMPTY",
    "NOTE_LATE",
    "NOTE_ON_TIME",
    "RANGE_CUSTOM",
    "RANGE_LABELS",
    "RANGE_SEMESTER",
    "ROW_CAP",
    "SUPERVISOR_PERMISSION",
    "build_rows",
    "coverage_for_offering",
    "csv_rows",
    "is_supervisor",
    "marks_by_lesson",
    "note_state",
    "offering_totals",
    "range_totals",
    "resolve_range",
    "scoped_lessons",
]
