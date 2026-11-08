"""``fill_legacy_cells_20261108`` — köhnə sistemin xanaları EMS jurnalının BOŞ xanalarına (defolt dry-run).

Qaydalar: :mod:`apps.registrar.legacy_cells_fill_2026_11_08`. Plan defolt olaraq modulun yanındakı JSON-dur (yalnız
id-lər). ``--undo`` bu əmrin yaratdığı (dəyişməmiş) xanaları silir. Stdout-a YALNIZ saylar (``legacy_cells: …``).
"""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand

from ... import legacy_cells_fill_2026_11_08 as fill
from .relocate_twin_enrollment import run_plan

PREFIX = "legacy_cells:"
DEFAULT_PLAN = Path(fill.__file__).with_suffix(".json")


class Command(BaseCommand):
    help = "Sahib 2026-11-08: köhnə sistemin xanaları boş jurnal xanalarına (defolt dry-run)."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--file", default=str(DEFAULT_PLAN), help="legacy-cells/1 JSON planı")
        parser.add_argument("--undo", action="store_true", help="Bu əmrin yaratdığı xanaları sil")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")

    def handle(self, *args, **options):
        plan = {"lessons": [], "cells": []} if options["undo"] else fill.load_plan(options["file"])

        def runner(organization, actor, counts):
            if options["undo"]:
                fill.undo(organization=organization, actor=actor, counts=counts)
            else:
                fill.run(
                    organization=organization,
                    actor=actor,
                    counts=counts,
                    cells=plan["cells"],
                    lessons_spec=plan["lessons"],
                )

        run_plan(self, options=options, prefix=PREFIX, runner=runner)
