"""``repair_applications_20261107b`` — RİM müraciətləri 2026-11-07b (MR-221, MR-188) (sabit id-lər; defolt dry-run).

Qaydalar: :mod:`apps.registrar.applications_repair_2026_11_07b`. Plan faylı yoxdur — id-lər koddadır. Stdout-a YALNIZ
saylar (``twin_merge: açar=say …``); prod-data-ops həmin sətirləri süzür.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from ...applications_repair_2026_11_07b import run
from .relocate_twin_enrollment import run_plan

PREFIX = "twin_merge:"


class Command(BaseCommand):
    help = "RİM 2026-11-07b: MR-221 (QKU-845 əkizləri → QKU-1047), MR-188 (434 R alt qrup payları), defolt dry-run."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")

    def handle(self, *args, **options):
        def runner(organization, actor, counts):
            run(organization=organization, actor=actor, counts=counts)

        run_plan(self, options=options, prefix=PREFIX, runner=runner)
