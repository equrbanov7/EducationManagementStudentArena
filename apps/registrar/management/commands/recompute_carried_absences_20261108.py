"""``recompute_carried_absences_20261108`` — «əvvəlki jurnal» qeydləri: boş xanaya bərpa + eyni dərs ikinci dəfə sayılmasın.

Sahib 2026-11-08 audit (135 TSPX): köhnə delta ana qrupun jurnalına alt qrup dərslərinin SURƏTİNİ yazmışdı; ana
jurnal sətri alt qrup sətri ilə əvəzlənəndə (``dropped`` + ``superseded_by``) surət dərslərinin qayıbı «əvvəlki
jurnal» kimi alt qrup jurnalındakı eyni dərsin qayıbının üstünə gəlirdi — 11 tələbə saxta həddi keçirdi.

Qayda (cari semestr): əvəzlənmiş sətrin HƏR xanasının dərsi hədəf sətrin öz jurnalında eyni tarix + başlama saatı
(hər ikisində dolu) + növ ilə dərsdə hədəfin XANASI kimi varsa — bu sətir təmiz surətdir, ``superseded_by`` bağı
açılır (xanalar silinmir, ana jurnalda qalır). Bir xanası belə əkizsizdirsə, üzrlü saat güzəşti varsa — toxunulmur.
Sonra hədəf sətirlərin qayıb sayğacı yenidən hesablanır. Bağlar audit sətrindədir — ``--undo`` qaytarır. Defolt
dry-run; stdout-a YALNIZ saylar.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from ...enrollment_history import predecessors
from ...twin_relocate import corrected_lesson_ids
from .relocate_twin_enrollment import run_plan

PREFIX = "carried_absences:"
RESOURCE = "registrar.duplicate_predecessor_unlink"
REASON = "Sahib 2026-11-08: «əvvəlki jurnal» surət sətri — eyni dərs ikinci dəfə sayılmasın"


def _model(name, app="registrar"):
    return django_apps.get_model(app, name)


def _slots(marks) -> set:
    return {(m.enrollment_id, m.lesson.date, m.lesson.start_time, m.lesson.kind) for m in marks}


def _fill(rows, pred_marks, own, counts) -> list:
    """Əvəzlənmiş sətrin xanaları hədəf jurnalın EYNİ tarix + saat + növ dərsinin BOŞ xanasına (sahib 2026-11-08:
    «müəllim burdakılara aid nə isə yazıbsa onları da bərpa et»). HƏR sətir üçün hamısı ya heç biri: sətrin bütün
    xanaları yer tapırsa (əkiz dərs var, tələbəyə aiddir, düzəlişsizdir) köçür — sonra bağ açılır, ikiqat sayılmır;
    biri belə yer tapmırsa sətir toxunulmur (nişanda qalır). Dolu xanaya yazılmır."""
    from ...lab_groups import applies
    from ...twin_relocate import copy_mark

    Lesson = _model("Lesson")
    target_of = {row.pk: row.superseded_by for row in rows}
    offerings = {row.superseded_by.offering_id for row in rows}
    by_slot: dict = {}
    for lesson in Lesson.objects.filter(offering_id__in=offerings, start_time__isnull=False):
        key = (lesson.offering_id, lesson.date, lesson.start_time, lesson.kind)
        by_slot[key] = None if key in by_slot else lesson  # iki eyni dərs — birmənalı deyil
    corrected = corrected_lesson_ids([lesson.pk for lesson in by_slot.values() if lesson is not None])
    grouped: dict = {}
    for mark in pred_marks:
        grouped.setdefault(mark.enrollment_id, []).append(mark)
    created = []
    for pred_id, marks in grouped.items():
        target = target_of.get(pred_id)
        if target is None:
            continue
        plan, ok = [], True
        for mark in marks:
            src = mark.lesson
            slot = (target.pk, src.date, src.start_time, src.kind)
            if src.start_time is not None and slot in own:
                continue  # hədəfdə artıq yazılıb
            lesson = by_slot.get((target.offering_id, src.date, src.start_time, src.kind)) if src.start_time else None
            if lesson is None or str(lesson.pk) in corrected or not applies(lesson, target):
                ok = False
                break
            plan.append((mark, lesson, slot))
        if not ok:
            counts["predecessors_not_placeable"] += 1
            continue
        for mark, lesson, slot in sorted(plan, key=lambda item: item[0].created_at):
            new = copy_mark(mark, lesson=lesson, enrollment=target)
            own.add(slot)
            created.append([str(new.pk), str(target.pk)])
            counts["marks_restored"] += 1
    return created


def unlink(organization, actor, counts) -> None:
    from ...gradebook_marks import recompute_absence_hours_many

    Enrollment, LessonMark = _model("Enrollment"), _model("LessonMark")
    period = (
        _model("AcademicPeriod", "organizations")
        .objects.filter(organization=organization, is_current=True, is_active=True)
        .order_by("-start_date")
        .first()
    )
    rows = list(
        predecessors()
        .filter(organization=organization, offering__period=period)
        .select_related("superseded_by")
        .order_by("pk")
    )
    counts["predecessors_checked"] = len(rows)
    if not rows:
        return
    pred_ids = [row.pk for row in rows]
    target_ids = {row.superseded_by_id for row in rows}
    marks = list(LessonMark.objects.filter(enrollment_id__in=[*pred_ids, *target_ids]).select_related("lesson"))
    own = _slots(m for m in marks if m.enrollment_id in target_ids and m.lesson.start_time is not None)
    credited = set(
        _model("AbsenceCredit").objects.filter(enrollment_id__in=pred_ids).values_list("enrollment_id", flat=True)
    )
    # Üzrlü güzəştli sətir bağlı qalır — onun xanaları köçürülsə ikiqat sayılardı.
    fillable = [m for m in marks if m.enrollment_id not in target_ids and m.enrollment_id not in credited]
    created = _fill(rows, fillable, own, counts)
    by_pred: dict = {}
    pred_set = set(pred_ids)
    for mark in marks:
        if mark.enrollment_id in pred_set:
            by_pred.setdefault(mark.enrollment_id, []).append(mark)
    unlinked, touched = [], []
    for row in rows:
        items = by_pred.get(row.pk) or []
        if not items:
            continue
        if row.pk in credited:
            counts["skipped_has_credit"] += 1
            continue
        if any(
            m.lesson.start_time is None
            or (row.superseded_by_id, m.lesson.date, m.lesson.start_time, m.lesson.kind) not in own
            for m in items
        ):
            continue
        unlinked.append([str(row.pk), str(row.superseded_by_id)])
        touched.append(row.superseded_by)
        counts["duplicate_absence_hours_removed"] += sum(m.lesson.hours for m in items if m.status == "absent")
    if not unlinked and not created:
        return
    Enrollment.objects.filter(pk__in=[pk for pk, _ in unlinked]).update(superseded_by=None, updated_at=timezone.now())
    counts["predecessors_unlinked"] = len(unlinked)
    touched = list(
        {
            row.pk: row
            for row in [
                *touched,
                *(
                    row.superseded_by
                    for row in rows
                    if str(row.superseded_by_id) in {target for _mark, target in created}
                ),
            ]
        }.values()
    )
    before = {row.pk: row.absence_hours for row in touched}
    result = recompute_absence_hours_many(touched)
    counts["absence_counters_changed"] = sum(1 for pk, hours in result.items() if pk in before and before[pk] != hours)
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        changes={"unlinked": unlinked, "marks_created": created},
        reason=REASON,
        resource_type=RESOURCE,
        resource_id=timezone.now().strftime("%Y%m%d%H%M%S%f"),
    )


def undo(organization, actor, counts) -> None:
    from ...gradebook_marks import recompute_absence_hours_many

    Enrollment = _model("Enrollment")
    rows = _model("AuditLog", "audit").objects.filter(organization=organization, resource_type=RESOURCE, reason=REASON)
    touched = []
    LessonMark = _model("LessonMark")
    for row in rows.order_by("-created_at"):
        created = [pk for pk, _target in (row.changes or {}).get("marks_created") or []]
        stale = LessonMark.objects.filter(pk__in=created, updated_at__gt=row.created_at)
        counts["undo_marks_changed_kept"] += stale.count()
        deleted = LessonMark.objects.filter(pk__in=created).exclude(pk__in=stale.values("pk"))
        counts["undo_marks_deleted"] += deleted.count()
        touched.extend(
            Enrollment.objects.filter(pk__in={t for _pk, t in (row.changes or {}).get("marks_created") or []})
        )
        deleted.delete()
        for pk, target in (row.changes or {}).get("unlinked") or []:
            done = Enrollment.objects.filter(pk=pk, status="dropped", superseded_by__isnull=True).update(
                superseded_by_id=target, updated_at=timezone.now()
            )
            counts["undo_relinked" if done else "undo_skipped"] += 1
            touched.extend(Enrollment.objects.filter(pk=target))
    recompute_absence_hours_many(touched)


class Command(BaseCommand):
    help = "Sahib 2026-11-08: «əvvəlki jurnal» surət sətirləri — eyni dərs ikinci dəfə sayılmasın (defolt dry-run)."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--undo", action="store_true", help="Açılmış bağları geri qaytar")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")

    def handle(self, *args, **options):
        def runner(organization, actor, counts):
            (undo if options["undo"] else unlink)(organization, actor, counts)

        run_plan(self, options=options, prefix=PREFIX, runner=runner)
