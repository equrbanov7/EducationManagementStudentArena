"""``hide_college_journals_20261110`` — Kollec jurnalları heç kimə göstərilmir (sahib 2026-11-10; defolt dry-run).

Qaydalar: :mod:`apps.registrar.college_journals_hide_2026_11_10`. ``--undo`` yalnız bu əmrin audit izinə görə geri
qaytarır. Stdout-a YALNIZ saylar (``twin_merge: açar=say …``); prod-data-ops həmin sətirləri süzür.
"""

from __future__ import annotations

import re

from django.core.management.base import BaseCommand, CommandError

from ...college_journals_hide_2026_11_10 import run, undo
from .relocate_twin_enrollment import run_plan

PREFIX = "twin_merge:"


def failure_code(exc: Exception) -> str:
    slug = re.sub(r"[^a-z0-9_]+", "_", f"{type(exc).__name__}_{exc}".lower()).strip("_")
    return f"college_hide_failed_{slug}"[:120]


class Command(BaseCommand):
    help = "Sahib 2026-11-10: Kollec qruplarının jurnalları passiv (köhnə sistemdə aparılır); defolt dry-run."

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
