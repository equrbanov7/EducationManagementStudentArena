"""``repair_applications_20261105`` — RİM müraciətləri MR-190 / MR-161 / MR-110 (sabit id-lər; defolt dry-run).

Qaydalar: :mod:`apps.registrar.applications_repair_2026_11_05`. Plan faylı yoxdur — cütlər koddadır. Stdout-a YALNIZ
saylar (``twin_merge: açar=say …``); prod-data-ops həmin sətirləri süzür.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from ...applications_repair_2026_11_05 import run
from .relocate_twin_enrollment import run_plan

PREFIX = "twin_merge:"


class Command(BaseCommand):
    help = "RİM 2026-11-05: əkiz jurnal birləşmələri (MR-190, MR-161) + MR-110 xanası (defolt dry-run)."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")

    def handle(self, *args, **options):
        def runner(organization, actor, counts):
            run(organization=organization, actor=actor, counts=counts)

        run_plan(self, options=options, prefix=PREFIX, runner=runner)
