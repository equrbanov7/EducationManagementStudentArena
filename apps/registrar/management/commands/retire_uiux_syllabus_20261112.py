"""``retire_uiux_syllabus_20261112`` — artıq «UI/UX» sillabusu passiv olur (sahib 2026-11-12; defolt dry-run).

Qaydalar: :mod:`apps.registrar.uiux_syllabus_retire_2026_11_12`. ``--undo`` yalnız bu əmrin audit izinə görə
geri qaytarır. Stdout-a YALNIZ saylar (``syllabus_retire: açar=say …``); prod-data-ops həmin sətirləri süzür.
"""

from __future__ import annotations

import re

from django.core.management.base import BaseCommand, CommandError

from ...uiux_syllabus_retire_2026_11_12 import run, undo
from .relocate_twin_enrollment import run_plan

PREFIX = "syllabus_retire:"


def failure_code(exc: Exception) -> str:
    slug = re.sub(r"[^a-z0-9_]+", "_", f"{type(exc).__name__}_{exc}".lower()).strip("_")
    return f"syllabus_retire_failed_{slug}"[:120]


class Command(BaseCommand):
    help = "Sahib 2026-11-12: Mustafayevanın artıq QKU-2703 «UI/UX» sillabusu passiv; defolt dry-run."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")
        parser.add_argument("--undo", action="store_true", help="Bu əmrin yazdıqlarını audit izinə görə geri qaytar")

    def handle(self, *args, **options):
        step = undo if options["undo"] else run

        def runner(organization, actor, counts):
            step(organization=organization, actor=actor, counts=counts, apply=options["apply"])

        try:
            run_plan(self, options=options, prefix=PREFIX, runner=runner)
        except CommandError:
            raise
        except Exception as exc:  # noqa: BLE001 — prod-data-ops yalnız CommandError kodunu göstərir
            raise CommandError(failure_code(exc)) from None
