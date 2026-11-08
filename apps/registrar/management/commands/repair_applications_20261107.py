"""``repair_applications_20261107`` — RİM müraciətləri 2026-11-07 (MR-247, MR-253, MR-245) (sabit id-lər; defolt dry-run).

Qaydalar: :mod:`apps.registrar.applications_repair_2026_11_07`. Plan faylı yoxdur — id-lər koddadır. ``--undo`` yalnız
bu əmrin audit izinə görə geri qaytarır. Stdout-a YALNIZ saylar (``twin_merge: açar=say …``); prod-data-ops həmin
sətirləri süzür.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from ...applications_repair_2026_11_07 import run, undo
from .relocate_twin_enrollment import run_plan

PREFIX = "twin_merge:"


class Command(BaseCommand):
    help = (
        "RİM 2026-11-07: uydurma / kollec jurnalları passiv (MR-247, MR-253), 209/6SP fənni (MR-245); defolt dry-run."
    )

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")
        parser.add_argument("--undo", action="store_true", help="Bu əmrin yazdıqlarını audit izinə görə geri qaytar")

    def handle(self, *args, **options):
        step = undo if options["undo"] else run

        def runner(organization, actor, counts):
            step(organization=organization, actor=actor, counts=counts, apply=options["apply"])

        run_plan(self, options=options, prefix=PREFIX, runner=runner)
