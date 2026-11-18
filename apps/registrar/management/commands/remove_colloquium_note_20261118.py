"""``remove_colloquium_note_20261118`` — MR-000537: Səkinə Abasovanın iki sillabusunun qiymətləndirmə qeydindən
«colloquium» cümlələri silinir. Qaydalar: :mod:`apps.registrar.colloquium_note_2026_11_18`. DEFOLT DRY-RUN;
``--undo --batch <colloq-…>`` geri qaytarır. Stdout-a YALNIZ saylar.
"""

from __future__ import annotations

import re

from django.core.management.base import BaseCommand, CommandError

from ... import colloquium_note_2026_11_18 as copier
from .relocate_twin_enrollment import run_plan

PREFIX = "colloquium_note:"
_BATCH = re.compile(r"^colloq-\d{8}-\d{6}-[0-9a-f]{4}$")


def failure_code(exc: Exception) -> str:
    slug = re.sub(r"[^a-z0-9_]+", "_", f"{type(exc).__name__}_{exc}".lower()).strip("_")
    return f"colloquium_note_failed_{slug}"[:120]


class Command(BaseCommand):
    help = "MR-000537: sillabusun qiymətləndirmə qeydindən «colloquium» cümlələri; defolt dry-run."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")
        parser.add_argument("--batch", default="", help="Qaçış id-si (colloq-…); --undo üçün məcburi")
        parser.add_argument("--undo", action="store_true", help="--batch qaçışını geri qaytar")

    def handle(self, *args, **options):
        batch = str(options["batch"] or "").strip()
        if batch and not _BATCH.match(batch):
            raise CommandError("colloquium_note_batch_invalid")
        if options["undo"] and not batch:
            raise CommandError("colloquium_note_undo_needs_batch")
        used = {}

        def runner(organization, actor, counts):
            if options["undo"]:
                copier.undo(organization=organization, actor=actor, counts=counts, batch=batch)
            else:
                used["batch"] = copier.run(organization=organization, actor=actor, counts=counts, batch=batch)

        try:
            run_plan(self, options=options, prefix=PREFIX, runner=runner)
        except CommandError:
            raise
        except Exception as exc:  # noqa: BLE001 — prod-data-ops yalnız CommandError kodunu göstərir
            raise CommandError(failure_code(exc)) from None
        if used.get("batch") and options["apply"] and not options["undo"]:
            self.stdout.write(f"{PREFIX} batch={used['batch']}")
