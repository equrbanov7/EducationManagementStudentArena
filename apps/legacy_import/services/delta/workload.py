"""Dərs yükü — legacy jurnalın müəllimi «Mənim dərs yüküm»də görsün (sahib 2026-10-23).

«Mənim dərs yüküm» ``TeacherAssignment``-dən (təsdiqlənmiş kafedra tapşırığı) qurulur, jurnal açılışından yox.
Ona görə müəllimi olan, amma HEÇ BİR tapşırıq sətrinin əhatə etmədiyi (fənn + semestr + qrup) legacy jurnalı
tədris şöbəsinin «Dərs yükü faylı» sətrinə çevrilir və həmin rəsmi axından keçir
(``apps.workload.public.legacy_loads``): tapşırıq → sətir → bölgü → təsdiq → açılış/qeydiyyat.

Kafedra: fənnin kafedrası, yoxdursa müəllimin kafedra üzvlüyü. Saat: jurnalın ``fenn_saati``-sı, fəaliyyətlərə
legacy sillabusun həftəlik saat payı ilə (mühazirə / seminar+praktiki / laboratoriya) bölünür; sillabus yoxdursa
dərs növlərinin payı ilə.

QORUYUCU (yeni sistem qalibdir): yalnız tapşırığı OLMAYAN və ya bölgüsü TƏSDİQLƏNMİŞ kafedralar; hər yazı
əvvəlcədən yoxlanılır (fənn/qrup/müəllim mətni başqa sətrə düşürsə, oxşar mövcud sətir varsa — ötürülür); hər
kafedra öz savepoint-indədir və əvvəlcədən VAR olan bölgü sətri, açılışın müəllimi və ya qeydiyyatın statusu
dəyişərsə, ya da eyni fənnin İKİNCİ açılışı yaranarsa — həmin kafedranın yazısı geri qaytarılır və sayılır.
"""

from __future__ import annotations

from collections import defaultdict

from django.apps import apps as django_apps
from django.db import transaction

from ..rehearsal_syllabus_source import legacy_hour_cell
from .resolve import subject_key

SEASON_BY_NAME = {"Payız": "fall", "Yaz": "spring", "Yay": "summer"}
#: Kafedranın bölgüsü artıq TƏSDİQLƏNİB — sətir rəsmi «düzəliş» kimi əlavə olunur. Qalan statuslarda (qaralama,
#: təqdim, təsdiq gözləyir …) kafedra hələ işləyir — ona toxunulmur, yazı ötürülür.
SETTLED_TASK_STATUSES = ("distributed", "amended")


class _ChairRejected(Exception):
    pass


def _syllabus_hours(row) -> dict:
    totals = {"lecture": 0, "seminar": 0, "lab": 0}
    for week in (row or {}).get("week") or ():
        for column, activity in (("muh_saat", "lecture"), ("sem_saat", "seminar"), ("praktiki_saat", "seminar")):
            totals[activity] += legacy_hour_cell(week.get(column))[0]
        totals["lab"] += legacy_hour_cell(week.get("lab_saat"))[0]
    return {key: value for key, value in totals.items() if value}


def _scaled(hours: dict, total: int) -> dict:
    """Sillabusun fəaliyyət PAYI, jurnalın semestr saatına (``fenn_saati``) miqyaslanır — o, jurnalın rəsmi cəmidir."""

    current = sum(hours.values())
    if not current or not total or current == total:
        return hours
    scaled = {key: int(value * total / current) for key, value in hours.items()}
    largest = max(scaled, key=lambda key: hours[key])
    scaled[largest] += total - sum(scaled.values())
    return {key: value for key, value in scaled.items() if value}


def _fallback_hours(journal, dates) -> dict:
    lecture = sum(1 for row in dates if int(row.get("sem_muh") or 0) == 1)
    total = int(journal.get("fenn_saati") or 0) or 2 * len(dates)
    if not total:
        return {}
    if not dates:
        return {"seminar": total}
    lecture_hours = round(total * lecture / len(dates))
    return {key: value for key, value in (("lecture", lecture_hours), ("seminar", total - lecture_hours)) if value}


def _teacher_text(user) -> str:
    patronymic = getattr(getattr(user, "profile", None), "patronymic", "") or ""
    return " ".join(part for part in (user.last_name, user.first_name, patronymic) if part)


def _chair_for(offering, chairs_of) -> object:
    """Fənnin AKTİV kafedrası, yoxdursa müəllimin aktiv kafedra üzvlüyü (deaktiv kafedraya yük yazılmır)."""

    subject = offering.subject
    if subject.chair_unit_id and subject.chair_unit.unit_type == "chair" and subject.chair_unit.is_active:
        return subject.chair_unit
    chair = chairs_of.get(offering.instructor_id)
    return chair if chair is not None and chair.is_active else None


def build_workload(run, slices: dict) -> None:
    """İki keçid: birincidə müəllimlər başqa kafedraya «əlavə müəllim» kimi qoşula bilir (rəsmi axın) — bu,
    əvvəl kafedrası tapılmayan jurnalların kafedrasını həll edir; ikinci keçid YALNIZ onlara baxır. Belə ki
    növbəti qaçışda heç nə qalmır (idempotentlik)."""

    applied, unresolved = _workload_pass(run, slices, only=None)
    if applied and unresolved:
        _workload_pass(run, slices, only=unresolved)
    else:
        run.count("workload.chair_unresolved", len(unresolved))


def _workload_pass(run, slices: dict, *, only) -> tuple[int, set]:
    from apps.workload.public import legacy_loads

    Row = django_apps.get_model("workload", "TeachingTaskRow")
    Assignment = django_apps.get_model("workload", "TeacherAssignment")
    CourseOffering = django_apps.get_model("registrar", "CourseOffering")
    Membership = django_apps.get_model("organizations", "Membership")
    org = run.organization
    syllabi = {row["id"]: row for row in run.bundle["syllabi"]}
    dates_by_journal: dict = defaultdict(list)
    for row in run.bundle["lesson_dates"]:
        dates_by_journal[row["journal_id"]].append(row)
    candidates = []
    for entry in slices.values():
        offerings = [
            o
            for o in entry.offerings
            if o.pk in entry.writable
            and o.instructor_id
            and o.period.name in SEASON_BY_NAME
            and (only is None or o.pk in only)
        ]
        if offerings:
            candidates.append((entry, offerings))
    periods = {o.period_id for _entry, offerings in candidates for o in offerings}
    covered = set()
    for subject_id, period_id, group_id in Row.objects.filter(
        organization=org, period_id__in=periods, groups__isnull=False
    ).values_list("subject_id", "period_id", "groups"):
        covered.add((subject_id, period_id, group_id))
    chairs_of = {}
    for user_id, unit in (
        Membership.objects.filter(
            organization=org, is_active=True, scope_unit__unit_type="chair", scope_unit__is_active=True
        )
        .order_by("-is_primary", "pk")
        .values_list("user_id", "scope_unit")
    ):
        chairs_of.setdefault(user_id, unit)
    units = django_apps.get_model("organizations", "OrgUnit").objects.in_bulk(set(chairs_of.values()))
    chairs_of = {user_id: units.get(unit_id) for user_id, unit_id in chairs_of.items()}
    by_chair: dict = defaultdict(list)
    unresolved: set = set()
    applied = 0
    for entry, offerings in candidates:
        missing = [o for o in offerings if (o.subject_id, o.period_id, o.group_id) not in covered]
        if only is None:
            run.count("workload.slice_covered", len(offerings) - len(missing))
        # Bir legacy jurnalı = bir sətir: eyni müəllim + eyni fənn üzrə qruplar birlikdə (axın/birləşmə).
        groups: dict = defaultdict(list)
        for offering in missing:
            groups[(offering.instructor_id, offering.subject_id, offering.period_id)].append(offering)
        for items in groups.values():
            first = items[0]
            chair = _chair_for(first, chairs_of)
            if chair is None:
                unresolved.update(o.pk for o in items)
                continue
            hours = _scaled(
                _syllabus_hours(syllabi.get(entry.journal.get("sillabus_id"))),
                int(entry.journal.get("fenn_saati") or 0),
            ) or _fallback_hours(entry.journal, dates_by_journal.get(entry.journal["id"], []))
            if not hours:
                run.count("workload.no_hours")
                continue
            by_chair[(chair.pk, first.period.academic_year)].append((chair, first, items, hours, entry.journal))
    Task = django_apps.get_model("workload", "TeachingTask")
    Enrollment = django_apps.get_model("registrar", "Enrollment")
    for (chair_id, year), items in sorted(by_chair.items(), key=lambda pair: (str(pair[0][0]), pair[0][1])):
        chair = items[0][0]
        status = (
            Task.objects.filter(organization=org, chair_id=chair_id, academic_year=year)
            .values_list("status", flat=True)
            .first()
        )
        if status is not None and status not in SETTLED_TASK_STATUSES:
            # Kafedra öz bölgüsü üzərində hələ işləyir — təsdiq axınını (Vakant + təsdiq) biz başlatmırıq.
            run.count("workload.chair_task_in_progress")
            continue
        entries = [
            legacy_loads.legacy_load_entry(
                line=index,
                teacher_text=_teacher_text(first.instructor),
                season=SEASON_BY_NAME[first.period.name],
                groups_text=", ".join(o.group.name for o in offerings),
                subject_text=first.subject.name,
                hours=hours,
                credits=str(journal.get("kredit") or ""),
            )
            for index, (_chair, first, offerings, hours, journal) in enumerate(items, start=1)
        ]
        reasons = legacy_loads.preview_legacy_entries(
            organization=org,
            chair=chair,
            actor_user=run.actor,
            year=year,
            entries=entries,
            targets=[
                (first.subject_id, {o.group_id for o in offerings}, first.instructor_id)
                for _c, first, offerings, _h, _j in items
            ],
        )
        kept = []
        for entry, item, reason in zip(entries, items, reasons):
            if reason:
                run.count(f"workload.entry_skipped.{reason}")
                continue
            kept.append((entry, item))
        if not kept:
            continue
        entries = [entry for entry, _item in kept]
        items = [item for _entry, item in kept]
        before_assign = {
            pk: values
            for pk, *values in Assignment.objects.filter(organization=org, row__task__academic_year=year).values_list(
                "pk", "teacher_id", "activity", "hours", "row_id"
            )
        }
        before_enrollments = dict(
            Enrollment.objects.filter(organization=org, offering__period__academic_year=year).values_list(
                "pk", "status"
            )
        )
        before_offerings = dict(
            CourseOffering.objects.filter(organization=org, period__academic_year=year).values_list(
                "pk", "instructor_id"
            )
        )
        intended: dict = defaultdict(set)
        for _c, first, offerings, _h, _j in items:
            for offering in offerings:
                intended[(offering.period_id, offering.group_id)].add(subject_key(first.subject.name))
        try:
            with transaction.atomic():
                report = legacy_loads.apply_legacy_loads(
                    organization=org, chair=chair, actor_user=run.actor, entries=entries, year=year
                )
                if report.get("denied"):
                    raise _ChairRejected(f"denied:{report['denied']}")
                _verify(org, year, before_assign, before_offerings, Assignment, CourseOffering, intended)
                _verify_enrollments(org, year, before_enrollments, Enrollment)
        except _ChairRejected as rejected:
            run.count(f"workload.chair_rolled_back.{str(rejected).split(':')[0]}")
            run.names("workload_chair_rolled_back", chair.name, str(rejected))
            continue
        counters = report.get("counters", {})
        run.count("workload.chair_applied")
        applied += 1
        run.count("workload.entries", len(entries))
        for key in ("row_created", "line_matched", "line_no_task_row", "assignment_vacant", "students_enrolled"):
            run.count(f"workload.{key}", int(counters.get(key, 0) or 0))
        for key, value in counters.items():
            if key.startswith(("teacher_", "group_not_found", "subject_unresolved", "row_blocked")):
                run.count(f"workload.{key}", int(value or 0))
        run.created("workload_chairs", chair.pk)
    if only is not None:
        run.count("workload.chair_unresolved", len(unresolved))
    return applied, unresolved


def _verify_enrollments(org, year, before: dict, Enrollment) -> None:
    """Mövcud qeydiyyatın statusu dəyişməməlidir (alt qrup birləşməsi / köçürmə — xanalar başqa sətrə keçir)."""

    after = dict(Enrollment.objects.filter(organization=org, pk__in=list(before)).values_list("pk", "status"))
    moved = sum(1 for pk, status in before.items() if after.get(pk) != status)
    if moved:
        raise _ChairRejected(f"existing_enrollment_changed:{moved}")


def _verify(org, year, before_assign, before_offerings, Assignment, CourseOffering, intended) -> None:
    """Qoruyucu — pozuntu varsa ``_ChairRejected`` (kod: nə və neçə)."""

    after = {
        pk: values
        for pk, *values in Assignment.objects.filter(organization=org, row__task__academic_year=year).values_list(
            "pk", "teacher_id", "activity", "hours", "row_id"
        )
    }
    gone = sum(1 for pk in before_assign if pk not in after)
    changed = sum(1 for pk, values in before_assign.items() if pk in after and after[pk] != values)
    if gone or changed:
        raise _ChairRejected(f"existing_assignment_changed:gone={gone}:changed={changed}")
    offerings = {
        pk: (instructor, period, group, name)
        for pk, instructor, period, group, name in CourseOffering.objects.filter(
            organization=org, period__academic_year=year
        ).values_list("pk", "instructor_id", "period_id", "group_id", "subject__name")
    }
    # Pozuntu: bizim yazdığımız (dövr, qrup)-da EYNİ ADLI fənnin İKİNCİ açılışı (mətn başqa kataloq sətrinə düşüb).
    # Kafedra tapşırığının öz sətirlərindən yaranan açılışlar (təsdiqin rəsmi nəticəsi) pozuntu deyil.
    duplicates = sum(
        1
        for pk, (_instructor, period, group, name) in offerings.items()
        if pk not in before_offerings and subject_key(name) in intended.get((period, group), ())
    )
    if duplicates:
        raise _ChairRejected(f"duplicate_offering:{duplicates}")
    moved = sum(1 for pk, instructor in before_offerings.items() if offerings.get(pk, (None,))[0] != instructor)
    if moved:
        raise _ChairRejected(f"instructor_changed:{moved}")


__all__ = ["build_workload"]
