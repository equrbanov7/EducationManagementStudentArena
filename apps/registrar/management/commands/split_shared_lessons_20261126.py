"""``split_shared_lessons_20261126`` — MR-000807/802: 435 R ing jurnalında ortaq dərslər iki seminar alt qrupuna.

Qaydalar: :mod:`apps.registrar.lesson_split_2026_11_26` (sabit id-lər), geri qaytarma:
:mod:`apps.registrar.lesson_split_undo_2026_11_26`. DEFOLT DRY-RUN. Hər qaçışın ``batch`` id-si var;
``--undo --batch <id>`` yalnız həmin qaçışı geri qaytarır. DB işi ``relocate_twin_enrollment.run_plan``-dadır
(``rls_worker_atomic()`` + ``bypass_rls()`` + RLS konteksti). Stdout-a YALNIZ saylar; qoruyucu pozulsa
``CommandError: lesson_split_refused_<kod>`` (heç nə yazılmır), gözlənilməz xəta ``lesson_split_failed_<sinif>_<mətn>``.
"""

from __future__ import annotations

import re

from django.core.management.base import BaseCommand, CommandError

from ... import lesson_split_2026_11_26 as fixer
from ... import lesson_split_undo_2026_11_26 as unfixer
from .relocate_twin_enrollment import run_plan

PREFIX = "lesson_split:"
_BATCH = re.compile(r"^lsplit-\d{8}-\d{6}-[0-9a-f]{4}$")


def failure_code(exc: Exception) -> str:
    slug = re.sub(r"[^a-z0-9_]+", "_", f"{type(exc).__name__}_{exc}".lower()).strip("_")
    return f"lesson_split_failed_{slug}"[:120]


class Command(BaseCommand):
    help = "MR-000807/802: 435 R ing jurnalında ortaq dərslər iki seminar alt qrupuna bölünür; defolt dry-run."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")
        parser.add_argument("--batch", default="", help="Qaçış id-si (lsplit-…); --undo üçün məcburi")
        parser.add_argument("--undo", action="store_true", help="--batch qaçışını geri qaytar")
        parser.add_argument("--ignore-counts", action="store_true", help="Gözlənilən 14/13 tələbə sayı yoxlamasını keç")

    def handle(self, *args, **options):
        batch = str(options["batch"] or "").strip()
        if batch and not _BATCH.match(batch):
            raise CommandError("lesson_split_batch_invalid")
        if options["undo"] and not batch:
            raise CommandError("lesson_split_undo_needs_batch")
        used = {}

        def runner(organization, actor, counts):
            if options["undo"]:
                unfixer.undo(organization=organization, actor=actor, counts=counts, batch=batch)
            else:
                used["batch"] = fixer.run(
                    organization=organization,
                    actor=actor,
                    counts=counts,
                    batch=batch,
                    ignore_counts=options["ignore_counts"],
                )

        try:
            run_plan(self, options=options, prefix=PREFIX, runner=runner)
        except fixer.SplitRefused as exc:
            raise CommandError(f"lesson_split_refused_{exc.code}"[:160]) from None
        except CommandError:
            raise
        except Exception as exc:  # noqa: BLE001 — prod-data-ops yalnız CommandError kodunu göstərir
            raise CommandError(failure_code(exc)) from None
        if used.get("batch") and options["apply"] and not options["undo"]:
            self.stdout.write(f"{PREFIX} batch={used['batch']}")
