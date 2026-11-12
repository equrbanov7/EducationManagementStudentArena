"""``split_share_journal_20261112`` — 434 R payını (Günay Əmirova) ayrıca alt qrup jurnalına çıxar (MR-000188; defolt dry-run).

Qaydalar: :mod:`apps.registrar.share_journal_split_2026_11_12`; ``--undo`` audit manifestinə görə geri qaytarır
(:mod:`apps.registrar.share_journal_split_undo_2026_11_12`). Stdout-a YALNIZ saylar (``share_split: açar=say …``);
prod-data-ops həmin sətirləri süzür, xəta yalnız ``CommandError: share_split_…`` kodu ilə görünür.
"""

from __future__ import annotations

import re

from django.core.management.base import BaseCommand, CommandError

from ...share_journal_split_2026_11_12 import Blocked, Splitter
from ...share_journal_split_undo_2026_11_12 import undo
from .relocate_twin_enrollment import run_plan

PREFIX = "share_split:"


def failure_code(exc: Exception) -> str:
    if isinstance(exc, Blocked):
        return f"share_split_blocked_{exc.code}"[:120]
    slug = re.sub(r"[^a-z0-9_]+", "_", f"{type(exc).__name__}_{exc}".lower()).strip("_")
    return f"share_split_failed_{slug}"[:120]


class Command(BaseCommand):
    help = "Sahib 2026-11-12 (MR-000188): 434 R payı → ayrıca alt qrup jurnalı (sahibi pay müəllimi); defolt dry-run."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")
        parser.add_argument("--undo", action="store_true", help="Bu əmrin bölgüsünü audit manifestinə görə geri qaytar")

    def handle(self, *args, **options):
        batch = []

        def runner(organization, actor, counts):
            if options["undo"]:
                undo(organization=organization, actor=actor, counts=counts)
                return
            splitter = Splitter(organization=organization, actor=actor, counts=counts)
            splitter.run()
            if splitter.batch:
                batch.append(splitter.batch)

        try:
            run_plan(self, options=options, prefix=PREFIX, runner=runner)
        except CommandError:
            raise
        except Exception as exc:  # noqa: BLE001 — prod-data-ops yalnız CommandError kodunu göstərir
            raise CommandError(failure_code(exc)) from None
        if batch:
            self.stdout.write(f"{PREFIX} batch={batch[0]}")
