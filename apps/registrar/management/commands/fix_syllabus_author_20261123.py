"""``fix_syllabus_author_20261123`` — MR-000647 (qiyabi sillabusun müəllifi = jurnalın müəllimi).
Qaydalar: :mod:`apps.registrar.syllabus_author_2026_11_23`. DEFOLT DRY-RUN;
``--undo --batch <syauth-…>`` geri qaytarır. Stdout-a YALNIZ saylar.
"""

from __future__ import annotations

import re

from django.core.management.base import BaseCommand, CommandError

from ... import syllabus_author_2026_11_23 as copier
from .relocate_twin_enrollment import run_plan

PREFIX = "syllabus_author:"
_BATCH = re.compile(r"^syauth-\d{8}-\d{6}-[0-9a-f]{4}$")


def failure_code(exc: Exception) -> str:
    slug = re.sub(r"[^a-z0-9_]+", "_", f"{type(exc).__name__}_{exc}".lower()).strip("_")
    return f"syllabus_author_failed_{slug}"[:120]


class Command(BaseCommand):
    help = "MR-000647: sillabusun müəllifi (sabit id); defolt dry-run."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")
        parser.add_argument("--batch", default="", help="Qaçış id-si (syauth-…); --undo üçün məcburi")
        parser.add_argument("--undo", action="store_true", help="--batch qaçışını geri qaytar")

    def handle(self, *args, **options):
        batch = str(options["batch"] or "").strip()
        if batch and not _BATCH.match(batch):
            raise CommandError("syllabus_author_batch_invalid")
        if options["undo"] and not batch:
            raise CommandError("syllabus_author_undo_needs_batch")
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
