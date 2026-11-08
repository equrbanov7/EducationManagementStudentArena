"""``recompute_carried_absences_20261108`` — əvvəlki jurnalı olan qeydiyyatların qayıb saatını yenidən hesabla.

Sahib 2026-11-08 (135 TSPX): ana jurnaldakı alt qrup dərslərinin SURƏTİ «əvvəlki jurnal» qayıbı kimi alt qrup
jurnalındakı eyni dərsin üstünə gəlirdi. Qayda düzəldi (:func:`guest_merge.carry_over_map` eyni dərsi ikinci dəfə
saymır); bu əmr saxlanmış sayğacları cari semestrdə yeniləyir. Defolt dry-run; stdout-a YALNIZ saylar.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand

from ...enrollment_history import predecessors
from .relocate_twin_enrollment import run_plan

PREFIX = "carried_absences:"


class Command(BaseCommand):
    help = "Sahib 2026-11-08: əvvəlki jurnal qayıbı — eyni dərs ikinci dəfə sayılmasın (defolt dry-run)."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")

    def handle(self, *args, **options):
        def runner(organization, actor, counts):
            from ...gradebook_marks import recompute_absence_hours_many

            Enrollment = django_apps.get_model("registrar", "Enrollment")
            period = (
                django_apps.get_model("organizations", "AcademicPeriod")
                .objects.filter(organization=organization, is_current=True, is_active=True)
                .order_by("-start_date")
                .first()
            )
            targets = list(
                Enrollment.objects.filter(
                    organization=organization,
                    offering__period=period,
                    pk__in=predecessors().filter(organization=organization).values("superseded_by_id"),
                )
            )
            before = {row.pk: row.absence_hours for row in targets}
            counts["enrollments_with_history"] = len(targets)
            for start in range(0, len(targets), 500):
                result = recompute_absence_hours_many(targets[start : start + 500])
                for pk, hours in result.items():
                    if pk in before and before[pk] != hours:
                        counts["absence_hours_changed"] += 1
                        counts["absence_hours_removed"] += max(0, before[pk] - hours)
                        counts["absence_hours_added"] += max(0, hours - before[pk])

        run_plan(self, options=options, prefix=PREFIX, runner=runner)
