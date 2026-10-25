"""«İntensiv kurs» — dərs yükü sətri + müəllim bölgüsü + jurnal açılışı + tələbə qeydiyyatı BİR addımda.

Sahib 2026-10-25: «İntensiv … dərs saatı az olur, 1-2 nəfər üçün açılır, müəllim təyin olunur, tez bitir …
dərs yükü yaradanda intensiv seçəndə rahat olsun — hər şey necəsə formalaşsın». Rəsmi ad tək: «İntensiv».

AXIN (:func:`create_intensive`, hamısı BİR tranzaksiyada — bir addım alınmasa heç nə qalmır):

1. Kafedranın HƏMİN tədris ilinin tapşırığı (yoxdursa qaralama yaradılır — ``tasks.get_or_create_task``);
2. registrar: qrupsuz intensiv açılış (``course_format="intensive"``, tarix aralığı, ``lesson_hours`` = saat
   cəmi, jurnal sahibi = müəllim) + seçilmiş tələbələrin qeydiyyatı «alt qrupdan əlavə» rəsmi servisi ilə
   (toqquşma / ikiqat qiymət qaydaları :mod:`apps.registrar.intensive`-dədir);
3. tapşırıq sətri ``row_kind="intensive"`` (qrupsuz — qrup açılışı sinxronu ona TOXUNMUR; jurnalı
   ``intensive_offering``) + mühazirə/seminar bölgüsü müəllimə → müəllimin yükünə «İntensiv» kimi düşür.

Sənəd statusu DƏYİŞMİR və dekanlıq zəncirindən keçmir: intensiv kurs il ərzində ad hoc açılır, bölünmüş
(``distributed``) sənədə də əlavə olunur — audit izi ``workload.intensive_created`` sətridir. Ümumi sətir /
bölgü redaktoru intensiv sətrə yazmır (``ensure_not_intensive``); dəyişiklik = «Ləğv et» (dərs yoxdursa) +
yenidən yarat.

İCAZƏ: kafedranın bölgü açarı (``workload.distribute`` — kafedra müdiri öz kafedrası, RİM hamısı) və ya
Tədris şöbəsinin ``workload.load_import`` açarı («Dərs yükü faylı» ilə eyni qayda).
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.db import transaction

from core.audit import log_action
from core.constants import AuditAction
from core.http_ids import parse_uuid

from ..constants import PERM_LOAD_IMPORT, Activity, RowKind, RowReviewStatus
from ..models import TeacherAssignment, TeachingTaskRow
from .people import ensure_assignable_teacher, resolve_chair
from .plan_calendar import season_from_period
from .scoping import WorkloadDenied, can_distribute_chair, can_manage_chair

MAX_HOURS = 120


def ensure_not_intensive(row) -> None:
    """Ümumi sətir/bölgü redaktoru intensiv sətrə yazmır (jurnal + qeydiyyatlar ona bağlıdır)."""
    if row is not None and getattr(row, "row_kind", "") == RowKind.INTENSIVE:
        raise WorkloadDenied(
            "workload.intensive_row",
            "İntensiv kurs sətri burada redaktə olunmur — dəyişmək üçün kursu ləğv edib yenidən yaradın.",
        )


def can_create(actor, chair_id) -> bool:
    return bool(actor.has(PERM_LOAD_IMPORT) or can_distribute_chair(actor, chair_id))


def _task_actor(actor, chair_id):
    """Tədris şöbəsi (``load_import``) kafedranın tapşırığına «Dərs yükü faylı» aktoru ilə yazır."""
    if can_manage_chair(actor, chair_id):
        return actor
    from .load_upload import import_actor

    return import_actor(actor.user, actor.organization)


def current_period(organization):
    period_model = django_apps.get_model("organizations", "AcademicPeriod")
    return period_model.objects.filter(organization=organization, is_current=True, is_active=True).first()


def _registrar():
    from apps.registrar import public as registrar_public

    return registrar_public


def _denied(exc) -> WorkloadDenied:
    return WorkloadDenied(f"workload.intensive_{getattr(exc, 'code', 'invalid')}", getattr(exc, "text", str(exc)))


def _int(value) -> int:
    try:
        return max(0, int(str(value or "0").strip() or 0))
    except ValueError:
        raise WorkloadDenied("workload.invalid_number", "Saat rəqəm olmalıdır.")


def _resolve(organization, *, subject_id, teacher_id, student_ids):
    Subject = django_apps.get_model("registrar", "Subject")
    from django.contrib.auth import get_user_model

    subject = Subject.objects.filter(organization=organization, pk=parse_uuid(subject_id), is_active=True).first()
    if subject is None:
        raise WorkloadDenied("workload.intensive_subject", "Fənn seçilməyib və ya tapılmadı.")
    teacher_pk = str(teacher_id or "").strip()
    teacher = get_user_model().objects.filter(pk=teacher_pk, is_active=True).first() if teacher_pk.isdigit() else None
    if teacher is None:
        raise WorkloadDenied("workload.intensive_teacher", "Müəllim seçilməyib.")
    ids = []
    for value in student_ids or ():
        try:
            ids.append(int(str(value)))
        except (TypeError, ValueError):
            continue
    students = list(get_user_model().objects.filter(pk__in=ids, is_active=True))
    if not students:
        raise WorkloadDenied("workload.intensive_students", "Ən azı bir tələbə seçin.")
    return subject, teacher, students


def preview(*, organization, actor, chair_id, subject_id, student_ids) -> dict:
    """Tələbə ön baxışı (yazmadan): hər tələbə ``ok`` / ``conflict`` / ``blocked`` + mətn."""
    chair = resolve_chair(organization, chair_id)
    if not can_create(actor, chair.pk):
        raise WorkloadDenied("workload.forbidden", "Bu kafedra üçün intensiv kurs açmaq səlahiyyətiniz yoxdur.")
    period = current_period(organization)
    if period is None:
        raise WorkloadDenied("workload.intensive_period_closed", "Cari aktiv semestr yoxdur.")
    Subject = django_apps.get_model("registrar", "Subject")
    subject = Subject.objects.filter(organization=organization, pk=parse_uuid(subject_id)).first()
    if subject is None:
        return {"students": [], "period": period.name}
    from django.contrib.auth import get_user_model

    students = list(get_user_model().objects.filter(pk__in=[s for s in student_ids if str(s).isdigit()]))
    registrar = _registrar()
    checks = registrar.check_intensive_students(
        organization=organization, period=period, subject_id=subject.pk, students=students
    )
    return {"students": [registrar.intensive_public_check(item) for item in checks], "period": period.name}


@transaction.atomic
def create_intensive(
    *,
    organization,
    actor,
    chair_id,
    subject_id,
    teacher_id,
    student_ids,
    lecture_hours,
    seminar_hours,
    starts_on,
    ends_on,
    note,
    release_source=False,
    request=None,
) -> dict:
    chair = resolve_chair(organization, chair_id)
    if not can_create(actor, chair.pk):
        raise WorkloadDenied("workload.forbidden", "Bu kafedra üçün intensiv kurs açmaq səlahiyyətiniz yoxdur.")
    lecture, seminar = _int(lecture_hours), _int(seminar_hours)
    if not 0 < lecture + seminar <= MAX_HOURS:
        raise WorkloadDenied("workload.intensive_hours", f"Mühazirə + seminar saatı 1–{MAX_HOURS} arasında olmalıdır.")
    period = current_period(organization)
    if period is None:
        raise WorkloadDenied("workload.intensive_period_closed", "Cari aktiv semestr yoxdur.")
    subject, teacher, students = _resolve(
        organization, subject_id=subject_id, teacher_id=teacher_id, student_ids=student_ids
    )
    from .tasks import get_or_create_task

    task, _created = get_or_create_task(
        organization=organization,
        chair_id=chair.pk,
        academic_year=period.academic_year,
        actor=_task_actor(actor, chair.pk),
        request=request,
    )
    # Başqa kafedranın müəllimi bu kafedrada ƏLAVƏ üzvlük alır (adi bölgü ilə eyni qayda); tələbə/əməkdaş — rədd.
    ensure_assignable_teacher(organization, chair, teacher, actor_user=actor.user)
    registrar = _registrar()
    try:
        opened = registrar.open_intensive_course(
            organization=organization,
            subject=subject,
            period=period,
            instructor=teacher,
            hours=lecture + seminar,
            starts_on=starts_on,
            ends_on=ends_on,
            note=note,
            students=students,
            by_user=actor.user,
            release_source=bool(release_source),
        )
    except registrar.IntensiveError as exc:
        raise _denied(exc) from None
    offering = opened["offering"]
    groups = sorted({item["group"] for item in opened["checks"] if item["group"]})
    row = TeachingTaskRow.objects.create(
        organization=organization,
        task=task,
        season=season_from_period(period),
        period=period,
        subject=subject,
        subject_text=subject.name[:255],
        row_kind=RowKind.INTENSIVE,
        groups_text=", ".join(groups)[:255],
        student_count=len(students),
        lecture_plan=lecture,
        lecture_total=lecture,
        seminar_plan=seminar,
        seminar_total=seminar,
        total_hours=lecture + seminar,
        credits_value=min(int(getattr(subject, "ects", 0) or 0), 60),
        review_status=RowReviewStatus.REVIEWED,
        note=f"İntensiv kurs ({offering.starts_on:%d.%m.%Y}–{offering.ends_on:%d.%m.%Y}): {offering.format_note}",
        intensive_offering=offering,
    )
    for activity, hours in ((Activity.LECTURE, lecture), (Activity.SEMINAR, seminar)):
        if hours:
            TeacherAssignment.objects.create(
                organization=organization,
                row=row,
                teacher=teacher,
                activity=activity,
                hours=hours,
                groups_note=row.groups_text,
                assigned_by=actor.user,
                note="İntensiv kurs",
            )
    log_action(
        AuditAction.CREATE,
        user=actor.user,
        organization=organization,
        obj=row,
        new_values={
            "offering": str(offering.pk),
            "teacher": str(teacher.pk),
            "lecture": lecture,
            "seminar": seminar,
            "students": len(students),
            "released": opened["released"],
        },
        reason="workload.intensive_created",
        request=request,
        resource_type="workload.TeachingTaskRow",
        resource_id=str(row.pk),
        resource_repr=f"{subject.name} · İntensiv",
    )
    return {
        "row_id": str(row.pk),
        "offering_id": str(offering.pk),
        "task_id": str(task.pk),
        "academic_year": task.academic_year,
        "students": len(students),
        "released": opened["released"],
    }


@transaction.atomic
def cancel_intensive(*, organization, actor, row_id, reason="", request=None) -> dict:
    """Dərssiz intensiv kursu ləğv: jurnal deaktiv, köçürülmüş qeydiyyatlar geri, sətir + bölgü silinir."""
    row = (
        TeachingTaskRow.objects.select_for_update(of=("self",))
        .filter(organization=organization, pk=parse_uuid(row_id), row_kind=RowKind.INTENSIVE)
        .select_related("task", "intensive_offering", "intensive_offering__subject")
        .first()
    )
    if row is None:
        raise WorkloadDenied("workload.row_not_found", "İntensiv kurs tapılmadı.")
    if not can_create(actor, row.task.chair_id):
        raise WorkloadDenied("workload.forbidden", "Bu kafedra üçün intensiv kursu ləğv etmək səlahiyyətiniz yoxdur.")
    removed = 0
    if row.intensive_offering_id:
        registrar = _registrar()
        try:
            removed = registrar.cancel_intensive_course(
                offering=row.intensive_offering, by_user=actor.user, reason=reason
            )["removed"]
        except registrar.IntensiveError as exc:
            raise _denied(exc) from None
    label = row.subject_label
    row_pk = str(row.pk)
    row.delete()
    log_action(
        AuditAction.DELETE,
        user=actor.user,
        organization=organization,
        old_values={"row": row_pk, "offering": str(row.intensive_offering_id or "")},
        new_values={"students_removed": removed},
        reason="workload.intensive_cancelled",
        request=request,
        resource_type="workload.TeachingTaskRow",
        resource_id=row_pk,
        resource_repr=f"{label} · İntensiv",
    )
    return {"removed": removed}


__all__ = ["can_create", "cancel_intensive", "create_intensive", "ensure_not_intensive", "preview"]
