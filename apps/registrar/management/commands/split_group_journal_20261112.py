"""``split_group_journal_20261112`` — birləşmiş qrup jurnalını qruplara ayır (MR-000317; defolt dry-run).

Defolt: 635 Q «Mülki müdafiə» → 635 İ. ``--source`` / ``--target`` / ``--group`` başqa cüt üçündür. Qaydalar:
:mod:`apps.registrar.group_journal_split_2026_11_12`; ``--undo`` audit manifestinə görə geri qaytarır
(:mod:`apps.registrar.group_journal_split_undo_2026_11_12`). Stdout-a YALNIZ saylar (``group_split: açar=say …``);
prod-data-ops həmin sətirləri süzür, xəta yalnız ``CommandError: group_split_…`` kodu ilə görünür.
"""

from __future__ import annotations

import re
import uuid

from django.core.management.base import BaseCommand, CommandError

from ...group_journal_split_2026_11_12 import GROUP, SOURCE, TARGET, Blocked, GroupSplitter
from ...group_journal_split_undo_2026_11_12 import undo
from .relocate_twin_enrollment import run_plan

PREFIX = "group_split:"


def failure_code(exc: Exception) -> str:
    if isinstance(exc, Blocked):
        return f"group_split_blocked_{exc.code}"[:120]
    slug = re.sub(r"[^a-z0-9_]+", "_", f"{type(exc).__name__}_{exc}".lower()).strip("_")
    return f"group_split_failed_{slug}"[:120]


def _uuid(value: str, code: str) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (TypeError, ValueError):
        raise CommandError(f"group_split_{code}_invalid") from None


class Command(BaseCommand):
    help = "Sahib 2026-11-12 (MR-000317): birləşmiş qrup jurnalı → qrupun öz jurnalı (defolt 635 Q → 635 İ); dry-run."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--source", default=SOURCE, help="Mənbə (birləşmiş) açılış id-si")
        parser.add_argument("--target", default=TARGET, help="Hədəf (qrupun öz) açılış id-si")
        parser.add_argument("--group", default=GROUP, help="Köçən tələbələrin akademik qrupu (OrgUnit id)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")
        parser.add_argument(
            "--undo", action="store_true", help="Bu cütün ayrılmasını audit manifestinə görə geri qaytar"
        )

    def handle(self, *args, **options):
        spec = {key: _uuid(options[key], key) for key in ("source", "target", "group")}
        batch = []

        def runner(organization, actor, counts):
            if options["undo"]:
                undo(organization=organization, actor=actor, counts=counts, **spec)
                return
            splitter = GroupSplitter(organization=organization, actor=actor, counts=counts, **spec)
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
