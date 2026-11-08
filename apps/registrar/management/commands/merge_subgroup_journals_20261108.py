"""``merge_subgroup_journals_20261108`` — alt qrup jurnallarını ana qrupun jurnalına birləşdir (defolt dry-run).

Qaydalar: :mod:`apps.registrar.subgroup_journal_merge_2026_11_08`. ``--undo`` manifestdəkini geri qaytarır. Stdout-a
YALNIZ saylar (``subgroup_merge: açar=say …``).
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from ...subgroup_journal_merge_2026_11_08 import Merger, undo
from .relocate_twin_enrollment import run_plan

PREFIX = "subgroup_merge:"


class Command(BaseCommand):
    help = "Sahib 2026-11-08: 536 MU / 536 Bİ alt qrup jurnalları → ana qrupun jurnalı (defolt dry-run)."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--undo", action="store_true", help="Bu əmrin birləşdirdiyini geri qaytar")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")

    def handle(self, *args, **options):
        def runner(organization, actor, counts):
            if options["undo"]:
                undo(organization=organization, actor=actor, counts=counts)
            else:
                Merger(organization=organization, actor=actor, counts=counts).run()

        run_plan(self, options=options, prefix=PREFIX, runner=runner)
