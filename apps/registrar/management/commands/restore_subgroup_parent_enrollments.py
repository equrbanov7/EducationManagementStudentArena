"""``restore_subgroup_parent_enrollments`` — alt qrupa keçiddə ana jurnaldan gizlənən sətirlər (defolt dry-run).

Qaydalar: :mod:`apps.registrar.subgroup_parent_restore_2026_11_07`. Stdout-a YALNIZ saylar
(``lab_groups: açar=say …``); prod-data-ops həmin sətirləri süzür.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from ...subgroup_parent_restore_2026_11_07 import run
from .relocate_twin_enrollment import run_plan

PREFIX = "lab_groups:"


class Command(BaseCommand):
    help = "Sahib 2026-11-07: alt qrupa keçiddə tarixçəyə düşən ana jurnal sətirlərini bərpa et (defolt dry-run)."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")

    def handle(self, *args, **options):
        def runner(organization, actor, counts):
            run(organization=organization, actor=actor, counts=counts)

        run_plan(self, options=options, prefix=PREFIX, runner=runner)
