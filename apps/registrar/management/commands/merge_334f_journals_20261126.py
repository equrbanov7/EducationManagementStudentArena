"""``merge_334f_journals_20261126`` — MR-000836: 334F1 + 334F2 → ana qrup «334F», hər fənn üçün bir jurnal.

Qaydalar: :mod:`apps.registrar.merge_334f_2026_11_26` (ad ilə həll olunur, sabit id yoxdur), geri qaytarma:
:mod:`apps.registrar.merge_334f_undo_2026_11_26`. DEFOLT DRY-RUN. Hər qaçışın ``batch`` id-si var;
``--undo --batch <id>`` yalnız həmin qaçışı geri qaytarır. DB işi ``relocate_twin_enrollment.run_plan``-dadır
(``rls_worker_atomic()`` + ``bypass_rls()`` + RLS konteksti). Stdout-a YALNIZ saylar və id prefiksləri
(``f334_merge: açar=dəyər …``; ailə başına ``family=<fənn kodu> status=<merged|blocked_<səbəb>|already_merged>``);
qoruyucu pozulsa ``CommandError: f334_merge_refused_<kod>`` (heç nə yazılmır), gözlənilməz xəta
``f334_merge_failed_<sinif>_<mətn>``.
"""

from __future__ import annotations

import re

from django.core.management.base import BaseCommand, CommandError

from ... import merge_334f_2026_11_26 as fixer
from ... import merge_334f_check_2026_11_27 as checker
from ... import merge_334f_undo_2026_11_26 as unfixer
from .relocate_twin_enrollment import run_plan

PREFIX = "f334_merge:"
_BATCH = re.compile(r"^m334f-\d{8}-\d{6}-[0-9a-f]{4}$")
_VALUE = re.compile(r"[^0-9a-z_-]+")


def failure_code(exc: Exception) -> str:
    slug = re.sub(r"[^a-z0-9_]+", "_", f"{type(exc).__name__}_{exc}".lower()).strip("_")
    return f"f334_merge_failed_{slug}"[:120]


def _safe(value) -> str:
    return _VALUE.sub("_", str(value).casefold()).strip("_") or "0"


def family_line(family, outcome, delta) -> str:
    status = outcome if outcome in ("merged", "already_merged") else f"blocked_{outcome}"
    pairs = [
        f"family={family['code']}",
        f"status={_safe(status)}",
        *(f"{name}={source[:8]}" for name, source in zip(("first", "second"), family["sources"])),
        *(f"{key}={_safe(value)}" for key, value in sorted(delta.items()) if re.fullmatch(r"[a-z_]+", key)),
    ]
    return f"{PREFIX} " + " ".join(pairs)


class Command(BaseCommand):
    help = "MR-000836: 334F1 + 334F2 → ana qrup 334F, payız fənlərinin jurnalları birləşir; defolt dry-run."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")
        parser.add_argument("--batch", default="", help="Qaçış id-si (m334f-…); --undo üçün məcburi")
        parser.add_argument("--undo", action="store_true", help="--batch qaçışını geri qaytar")
        parser.add_argument(
            "--check", action="store_true", help="--batch qaçışının qayıb saatlarını tutuşdur (yalnız oxuyur)"
        )

    def handle(self, *args, **options):
        batch = str(options["batch"] or "").strip()
        if batch and not _BATCH.match(batch):
            raise CommandError("f334_merge_batch_invalid")
        if options["undo"] and not batch:
            raise CommandError("f334_merge_undo_needs_batch")
        if options["check"] and (not batch or options["undo"] or options["apply"]):
            raise CommandError("f334_merge_check_needs_batch_only")
        used, report = {}, []

        def runner(organization, actor, counts):
            if options["check"]:
                checker.check(organization=organization, batch=batch, counts=counts, report=report)
            elif options["undo"]:
                unfixer.undo(organization=organization, actor=actor, counts=counts, batch=batch)
            else:
                used["batch"] = fixer.run(
                    organization=organization, actor=actor, counts=counts, batch=batch, report=report
                )

        try:
            run_plan(self, options=options, prefix=PREFIX, runner=runner)
        except fixer.MergeRefused as exc:
            raise CommandError(f"f334_merge_refused_{exc.code}"[:160]) from None
        except CommandError:
            raise
        except Exception as exc:  # noqa: BLE001 — prod-data-ops yalnız CommandError kodunu göstərir
            raise CommandError(failure_code(exc)) from None
        if options["check"]:
            for item in report:
                self.stdout.write(f"{PREFIX} kind=check " + " ".join(f"{k}={_safe(v)}" for k, v in item.items()))
            return
        for family, outcome, delta in report:
            self.stdout.write(family_line(family, outcome, delta))
        if used.get("batch") and options["apply"] and not options["undo"]:
            self.stdout.write(f"{PREFIX} batch={used['batch']}")
