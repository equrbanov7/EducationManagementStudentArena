"""``apply_seminar_groups`` — seminar alt qrupları reyestrin alt qruplarından (defolt dry-run, sahib 2026-11-07).

Qaydalar: :mod:`apps.registrar.seminar_groups_apply`. ``--offering`` (təkrarlana bilər) — yalnız həmin jurnallar.
Stdout-a YALNIZ saylar (``lab_groups: açar=say …``); prod-data-ops həmin sətirləri süzür.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from ...seminar_groups_apply import run
from .relocate_twin_enrollment import run_plan

PREFIX = "lab_groups:"


class Command(BaseCommand):
    help = "Sahib 2026-11-07: ana qrup jurnallarında seminar alt qrupları (234 K1 / 234 K2) — defolt dry-run."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--offering", action="append", default=[], help="Yalnız bu jurnal(lar) (UUID)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")

    def handle(self, *args, **options):
        def runner(organization, actor, counts):
            run(organization=organization, actor=actor, counts=counts, offering_ids=options["offering"])

        run_plan(self, options=options, prefix=PREFIX, runner=runner)
