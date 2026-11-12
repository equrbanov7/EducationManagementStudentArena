"""``restore_intensive_results_20261112`` — köhnə intensiv/təkrar jurnalında keçilmiş fənnin rəsmi nəticəsi (MR-000288).

Qaydalar: :mod:`apps.registrar.intensive_results_restore_2026_11_12`. Plan faylı (``intensive-results/1``, YALNIZ
legacy id-ləri + rəqəmlər) şifrəli release ilə gəlir. DEFOLT DRY-RUN (eyni kod, geri qaytarılır). Hər qaçışın
``batch`` id-si var; ``--undo --batch <id>`` yalnız həmin qaçışı geri qaytarır. Bütün DB işi
``relocate_twin_enrollment.run_plan``-dadır (``rls_worker_atomic()`` + ``bypass_rls()`` + RLS konteksti).
Stdout-a YALNIZ saylar (``intensive_results: açar=say …``; açarlarda rəqəm yoxdur); gözlənilməz xəta
``CommandError: intensive_results_failed_<sinif>_<mətn>`` kimi görünür.
"""

from __future__ import annotations

import json
import re

from django.core.management.base import BaseCommand, CommandError

from ... import intensive_results_restore_2026_11_12 as restore
from .relocate_twin_enrollment import run_plan

PREFIX = "intensive_results:"
_BATCH = re.compile(r"^intensive-\d{8}-\d{6}-[0-9a-f]{4}$")


def failure_code(exc: Exception) -> str:
    slug = re.sub(r"[^a-z0-9_]+", "_", f"{type(exc).__name__}_{exc}".lower()).strip("_")
    return f"intensive_results_failed_{slug}"[:120]


def load_plan(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        raise CommandError("intensive_results_file_unreadable") from None
    try:
        restore.validate_plan(data)
    except ValueError as exc:
        raise CommandError(str(exc)) from None
    return data


class Command(BaseCommand):
    help = "MR-000288: köhnə intensiv/təkrar jurnalında keçilmiş fənnin rəsmi nəticəsi; defolt dry-run."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--file", default="", help="intensive-results/1 JSON faylı (--undo-suz məcburi)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")
        parser.add_argument("--batch", default="", help="Qaçış id-si (intensive-…); --undo üçün məcburi")
        parser.add_argument("--undo", action="store_true", help="--batch qaçışını geri qaytar")
        parser.add_argument("--student", default="", help="Yalnız bu legacy tələbə id-ləri (vergüllə; sınaq üçün)")

    def handle(self, *args, **options):
        batch = str(options["batch"] or "").strip()
        if batch and not _BATCH.match(batch):
            raise CommandError("intensive_results_batch_invalid")
        if options["undo"] and not batch:
            raise CommandError("intensive_results_undo_needs_batch")
        plan = None if options["undo"] else load_plan(str(options["file"] or ""))
        only = {int(part) for part in str(options["student"] or "").split(",") if part.strip().isdigit()}
        used = {}

        def runner(organization, actor, counts):
            if options["undo"]:
                restore.undo(organization=organization, actor=actor, counts=counts, batch=batch)
            else:
                used["batch"] = restore.run(
                    organization=organization, actor=actor, plan=plan, counts=counts, batch=batch, only_students=only
                )

        try:
            run_plan(self, options=options, prefix=PREFIX, runner=runner)
        except CommandError:
            raise
        except Exception as exc:  # noqa: BLE001 — prod-data-ops yalnız CommandError kodunu göstərir
            raise CommandError(failure_code(exc)) from None
        if used.get("batch"):
            self.stdout.write(f"{PREFIX} batch={used['batch']}")
