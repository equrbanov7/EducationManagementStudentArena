"""``rebuild_language_cohorts_20261106`` — xarici dil səviyyə qruplarını rəsmi siyahı üzrə qur (defolt dry-run).

Qaydalar: :mod:`apps.registrar.language_cohort_rebuild_2026_11_06`. Plan faylı repodadır (YALNIZ id-lər).
``--undo`` geri qaytarır. Stdout-a YALNIZ saylar (``twin_merge: açar=say …``); prod-data-ops həmin sətirləri süzür.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from ...language_cohort_rebuild_2026_11_06 import run, undo
from .relocate_twin_enrollment import run_plan

PREFIX = "twin_merge:"


class Command(BaseCommand):
    help = "Xarici dil səviyyə qrupları — rəsmi siyahı üzrə kohort jurnalları (defolt dry-run, --undo geri qaytarır)."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")
        parser.add_argument("--undo", action="store_true", help="Əvvəlki tətbiqi geri qaytar")

    def handle(self, *args, **options):
        action = undo if options["undo"] else run

        def runner(organization, actor, counts):
            action(organization=organization, actor=actor, counts=counts)

        run_plan(self, options=options, prefix=PREFIX, runner=runner)
