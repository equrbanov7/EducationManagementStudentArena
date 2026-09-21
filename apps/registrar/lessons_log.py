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

MODUL BÖLGÜSÜ (2026-09-21, modul-ölçü qapısı): dövr / tədris ili / aralıq həlli
``lessons_log_periods.py``-da, KPI aqreqatı ``lessons_log_totals.py``-dadır;
hər ikisinin adları buradan yenidən ixrac olunur (``service.*`` yolu dəyişmir).
"""

from __future__ import annotations

import datetime as _dt

from django.db.models import Count, Min, Q, Sum
from django.utils import timezone
from django.utils.translation import pgettext

from apps.registrar.lessons_log_periods import (  # noqa: F401 — geri-uyğun re-export
    ALL,
    RANGE_CUSTOM,
    RANGE_LABELS,
    RANGE_MONTH,
    RANGE_SEMESTER,
    RANGE_TODAY,
    RANGE_WEEK,
    RANGE_YEAR,
    SEASON_AUTUMN,
    SEASON_LABELS,
    SEASON_SPRING,
    SEASON_SUMMER,
    period_catalog,
    resolve_range,
    resolve_selection,
    season_of,
    select_periods,
    window_for_periods,
    year_options,
)
from apps.registrar.lessons_log_totals import (  # noqa: F401 — geri-uyğun re-export
    LATE_AFTER_HOURS,
    TOTALS_CACHE_TTL,
    range_totals,
    totals_cache_key,
)
from apps.registrar.models import AttendanceStatus, Lesson, LessonKind, LessonMark
from apps.registrar.models.catalog_meta import EducationForm

_CTX = "registrar.lessons_log"


#: Nəzarət görünüşünün icazə açarları.
#:
#: * ``journal.roster`` — kafedra müdiri / dekanlıq / RİM (mövcud açar);
#: * ``journal.lessons_unit`` (2026-09-08, sahib) — LABORANT: öz kafedrasının
#:   müəllimlərinin dərs izinə OXU-ONLY baxış. Ayrıca açardır ki, siyahı
#:   idarəsi (`journal.roster`) hüququ verilməsin.
#:
#: Hər iki açarın əhatəsi ``Membership.scope_unit`` alt-ağacıdır; aktor iki
#: açarın da əhatəsini daşıyırsa dərslər BİRLƏŞİR (OR).
SUPERVISOR_PERMISSION = "journal.roster"
UNIT_VIEW_PERMISSION = "journal.lessons_unit"
SUPERVISOR_PERMISSIONS = (SUPERVISOR_PERMISSION, UNIT_VIEW_PERMISSION)


#: «Gec yazılıb» həddi (48 saat) — `lessons_log_totals`-da təyin olunur
#: (F-13 üçün KPI aqreqatı ayrıca modula çıxarılıb, modul-ölçü qapısı).

#: Bir səhifədə göstərilən maksimum dərs (dizayn: «İlk 90 dərs göstərilir»).
ROW_CAP = 90


#: Jurnal qeydinin vəziyyəti — `core.ui.status_catalog` `journal_note` ailəsi.
NOTE_ON_TIME = "on_time"
NOTE_LATE = "late"
NOTE_EMPTY = "empty"


# --------------------------------------------------------------------------- #
# Əhatə
# --------------------------------------------------------------------------- #


def _supervision_scopes(user, organization) -> list:
    """Nəzarət açarlarının struktur əhatələri (yalnız əhatəsi olanlar)."""
    from django.apps import apps as django_apps

    org_unit_model = django_apps.get_model("organizations", "OrgUnit")
    scopes = []
    for permission in SUPERVISOR_PERMISSIONS:
        scope = org_unit_model.user_permission_scope(user, organization, permission)
        if scope.has_structure_access:
            scopes.append(scope)
    return scopes


def is_supervisor(user, organization) -> bool:
    """Nəzarət açarlarından biri aktora struktur əhatəsi verirmi."""
    return bool(_supervision_scopes(user, organization))


def scoped_lessons(user, organization, *, supervisor: bool):
    """Aktorun görə biləcəyi dərslərin queryset-i (fail-closed).

    Müəllim: ``instructor=user`` VƏ YA açılışın müəllimi özüdür (dərsin öz
    ``instructor``-u boş ola bilər — o zaman açılışınkı sayılır).
    Nəzarətçi: nəzarət açarlarının alt-ağaclarının BİRLƏŞMƏSİ; org-genişli
    əhatə varsa bütün təşkilat. Əhatəsiz nəzarətçi BOŞ nəticə alır.
    """
    queryset = Lesson.objects.filter(organization=organization)
    if not supervisor:
        return queryset.filter(Q(instructor=user) | Q(instructor__isnull=True, offering__instructor=user))
    scopes = _supervision_scopes(user, organization)
    if not scopes:
        return queryset.none()
    if any(scope.is_org_wide for scope in scopes):
        return queryset
    combined = Q()
    for scope in scopes:
        combined |= scope.unit_subtree_q(path_field="offering__group__path", id_field="offering__group__id")
    return queryset.filter(combined)


def education_form_options() -> list:
    return [{"value": str(value), "label": str(label)} for value, label in EducationForm.choices]


def apply_filters(lessons, *, q="", offering="", kind="", group="", teacher="", form="", supervisor=False):
    """Bölmə VƏ CSV üçün EYNİ süzgəc zənciri (tək mənbə).

    ``teacher`` yalnız nəzarətçidə tətbiq olunur — adi müəllimin sorğusunda
    parametr SƏSSİZ keçilir (panel), CSV isə onu ayrıca 403 ilə rədd edir.
    """
    if q:
        lessons = lessons.filter(
            Q(topic__icontains=q)
            | Q(offering__subject__name__icontains=q)
            | Q(offering__subject__code__icontains=q)
            | Q(offering__group__name__icontains=q)
        )
    if offering:
        lessons = lessons.filter(offering_id=offering)
    if kind:
        lessons = lessons.filter(kind=kind)
    if group:
        lessons = lessons.filter(offering__group__name=group)
    if form and form in {value for value, _label in EducationForm.choices}:
        # Təhsil forması qrupun metadatasındadır (`OrgUnit.settings.education_form`).
        lessons = lessons.filter(offering__group__settings__education_form=form)
    if teacher and supervisor:
        lessons = lessons.filter(Q(instructor_id=teacher) | Q(instructor__isnull=True, offering__instructor=teacher))
    return lessons


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
    from apps.syllabus import public as syllabus_services
    from apps.syllabus.public import SectionKey

    syllabus = syllabus_services.syllabus_for_offering_obj(offering)
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
            # ⚠️ Aşağıdakı `teacher` buna geri çəkilir və bu NORMAL yoldur
            # (`Lesson.instructor` yalnız bölünmüş fənndə dolur). Siyahıdan
            # düşəndə hər sətir bir sorğu edirdi — CSV eksportunda 5000.
            "offering__instructor",
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
    "ALL",
    "LATE_AFTER_HOURS",
    "NOTE_EMPTY",
    "NOTE_LATE",
    "NOTE_ON_TIME",
    "RANGE_CUSTOM",
    "RANGE_LABELS",
    "RANGE_SEMESTER",
    "ROW_CAP",
    "SEASON_AUTUMN",
    "SEASON_LABELS",
    "SEASON_SPRING",
    "SEASON_SUMMER",
    "SUPERVISOR_PERMISSION",
    "SUPERVISOR_PERMISSIONS",
    "UNIT_VIEW_PERMISSION",
    "apply_filters",
    "build_rows",
    "coverage_for_offering",
    "csv_rows",
    "education_form_options",
    "is_supervisor",
    "marks_by_lesson",
    "note_state",
    "offering_totals",
    "period_catalog",
    "range_totals",
    "resolve_range",
    "resolve_selection",
    "scoped_lessons",
    "season_of",
    "select_periods",
    "window_for_periods",
    "year_options",
]
