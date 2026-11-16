"""MR-000393 (2132T) — seçmə blok «Genderin tarixi» → «Sosial tarix» + yük sətrinin jurnal sinxronu (2026-11-16).

Yol (yeni yazı yolu icad olunmur):

1. qrupun cari semestr qərarı (``GroupElectiveChoice``) «Genderin tarixi»dir — tək olmalıdır; blok adı oradan;
2. «Sosial tarix» HƏMİN blokda, qrup tələbələrinin planında (ən çox işlədilən plan) — fənn ADLA, tək olmalıdır;
3. «Sosial tarix» + 2132T + semestr yük sətri tək, müəllimi (``owner_for_rows``) var;
4. ``choose_group_elective`` (rəsmi qərar + qrupun ``elective`` qeydiyyatı; köhnə seçimin BOŞ qeydiyyatları
   jurnal gigiyenası ilə çıxır), sonra ``sync_row_offerings`` — jurnalın müəllimi sətrin müəllimi olur;
5. köhnə «Genderin tarixi» jurnalı yalnız DƏRSİ YOXDURSA passiv olur (qalan aktiv qeydiyyatlar ``dropped``,
   cədvəl slotları parklanır).

Jurnal sətrin müəllimi ilə açılmayıbsa hissə bütövlükdə geri qaytarılır (``a_teacher_not_set``). ``undo`` köhnə
jurnalı bərpa edir, qərarı köhnə fənnə qaytarır (gigiyenanın çıxardığı boş qeydiyyatlar özü bərpa olunur) və bu
paketin YARATDIĞI «Sosial tarix» jurnalını (dərsi yoxdursa) passivləşdirir.
"""

from __future__ import annotations

from collections import Counter

from django.utils import timezone

from ..constants import TaskStatus
from ..models import TeachingTaskRow
from .applications_repair_2026_11_16 import (
    A_GROUP,
    A_NEW_SUBJECT,
    A_OLD_SUBJECT,
    REASONS,
    RES_ELECTIVE,
    Skip,
    audit,
    model,
    one_group,
)
from .offering_rules import owner_for_rows
from .offering_sync import rows_queryset, sync_row_offerings
from .scoping import resolve_actor

PARK_REASON = "MR-000393: qrupun seçmə fənni dəyişdi — köhnə jurnal passivdir"


def _block_option(organization, group, block, old_subject):
    """``(plan, yeni fənn)`` — yeni fənn köhnə ilə EYNİ blokda, qrup tələbələrinin planında."""
    Record = model("registrar", "StudentAcademicRecord")
    ranked = Counter(
        Record.objects.filter(
            organization=organization, group=group, is_active=True, curriculum__isnull=False
        ).values_list("curriculum_id", flat=True)
    )
    options: dict = {}
    for row in (
        model("registrar", "CurriculumSubject")
        .objects.filter(
            organization=organization, curriculum_id__in=list(ranked), elective_group=block, is_elective=True
        )
        .select_related("subject")
    ):
        options.setdefault(row.curriculum_id, {}).setdefault(row.subject.name.strip(), set()).add(row.subject_id)
    fitting = [
        curriculum_id
        for curriculum_id, _count in ranked.most_common()
        if old_subject.pk in options.get(curriculum_id, {}).get(A_OLD_SUBJECT, set())
        and options.get(curriculum_id, {}).get(A_NEW_SUBJECT)
    ]
    new_ids = {pk for curriculum_id in fitting for pk in options[curriculum_id][A_NEW_SUBJECT]}
    if not fitting:
        raise Skip("new_subject_not_in_block")
    if len(new_ids) != 1:
        raise Skip("new_subject_ambiguous")
    curriculum = model("registrar", "Curriculum").objects.get(pk=fitting[0])
    return curriculum, model("registrar", "Subject").objects.get(pk=next(iter(new_ids)))


def _load_row(organization, group, period, subject):
    rows = list(
        TeachingTaskRow.objects.filter(organization=organization, subject=subject, groups=group, period=period)
        .exclude(task__status=TaskStatus.CANCELLED)
        .select_related("task", "period")
        .distinct()
    )
    if len(rows) != 1:
        raise Skip("row_unresolved")
    row = rows[0]
    teacher = owner_for_rows(list(rows_queryset(row.task).filter(pk=row.pk)))
    if teacher is None:
        raise Skip("row_teacher_missing")
    return row, teacher


def _retire(offering, *, actor, counts, prefix: str) -> dict:
    """Dərssiz jurnalı passivləşdirir: aktiv qeydiyyatlar ``dropped``, slotlar parklanır. Qaytarır: id-lər."""
    Offering, Enrollment = model("registrar", "CourseOffering"), model("registrar", "Enrollment")
    Slot, Lesson = model("registrar", "ScheduleSlot"), model("registrar", "Lesson")
    if not offering.is_active:
        counts[f"{prefix}_already_inactive"] += 1
        return {}
    if Lesson.objects.filter(offering=offering).exists():
        counts[f"{prefix}_has_lessons_kept"] += 1
        return {}
    now = timezone.now()
    dropped = [
        str(pk)
        for pk in Enrollment.objects.filter(offering=offering, status="enrolled")
        .order_by("pk")
        .values_list("pk", flat=True)
    ]
    Enrollment.objects.filter(pk__in=dropped).update(status="dropped", updated_at=now)
    parked = [
        str(pk)
        for pk in Slot.objects.filter(offering=offering, is_parked=False).order_by("pk").values_list("pk", flat=True)
    ]
    Slot.objects.filter(pk__in=parked).update(
        is_parked=True, parked_at=now, parked_by=actor, park_reason=PARK_REASON, updated_at=now
    )
    Offering.objects.filter(pk=offering.pk).update(is_active=False, updated_at=now)
    counts[f"{prefix}_deactivated"] += 1
    counts[f"{prefix}_enrollments_dropped"] += len(dropped)
    counts[f"{prefix}_slots_parked"] += len(parked)
    return {"offering": str(offering.pk), "dropped_enrollments": dropped, "parked_slots": parked}


def apply(*, organization, actor, period, batch, counts) -> None:
    from apps.registrar.public import services as registrar_services

    Choice, Offering = model("registrar", "GroupElectiveChoice"), model("registrar", "CourseOffering")
    group = one_group(organization, A_GROUP, "group_unresolved")
    choices = list(
        Choice.objects.select_for_update(of=("self",))
        .filter(organization=organization, group=group, period=period)
        .select_related("chosen_subject")
    )
    old = [choice for choice in choices if choice.chosen_subject.name.strip() == A_OLD_SUBJECT]
    if not old:
        done = any(choice.chosen_subject.name.strip() == A_NEW_SUBJECT for choice in choices)
        raise Skip("already_done" if done else "choice_missing")
    if len(old) != 1:
        raise Skip("choice_ambiguous")
    choice = old[0]
    old_subject, block, old_decider = choice.chosen_subject, choice.elective_group, choice.decided_by_id
    curriculum, new_subject = _block_option(organization, group, block, old_subject)
    row, teacher = _load_row(organization, group, period, new_subject)
    scope = {"organization": organization, "period": period, "group": group}
    existing = Offering.objects.filter(subject=new_subject, **scope).first()
    if existing is not None and not existing.is_active:
        raise Skip("new_journal_inactive")

    registrar_services.choose_group_elective(
        **scope,
        curriculum=curriculum,
        elective_group=block,
        subject=new_subject,
        decided_by=actor,
        enforce_window=False,
    )
    report = sync_row_offerings(row, actor=resolve_actor(actor, organization), create=True)
    journal = Offering.objects.filter(subject=new_subject, **scope).first()
    if journal is None or not journal.is_active or journal.instructor_id != teacher.pk:
        raise Skip("teacher_not_set")
    counts["a_choice_switched"] += 1
    counts["a_journal_created" if existing is None else "a_journal_reused"] += 1
    counts["a_students_enrolled"] += (
        model("registrar", "Enrollment").objects.filter(offering=journal, status="enrolled").count()
    )
    counts["a_sync_instructor_set"] += int(report.get("instructor_set") or 0)

    retired = {}
    old_journal = Offering.objects.select_for_update(of=("self",)).filter(subject=old_subject, **scope).first()
    if old_journal is None:
        counts["a_old_journal_missing"] += 1
    else:
        retired = _retire(old_journal, actor=actor, counts=counts, prefix="a_old_journal")
    audit(
        actor=actor,
        organization=organization,
        resource_type=RES_ELECTIVE,
        resource_id=group.pk,
        repr_=f"{group.name}: {old_subject.name} → {new_subject.name}",
        reason=REASONS["a"],
        old_values={"chosen_subject": str(old_subject.pk), "decided_by": old_decider},
        new_values={
            "batch": batch,
            "group": str(group.pk),
            "period": str(period.pk),
            "block": block,
            "curriculum": str(curriculum.pk),
            "old_subject": str(old_subject.pk),
            "new_subject": str(new_subject.pk),
            "row": str(row.pk),
            "teacher": teacher.pk,
            "new_offering": str(journal.pk),
            "new_offering_existed": existing is not None,
            "old_offering": str(old_journal.pk) if old_journal is not None else "",
            "retired": retired,
        },
    )


def undo(*, organization, actor, row, batch, counts) -> None:
    from apps.registrar.public import services as registrar_services

    Choice, Offering = model("registrar", "GroupElectiveChoice"), model("registrar", "CourseOffering")
    Enrollment, Slot = model("registrar", "Enrollment"), model("registrar", "ScheduleSlot")
    values = row.new_values or {}
    choice = (
        Choice.objects.select_for_update(of=("self",))
        .filter(
            organization=organization,
            group_id=values.get("group"),
            period_id=values.get("period"),
            elective_group=values.get("block"),
        )
        .first()
    )
    if choice is None or str(choice.chosen_subject_id) != values.get("new_subject"):
        raise Skip("choice_changed")
    retired = values.get("retired") or {}
    if retired.get("offering"):
        Offering.objects.filter(pk=retired["offering"]).update(is_active=True, updated_at=timezone.now())
        counts["a_undo_old_journal_restored"] += 1
        counts["a_undo_enrollments_restored"] += Enrollment.objects.filter(
            pk__in=retired.get("dropped_enrollments") or [], status="dropped"
        ).update(status="enrolled", updated_at=timezone.now())
        Slot.objects.filter(pk__in=retired.get("parked_slots") or [], is_parked=True).update(
            is_parked=False, parked_at=None, parked_by=None, park_reason="", updated_at=timezone.now()
        )
    group = model("organizations", "OrgUnit").objects.get(pk=values["group"])
    registrar_services.choose_group_elective(
        organization=organization,
        group=group,
        curriculum=model("registrar", "Curriculum").objects.get(pk=values["curriculum"]),
        period=model("organizations", "AcademicPeriod").objects.get(pk=values["period"]),
        elective_group=values["block"],
        subject=model("registrar", "Subject").objects.get(pk=values["old_subject"]),
        decided_by=actor,
        enforce_window=False,
    )
    Choice.objects.filter(pk=choice.pk).update(decided_by_id=(row.old_values or {}).get("decided_by"))
    counts["a_undo_choice_restored"] += 1
    if not values.get("new_offering_existed"):
        journal = Offering.objects.select_for_update(of=("self",)).filter(pk=values.get("new_offering")).first()
        if journal is not None:
            _retire(journal, actor=actor, counts=counts, prefix="a_undo_new_journal")
    audit(
        actor=actor,
        organization=organization,
        resource_type=f"{RES_ELECTIVE}.undo",
        resource_id=row.resource_id,
        repr_="MR-000393 geri qaytarıldı",
        reason=f"{REASONS['a']} — geri qaytarma",
        old_values={"batch": batch},
        new_values={"undone_batch": batch},
    )
