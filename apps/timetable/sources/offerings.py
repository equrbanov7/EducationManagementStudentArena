"""Əhatədəki açılışlar → «kurs vahidləri»: növ üzrə saat + növ üzrə müəllim.

SAAT (``CourseOffering.lesson_hours`` ŞİŞİRDİLMİŞ cəmdir — işlədilmir) mənbə sırası:

1. qrupun AKTİV tələbələrinin kurikulumu (çoxluq) — tələbənin real planı;
2. ixtisasın (qrupun pilləsinə uyğun proqramın) TƏSDİQLƏNMİŞ ən yeni planı;
3. fənnin istənilən təsdiqlənmiş planı (``plan_hours.plan_hours_for_subject`` geri çəkilməsi);
4. kafedra tapşırığının sətri (``*_plan``, yoxdursa ``*_total``) —
   ``plan_hours.workload_hours_for_offering`` ilə eyni.

Hamısı TOPLU sorğularladır (açılış başına sorğu yoxdur).

MÜƏLLİM (bölünmüş tədris): əsas mənbə ``apps.workload.public.teachers_for_offerings``
(dərs yükü modulunun TOPLU müqaviləsi): mühazirəçi = jurnal sahibi
(``offering.instructor``), yoxdursa yükün mühazirəçisi; seminar/lab müəllimləri
bölgüdən. Bir fəaliyyətə bir neçə müəllim bölünübsə — ``groups_note`` mətnində qrup
adı axtarılır, tapılmasa sətrin qrup sırası ilə paylanır. Müqavilə əlçatmazdırsa
eyni qayda tapşırıq sətirlərinin birbaşa oxunması ilə tətbiq olunur (get_model).
Bölgü yoxdursa → ``offering.instructor`` (bütün növlər).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from django.apps import apps as django_apps

from ..constants import KIND_LAB, KIND_LECTURE, KIND_SEMINAR, KINDS

logger = logging.getLogger(__name__)

_HOUR_FIELDS = ((KIND_LECTURE, "lecture_hours"), (KIND_SEMINAR, "seminar_hours"), (KIND_LAB, "lab_hours"))


@dataclass
class CourseUnit:
    offering_id: str
    group_id: str
    subject_id: str
    subject_code: str
    subject_name: str
    instructor_id: int | None
    hours: dict = field(default_factory=dict)
    hours_source: str = ""
    teachers: dict = field(default_factory=dict)
    row_id: str = ""
    row_groups: tuple = ()
    union_count: int = 1


def _hours_of(row, fields=_HOUR_FIELDS) -> dict:
    out = {}
    for kind, name in fields:
        value = int(row.get(name) or 0)
        if value > 0:
            out[kind] = value
    return out


def _plan_maps(organization, subject_ids, curriculum_ids, unit_degrees):
    """(kurikulum, fənn) / (proqram, fənn) / fənn → saat xəritələri."""
    Row = django_apps.get_model("registrar", "CurriculumSubject")
    Program = django_apps.get_model("registrar", "Program")
    own = {}
    if curriculum_ids:
        for row in (
            Row.objects.filter(organization=organization, curriculum_id__in=curriculum_ids, subject_id__in=subject_ids)
            .order_by("semester_number", "pk")
            .values("curriculum_id", "subject_id", "lecture_hours", "seminar_hours", "lab_hours")
        ):
            key = (str(row["curriculum_id"]), str(row["subject_id"]))
            hours = _hours_of(row)
            if hours and key not in own:
                own[key] = hours
    programs: dict = {}
    for row in Program.objects.filter(organization=organization, specialty_unit_id__in=list(unit_degrees)).values(
        "pk", "specialty_unit_id", "degree_level"
    ):
        programs.setdefault((str(row["specialty_unit_id"]), row["degree_level"]), []).append(str(row["pk"]))
    by_program, by_subject = {}, {}
    for row in (
        Row.objects.filter(organization=organization, subject_id__in=subject_ids, curriculum__status="approved")
        .order_by("-curriculum__admission_year", "-curriculum__version", "semester_number", "pk")
        .values("curriculum__program_id", "subject_id", "lecture_hours", "seminar_hours", "lab_hours")
    ):
        hours = _hours_of(row)
        if not hours:
            continue
        by_program.setdefault((str(row["curriculum__program_id"]), str(row["subject_id"])), hours)
        by_subject.setdefault(str(row["subject_id"]), hours)
    return own, programs, by_program, by_subject


def _task_rows(organization, period, subject_ids, group_ids):
    """(fənn, qrup) → tapşırıq sətri + fəaliyyət bölgüləri (get_model — workload import edilmir)."""
    try:
        TaskRow = django_apps.get_model("workload", "TeachingTaskRow")
        Assignment = django_apps.get_model("workload", "TeacherAssignment")
    except LookupError:
        return {}, {}
    rows = {
        str(row["pk"]): row
        for row in TaskRow.objects.filter(organization=organization, period=period, subject_id__in=subject_ids)
        .order_by("-updated_at", "pk")
        .values(
            "pk",
            "subject_id",
            "union_count",
            "lecture_plan",
            "lecture_total",
            "seminar_plan",
            "seminar_total",
            "lab_plan",
            "lab_total",
        )
    }
    through = TaskRow.groups.through
    members: dict = {}
    for link in through.objects.filter(teachingtaskrow_id__in=list(rows)).values("teachingtaskrow_id", "orgunit_id"):
        members.setdefault(str(link["teachingtaskrow_id"]), []).append(str(link["orgunit_id"]))
    by_pair: dict = {}
    for row_id, row in rows.items():
        row["groups"] = tuple(sorted(gid for gid in members.get(row_id, []) if gid in group_ids))
        for gid in row["groups"]:
            by_pair.setdefault((str(row["subject_id"]), gid), row)
    assignments: dict = {}
    for item in (
        Assignment.objects.filter(organization=organization, row_id__in=list(rows), teacher__isnull=False)
        .order_by("row_id", "activity", "created_at", "pk")
        .values("row_id", "teacher_id", "activity", "hours", "groups_note")
    ):
        assignments.setdefault(str(item["row_id"]), {}).setdefault(item["activity"], []).append(item)
    return by_pair, assignments


def _row_hours(row) -> dict:
    out = {}
    for kind in KINDS:
        value = int(row.get(f"{kind}_plan") or 0) or int(row.get(f"{kind}_total") or 0)
        if value > 0:
            out[kind] = value
    return out


def _norm(text) -> str:
    return " ".join(str(text or "").casefold().split())


def _pick_teacher(items, group_name, row_groups, group_id):
    teachers = list(dict.fromkeys(item["teacher_id"] for item in items))
    if not teachers:
        return None
    if len(teachers) == 1:
        return teachers[0]
    name = _norm(group_name)
    for item in items:
        if name and name in _norm(item["groups_note"]):
            return item["teacher_id"]
    position = row_groups.index(group_id) if group_id in row_groups else 0
    return teachers[position % len(teachers)]


def _workload_teachers(offerings):
    """``apps.workload.public.teachers_for_offerings`` — yoxdursa/xəta verirsə ``None``."""
    try:
        from apps.workload import public as workload_public
    except ImportError:  # pragma: no cover — modul həmişə quraşdırılıb
        return None
    bulk = getattr(workload_public, "teachers_for_offerings", None)
    if bulk is None:
        return None
    try:
        return bulk(offerings)
    except Exception:  # pragma: no cover — müqavilə xətası generatoru dayandırmamalıdır
        logger.warning("timetable: teachers_for_offerings xətası — birbaşa oxuya keçilir", exc_info=True)
        return None


def _teachers_from_api(described, items, info, row_groups):
    """Müqavilənin nəticəsi → ``{kind: user_id}`` (bir neçə seminar müəllimi → qrupa görə seçim)."""
    lecture = described.get("lecture")
    out = {KIND_LECTURE: getattr(lecture, "pk", None)}
    for kind in (KIND_SEMINAR, KIND_LAB):
        people = [user.pk for user in described.get(kind) or []]
        if len(people) <= 1:
            out[kind] = people[0] if people else None
            continue
        pool = [item for item in items.get(kind, []) if item["teacher_id"] in people]
        out[kind] = _pick_teacher(pool, info.name, row_groups, info.id) if pool else people[0]
    return out


def load_units(organization, period, infos: dict) -> list:
    """Əhatənin açılışları (qrup adı + fənn kodu sırası ilə) → ``CourseUnit`` siyahısı."""
    Offering = django_apps.get_model("registrar", "CourseOffering")
    offerings = list(
        Offering.objects.filter(organization=organization, period=period, group_id__in=list(infos), is_active=True)
        .select_related("subject")
        .order_by("group__name", "subject__code", "pk")
    )
    subject_ids = sorted({str(o.subject_id) for o in offerings})
    curricula = sorted({info.curriculum_id for info in infos.values() if info.curriculum_id})
    unit_degrees = {info.unit_id: info.degree for info in infos.values() if info.unit_id}
    own, programs, by_program, by_subject = _plan_maps(organization, subject_ids, curricula, unit_degrees)
    by_pair, assignments = _task_rows(organization, period, subject_ids, set(infos))
    api = _workload_teachers(offerings)
    units = []
    for offering in offerings:
        info = infos[str(offering.group_id)]
        subject = str(offering.subject_id)
        row = by_pair.get((subject, info.id))
        hours, source = {}, ""
        if info.curriculum_id and (info.curriculum_id, subject) in own:
            hours, source = own[(info.curriculum_id, subject)], "curriculum"
        if not hours:
            for program_id in programs.get((info.unit_id, info.degree), []):
                if (program_id, subject) in by_program:
                    hours, source = by_program[(program_id, subject)], "program_plan"
                    break
        if not hours and subject in by_subject:
            hours, source = by_subject[subject], "any_plan"
        described = api.get(offering.pk) if api is not None else None
        if not hours and described is not None:
            hours = {kind: int(value) for kind, value in (described.get("hours") or {}).items() if int(value or 0) > 0}
            source = "task_row" if hours else ""
        if not hours and row is not None:
            hours, source = _row_hours(row), "task_row"
        items = assignments.get(str(row["pk"]), {}) if row is not None else {}
        row_groups = tuple(row["groups"]) if row is not None else ()
        if described is not None:
            teachers = _teachers_from_api(described, items, info, row_groups)
        else:
            teachers = {kind: _pick_teacher(items.get(kind, []), info.name, row_groups, info.id) for kind in KINDS}
            # Jurnal sahibi mühazirəçidir (workload spec §11.3) — bölgüdən ÜSTÜNDÜR.
            teachers[KIND_LECTURE] = offering.instructor_id or teachers[KIND_LECTURE]
        lecture = teachers[KIND_LECTURE] or offering.instructor_id
        teachers[KIND_LECTURE] = lecture
        teachers[KIND_SEMINAR] = teachers[KIND_SEMINAR] or lecture
        teachers[KIND_LAB] = teachers[KIND_LAB] or teachers[KIND_SEMINAR]
        units.append(
            CourseUnit(
                offering_id=str(offering.pk),
                group_id=info.id,
                subject_id=subject,
                subject_code=getattr(offering.subject, "code", "") or "",
                subject_name=getattr(offering.subject, "name", "") or "",
                instructor_id=offering.instructor_id,
                hours=dict(hours),
                hours_source=source,
                teachers=teachers,
                row_id=str(row["pk"]) if row is not None else "",
                row_groups=row_groups,
                union_count=int(row["union_count"] or 1) if row is not None else 1,
            )
        )
    return units


__all__ = ["CourseUnit", "load_units"]
