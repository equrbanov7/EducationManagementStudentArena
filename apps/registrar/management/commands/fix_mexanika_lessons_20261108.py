"""``fix_mexanika_lessons_20261108`` — Mexanika jurnallarının dərs növü və səhv jurnala düşmüş dərsləri (defolt dry-run).

Qaydalar: :mod:`apps.registrar.mexanika_lessons_fix_2026_11_08`. Plan defolt olaraq modulun yanındakı JSON-dur
(YALNIZ id / tarix / saat / növ). ``--undo`` dəyişməmiş hər şeyi geri qaytarır. Stdout-a YALNIZ saylar
(``mexanika_lessons: açar=say …``).
"""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand

from ... import mexanika_lessons_fix_2026_11_08 as fix
from .relocate_twin_enrollment import run_plan

PREFIX = "mexanika_lessons:"
DEFAULT_PLAN = Path(fix.__file__).with_suffix(".json")


class Command(BaseCommand):
    help = "Sahib 2026-11-08: Mexanika jurnalları — dərs növü + səhv jurnaldakı dərslər (defolt dry-run)."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--file", default=str(DEFAULT_PLAN), help="mexanika-lessons/1 JSON planı")
        parser.add_argument("--undo", action="store_true", help="Bu əmrin dəyişdiklərini geri qaytar")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")

    def handle(self, *args, **options):
        plan = {} if options["undo"] else fix.load_plan(options["file"])

        def runner(organization, actor, counts):
            if options["undo"]:
                fix.undo(organization=organization, actor=actor, counts=counts)
            else:
                fix.run(organization=organization, actor=actor, counts=counts, plan=plan)

        run_plan(self, options=options, prefix=PREFIX, runner=runner)
