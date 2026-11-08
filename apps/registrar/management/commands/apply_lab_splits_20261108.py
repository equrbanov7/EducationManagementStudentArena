"""``apply_lab_splits_20261108`` — Mexanika fizika jurnallarında Lab-1 / Lab-2 (sahib 2026-11-08, defolt dry-run).

Sahib: «hər müəllim öz jurnalında … lab qruplarını görməlidir». Köhnə sistemdə bu jurnalların lab datası yoxdur;
Excel-in «N*H» sayı üzrə hər qrupun aktiv siyahısı soyada görə bərabər ardıcıl hissələrə bölünüb (iki qrup bir lab
qrupunda qarışmır). Plan ``lab_splits_2026_11_08.json`` (yalnız id-lər) — qaydalar
:mod:`apps.registrar.first_year_splits_2026_11_07` (yalnız boş lab qrupu doldurulur, qarışıq lab dərsi qrupsuz qalır).
Stdout-a YALNIZ saylar (``lab_groups: açar=say …``).
"""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand

from ...first_year_splits_2026_11_07 import run
from .relocate_twin_enrollment import run_plan

PREFIX = "lab_groups:"
PLAN = Path(__file__).resolve().parents[2] / "lab_splits_2026_11_08.json"


class Command(BaseCommand):
    help = "Sahib 2026-11-08: Mexanika fizika jurnallarında Lab-1 / Lab-2 (defolt dry-run)."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")

    def handle(self, *args, **options):
        data = json.loads(PLAN.read_text(encoding="utf-8"))

        def runner(organization, actor, counts):
            run(organization=organization, actor=actor, counts=counts, data=data)

        run_plan(self, options=options, prefix=PREFIX, runner=runner)
