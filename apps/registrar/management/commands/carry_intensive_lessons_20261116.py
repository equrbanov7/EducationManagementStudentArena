"""``carry_intensive_lessons_20261116`` — MR-000379: köhnə jurnalın dərsləri və xanaları intensiv jurnala.

Qaydalar: :mod:`apps.registrar.intensive_lessons_carry_2026_11_16` (sabit id-lər, plan faylı yoxdur). DEFOLT DRY-RUN
(eyni kod, geri qaytarılır). Hər qaçışın ``batch`` id-si var; ``--undo --batch <id>`` yalnız həmin qaçışı geri
qaytarır. DB işi ``relocate_twin_enrollment.run_plan``-dadır (``rls_worker_atomic()`` + ``bypass_rls()`` + RLS
konteksti). Stdout-a YALNIZ saylar; gözlənilməz xəta ``CommandError: intensive_carry_failed_<sinif>_<mətn>``.
"""

from __future__ import annotations

import re

from django.core.management.base import BaseCommand, CommandError

from ... import intensive_lessons_carry_2026_11_16 as carry
from .relocate_twin_enrollment import run_plan

PREFIX = "intensive_carry:"
_BATCH = re.compile(r"^icarry-\d{8}-\d{6}-[0-9a-f]{4}$")


def failure_code(exc: Exception) -> str:
    slug = re.sub(r"[^a-z0-9_]+", "_", f"{type(exc).__name__}_{exc}".lower()).strip("_")
    return f"intensive_carry_failed_{slug}"[:120]


class Command(BaseCommand):
    help = "MR-000379: intensivə köçürülmüş tələbənin dərsləri və xanaları köhnə jurnaldan; defolt dry-run."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")
        parser.add_argument("--batch", default="", help="Qaçış id-si (icarry-…); --undo üçün məcburi")
        parser.add_argument("--undo", action="store_true", help="--batch qaçışını geri qaytar")

    def handle(self, *args, **options):
        batch = str(options["batch"] or "").strip()
        if batch and not _BATCH.match(batch):
            raise CommandError("intensive_carry_batch_invalid")
        if options["undo"] and not batch:
            raise CommandError("intensive_carry_undo_needs_batch")
        used = {}

        def runner(organization, actor, counts):
            if options["undo"]:
                carry.undo(organization=organization, actor=actor, counts=counts, batch=batch)
            else:
                used["batch"] = carry.run(organization=organization, actor=actor, counts=counts, batch=batch)

        try:
            run_plan(self, options=options, prefix=PREFIX, runner=runner)
        except CommandError:
            raise
        except Exception as exc:  # noqa: BLE001 — prod-data-ops yalnız CommandError kodunu göstərir
            raise CommandError(failure_code(exc)) from None
        if used.get("batch") and options["apply"]:
            self.stdout.write(f"{PREFIX} batch={used['batch']}")
