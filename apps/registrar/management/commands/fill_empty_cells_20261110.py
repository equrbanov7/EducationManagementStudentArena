"""``fill_empty_cells_20261110`` — boş jurnal xanaları yalnız sistemdaxili mötəbər mənbədən (sahib 2026-11-10).

Qaydalar: :mod:`apps.registrar.empty_cells_fill_2026_11_10` (``dedupe`` — boş dublikat qeydiyyat azad edilir;
``sibling`` — eyni dərsin tarixçə qeydiyyatındakı xanası köçürülür). DEFOLT DRY-RUN (eyni kod, geri qaytarılır).
Hər qaçışın ``batch`` id-si var; ``--undo --batch <id>`` yalnız həmin qaçışı geri qaytarır. Bütün DB işi
``relocate_twin_enrollment.run_plan``-dadır (``rls_worker_atomic()`` + ``bypass_rls()`` + RLS konteksti).
Stdout-a YALNIZ saylar (``twin_merge: açar=say …``; açarlarda rəqəm yoxdur); prod-data-ops həmin sətirləri süzür;
gözlənilməz xəta ``CommandError: empty_cells_failed_<sinif>_<mətn>`` kimi görünür.
"""

from __future__ import annotations

import re

from django.core.management.base import BaseCommand, CommandError

from ... import empty_cells_fill_2026_11_10 as fill
from .relocate_twin_enrollment import run_plan

PREFIX = "twin_merge:"
_BATCH = re.compile(r"^emptycells-\d{8}-\d{6}-[0-9a-f]{4}$")


def failure_code(exc: Exception) -> str:
    slug = re.sub(r"[^a-z0-9_]+", "_", f"{type(exc).__name__}_{exc}".lower()).strip("_")
    return f"empty_cells_failed_{slug}"[:120]


class Command(BaseCommand):
    help = "Sahib 2026-11-10: boş xanalar yalnız mötəbər sistemdaxili mənbədən; defolt dry-run."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")
        parser.add_argument("--only", choices=fill.OPS, help="Yalnız bir əməliyyat (defolt: dedupe + sibling)")
        parser.add_argument("--batch", default="", help="Qaçış id-si (emptycells-…); --undo üçün məcburi")
        parser.add_argument("--undo", action="store_true", help="--batch qaçışını geri qaytar")

    def handle(self, *args, **options):
        batch = str(options["batch"] or "").strip()
        if batch and not _BATCH.match(batch):
            raise CommandError("empty_cells_batch_invalid")
        if options["undo"] and not batch:
            raise CommandError("empty_cells_undo_needs_batch")
        ops = (options["only"],) if options["only"] else fill.OPS
        used = {}

        def runner(organization, actor, counts):
            if options["undo"]:
                fill.undo(organization=organization, actor=actor, counts=counts, batch=batch)
            else:
                used["batch"] = fill.run(organization=organization, actor=actor, counts=counts, ops=ops, batch=batch)

        try:
            run_plan(self, options=options, prefix=PREFIX, runner=runner)
        except CommandError:
            raise
        except Exception as exc:  # noqa: BLE001 — prod-data-ops yalnız CommandError kodunu göstərir
            raise CommandError(failure_code(exc)) from None
        if used.get("batch"):
            self.stdout.write(f"{PREFIX} batch={used['batch']}")
