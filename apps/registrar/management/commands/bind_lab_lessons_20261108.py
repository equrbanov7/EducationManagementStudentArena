"""``bind_lab_lessons_20261108`` — qrupsuz lab dərsini lab qrupuna bağla (defolt dry-run; ``--undo`` geri qaytarır).

Qaydalar: :mod:`apps.registrar.lab_lesson_bind_2026_11_08`. Stdout-a YALNIZ saylar (``lab_groups: açar=say …``).
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from ...lab_lesson_bind_2026_11_08 import run
from .relocate_twin_enrollment import run_plan

PREFIX = "lab_groups:"


class Command(BaseCommand):
    help = "Sahib 2026-11-08: 236 EM 03.11 lab dərsi → Lab-1 (defolt dry-run)."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--undo", action="store_true", help="Bu əmrin bağladığı dərsi qrupsuz et")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")

    def handle(self, *args, **options):
        def runner(organization, actor, counts):
            run(organization=organization, actor=actor, counts=counts, undo=options["undo"])

        run_plan(self, options=options, prefix=PREFIX, runner=runner)
