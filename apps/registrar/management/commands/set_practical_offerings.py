"""``set_practical_offerings`` — «Praktiki məşğələ» bayrağını köhnə sistemin planından DOLDURUR (sahib 2026-10-28).

Bayraq YALNIZ görünüşdür (:mod:`apps.registrar.practical_label`): saxlanan növ ``seminar`` qalır — bal, pay, slot,
yük, DB CHECK-ləri dəyişmir. Plan faylı lokal qurulur (``build_practical_flag_plan`` — köhnə sistemin kod 3 jurnalları,
YALNIZ açılış id-ləri): ``{"format": "practical-offerings/1", "offerings": [uuid, …]}``.

FILL-ONLY: yalnız ``False`` → ``True``; heç vaxt söndürmür. Plan BİRDƏFƏLİKDİR — kafedra müdiri / RİM jurnalda
söndürdükdən sonra eyni planla yenidən qaçış onu yandırar (belə açılış plandan çıxarılır). Aktiv olmayan açılış
ötürülür (sayılır).
Bir audit sətri (açılış id-ləri). DEFOLT DRY-RUN. Stdout-a YALNIZ saylar (``practical_flag: açar=say …``).
İdempotent: ikinci qaçışda ``offerings_set=0``.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from ...models import CourseOffering
from .relocate_twin_enrollment import add_plan_arguments, load_plan, run_plan

PREFIX = "practical_flag:"
FORMAT = "practical-offerings/1"
REASON = "Köhnə sistemin «praktiki məşğələ» (kod 3) jurnalları — seminar etiketi «Praktiki məşğələ» (sahib 2026-10-28)"


class Command(BaseCommand):
    help = "«Praktiki məşğələ» bayrağını plan faylından doldurur (yalnız False → True; defolt dry-run)."

    def add_arguments(self, parser):
        add_plan_arguments(parser, FORMAT)

    def handle(self, *args, **options):
        data = load_plan(options["file"], FORMAT, "practical_flag")

        def runner(organization, actor, counts):
            ids = sorted({value for value in data.get("offerings") or [] if isinstance(value, str)})
            counts["offerings_in_file"] = len(ids)
            rows = list(
                CourseOffering.objects.select_for_update()
                .filter(organization=organization, pk__in=ids)
                .values_list("pk", "is_active", "seminar_is_practical")
            )
            counts["offerings_missing"] = len(ids) - len(rows)
            counts["offerings_inactive"] = sum(1 for _pk, active, _flag in rows if not active)
            counts["offerings_already_set"] = sum(1 for _pk, active, flag in rows if active and flag)
            targets = [pk for pk, active, flag in rows if active and not flag]
            counts["offerings_set"] = len(targets)
            if not targets:
                return
            CourseOffering.objects.filter(pk__in=targets).update(seminar_is_practical=True, updated_at=timezone.now())
            log_action(
                action=AuditAction.UPDATE,
                user=actor,
                organization=organization,
                reason=f"registrar: practical label fill — {REASON}",
                old_values={"seminar_is_practical": False},
                new_values={"seminar_is_practical": True, "offering_ids": [str(pk) for pk in targets]},
                resource_type="registrar.courseoffering",
                resource_repr="seminar_is_practical",
            )

        run_plan(self, options=options, prefix=PREFIX, runner=runner)
