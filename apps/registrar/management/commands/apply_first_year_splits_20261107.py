"""``apply_first_year_splits_20261107`` — 1-ci kurslar: köhnə sistemin lab / alt qrup bölgüsü (defolt dry-run).

Qaydalar: :mod:`apps.registrar.first_year_splits_2026_11_07`. Plan faylı repodadır (yalnız id-lər). Stdout-a YALNIZ
saylar (``lab_groups: açar=say …``); prod-data-ops həmin sətirləri süzür.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from ...first_year_splits_2026_11_07 import run
from .relocate_twin_enrollment import run_plan

PREFIX = "lab_groups:"


class Command(BaseCommand):
    help = "Sahib 2026-11-07: 1-ci kurs Fizika / kimya Lab-1 / Lab-2 və ADİAK alt qrup payları (defolt dry-run)."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")

    def handle(self, *args, **options):
        def runner(organization, actor, counts):
            run(organization=organization, actor=actor, counts=counts)

        run_plan(self, options=options, prefix=PREFIX, runner=runner)
