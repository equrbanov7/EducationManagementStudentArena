"""``fix_seminar_week_rows_20261124`` — seminar saatı «mühazirə» kimi yazılmış həftəlik planlar (sahib 2026-11-24).

Forma və qayda: :mod:`apps.registrar.seminar_week_rows_2026_11_24`. DEFOLT DRY-RUN. Hər qaçışın ``batch`` id-si var;
``--undo --batch <id>`` yalnız həmin qaçışı geri qaytarır. Stdout: ``seminar_weeks: açar=say …`` (yalnız saylar) +
``seminar_weeks_ids: açar=<versiya uuid>`` sətirləri (şəxs adı yoxdur). Gözlənilməz xəta
``CommandError: seminar_weeks_failed_<sinif>_<mətn>``.
"""

from __future__ import annotations

import re

from django.core.management.base import BaseCommand, CommandError

from ... import seminar_week_rows_2026_11_24 as filler
from .relocate_twin_enrollment import run_plan

PREFIX = "seminar_weeks:"
IDS_PREFIX = "seminar_weeks_ids:"
_BATCH = re.compile(r"^semwk-\d{8}-\d{6}-[0-9a-f]{4}$")


def failure_code(exc: Exception) -> str:
    slug = re.sub(r"[^a-z0-9_]+", "_", f"{type(exc).__name__}_{exc}".lower()).strip("_")
    return f"seminar_weeks_failed_{slug}"[:120]


class Command(BaseCommand):
    help = "Sahib 2026-11-24: mühazirə kimi yazılmış seminar sətirləri seminara keçir; defolt dry-run."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")
        parser.add_argument("--batch", default="", help="Qaçış id-si (semwk-…); --undo üçün məcburi")
        parser.add_argument("--undo", action="store_true", help="--batch qaçışını geri qaytar")

    def handle(self, *args, **options):
        batch = str(options["batch"] or "").strip()
        if batch and not _BATCH.match(batch):
            raise CommandError("seminar_weeks_batch_invalid")
        if options["undo"] and not batch:
            raise CommandError("seminar_weeks_undo_needs_batch")
        used = {}

        def runner(organization, actor, counts):
            if options["undo"]:
                filler.undo(organization=organization, actor=actor, counts=counts, batch=batch)
            else:
                used["batch"], used["ids"] = filler.run(
                    organization=organization, actor=actor, counts=counts, batch=batch
                )

        try:
            run_plan(self, options=options, prefix=PREFIX, runner=runner)
        except CommandError:
            raise
        except Exception as exc:  # noqa: BLE001 — prod-data-ops yalnız CommandError kodunu göstərir
            raise CommandError(failure_code(exc)) from None
        for key, ids in sorted((used.get("ids") or {}).items()):
            for version_id in ids:
                self.stdout.write(f"{IDS_PREFIX} {key}={version_id}")
        if used.get("batch") and options["apply"] and not options["undo"]:
            self.stdout.write(f"{PREFIX} batch={used['batch']}")
