"""``fix_legacy_lesson_kinds`` — köhnə sistemin kod 2 (laboratoriya) dərslərini «seminar»dan «laboratoriya»ya keçirir
(RİM 2026-10-27, MR-8/9/29).

Delta (``rehearsal_journal_lesson_kinds.cell_kind``) legacy ``sem_muh=2`` kodunu SEMINAR yazırdı, halbuki o,
laboratoriyadır (2026/2027 payızında bütün kod-2 jurnallarının sillabusunda ``lab_saat`` var). Nəticə: dərs və cədvəl
slotu «seminar», aktivlik balı (``activity_kinds``: seminar + lab → 5 + 5) yarıya düşür.

Plan faylı lokal qurulur (``build_twin_repair_plans`` — köhnə sistemin xanaları ilə: dərsin xanalarının əksəriyyəti
kod 2-dir), YALNIZ dərs id-ləri: ``{"format": "legacy-lesson-kinds/1", "lessons": [uuid, …]}``.

Yazı (hər açılış öz savepoint-ində, kilid altında yenidən yoxlanılır):

* dərs hələ də ``seminar``, köçürmənin yaratdığıdır (``created_by`` boş), rəsmi dərs düzəlişi (``LessonCorrection``)
  yoxdur; açılış aktiv, jurnalı bağlı deyil;
* açılışın TƏSDİQLƏNMİŞ sillabusunun plan saatında (kafedranın ``plan_hours_override``-ı üstündür) ``lab > 0`` və
  ``seminar = 0`` → dərslər ``lab`` + açılışın canlı ``seminar`` cədvəl slotları ``lab``;
* plan həm seminar, həm lab daşıyırsa yalnız ``--include-mixed`` ilə və YALNIZ dərslər (slot hansı növə aid olduğu
  bilinmir — toxunulmur); laboratoriyası olmayan plan — toxunulmur (sayılır).

Xanalara toxunulmur (``trg_journal_mark_guard`` UPDATE-i yoxdur): seminar da, lab da bal qəbul edir. Aktivlik balı
canlı SQL ifadəsidir (``activity_kinds.bits_expression``) — saxlanmış «cache» yoxdur, növ dəyişən kimi düzəlir.
Hər açılış üçün audit (dərs + slot id-ləri). DEFOLT DRY-RUN. Stdout-a YALNIZ saylar (``lesson_kinds: açar=say …``).
İdempotent: ikinci qaçışda dərs artıq ``lab``-dır.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from ...models import CourseOffering, Lesson, ScheduleSlot
from ...twin_relocate import closed, corrected_lesson_ids
from .relocate_twin_enrollment import add_plan_arguments, load_plan, run_plan

PREFIX = "lesson_kinds:"
FORMAT = "legacy-lesson-kinds/1"
REASON = "Köhnə sistemin laboratoriya (kod 2) dərsləri «seminar» kimi köçmüşdü — RİM 2026-10-27 (MR-8/9)"


def _hours(plan, key) -> Decimal:
    try:
        return Decimal(str((plan or {}).get(key) or 0))
    except (InvalidOperation, ValueError):
        return Decimal(0)


def approved_plan(offering) -> dict | None:
    """Açılışın təsdiqlənmiş sillabus planı (kafedranın əl düzəlişi üstün); təsdiqlənmiş sillabus yoxdursa ``None``."""

    Syllabus = django_apps.get_model("syllabus", "Syllabus")
    syllabus = (
        Syllabus.objects.filter(organization_id=offering.organization_id, offering=offering, is_active=True)
        .select_related("approved_version")
        .first()
    )
    if syllabus is None or syllabus.approved_version is None:
        return None
    return syllabus.plan_hours_override or syllabus.approved_version.plan_hours or {}


class Command(BaseCommand):
    help = "Köhnə sistemin kod-2 (laboratoriya) dərslərini seminar → lab edir (plan faylı ilə; defolt dry-run)."

    def add_arguments(self, parser):
        add_plan_arguments(parser, FORMAT)
        parser.add_argument(
            "--include-mixed",
            action="store_true",
            help="Plan HƏM seminar, HƏM lab daşıyan açılışlarda da (yalnız dərslər; slotlar toxunulmur)",
        )

    def handle(self, *args, **options):
        data = load_plan(options["file"], FORMAT, "lesson_kinds")
        mixed = bool(options["include_mixed"])

        def runner(organization, actor, counts):
            by_offering = defaultdict(list)
            ids = [value for value in data.get("lessons") or [] if isinstance(value, str)]
            counts["lessons_in_file"] = len(ids)
            for lesson in Lesson.objects.filter(organization=organization, pk__in=ids).only("pk", "offering_id"):
                by_offering[lesson.offering_id].append(lesson.pk)
            counts["lessons_missing"] = len(ids) - sum(len(rows) for rows in by_offering.values())
            for offering_id, lesson_ids in sorted(by_offering.items(), key=lambda item: str(item[0])):
                with transaction.atomic():
                    self._offering(organization, actor, offering_id, lesson_ids, mixed, counts)

        run_plan(self, options=options, prefix=PREFIX, runner=runner)

    def _offering(self, organization, actor, offering_id, lesson_ids, mixed, counts) -> None:
        offering = CourseOffering.objects.select_for_update(of=("self",)).filter(pk=offering_id).first()
        if offering is None or not offering.is_active or closed([offering.pk]):
            counts["offering_closed_or_inactive"] += 1
            return
        plan = approved_plan(offering)
        lab, seminar = _hours(plan, "lab"), _hours(plan, "seminar")
        if plan is None:
            counts["offering_no_approved_syllabus"] += 1
            return
        if lab <= 0:
            counts["offering_no_lab_in_plan"] += 1
            return
        if seminar > 0 and not mixed:
            counts["offering_mixed_plan_skipped"] += 1
            return
        corrected = corrected_lesson_ids(lesson_ids)
        rows = list(
            Lesson.objects.select_for_update()
            .filter(pk__in=lesson_ids, kind="seminar", created_by__isnull=True)
            .values_list("pk", flat=True)
        )
        targets = [pk for pk in rows if str(pk) not in corrected]
        counts["lessons_corrected_kept"] += len(rows) - len(targets)
        counts["lessons_not_seminar_or_teacher_made"] += len(lesson_ids) - len(rows)
        if not targets:
            return
        now = timezone.now()
        Lesson.objects.filter(pk__in=targets).update(kind="lab", updated_at=now)
        slot_ids = []
        if seminar <= 0:
            slot_ids = [
                str(pk)
                for pk in ScheduleSlot.objects.filter(offering=offering, kind="seminar").values_list("pk", flat=True)
            ]
            ScheduleSlot.objects.filter(pk__in=slot_ids).update(kind="lab", updated_at=now)
        else:
            counts["offering_mixed_slots_kept"] += 1
        counts["offerings_fixed"] += 1
        counts["lessons_set_lab"] += len(targets)
        counts["slots_set_lab"] += len(slot_ids)
        log_action(
            action=AuditAction.UPDATE,
            user=actor,
            organization=organization,
            obj=offering,
            reason=f"registrar: legacy lesson kind fix — {REASON}",
            old_values={"kind": "seminar"},
            new_values={
                "kind": "lab",
                "lesson_ids": [str(pk) for pk in targets],
                "slot_ids": slot_ids,
                "plan_hours": {key: str(_hours(plan, key)) for key in ("lecture", "seminar", "lab")},
            },
        )
