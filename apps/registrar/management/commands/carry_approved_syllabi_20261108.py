"""``carry_approved_syllabi_20261108`` — müəllimin təsdiqlənmiş sillabusu onun eyni fənn üzrə BOŞ jurnallarına da.

Sahib 2026-11-08. Qaydalar: :mod:`apps.registrar.syllabus_carry`; paket/geri qaytarma:
:mod:`apps.registrar.syllabus_carry_backfill`.

* DEFOLT DRY-RUN — eyni kod bir tranzaksiyada işləyir, sonda geri alınır (saylar dəqiqdir).
* ``--apply`` — yazır; paket ``sylcarry-YYYYMMDD-HHMMSS-xxxx`` (xülasədə ``batch=``).
* ``--undo <paket> --apply`` — paketin yaratdığı paylaşımları silir.
* Stdout-a YALNIZ saylar: ``syllabus_carry: açar=say …`` (ad yox, yalnız id-li audit).

    manage.py carry_approved_syllabi_20261108 --org qku --actor <superadmin> [--apply]
    manage.py carry_approved_syllabi_20261108 --org qku --actor <superadmin> --undo sylcarry-… --apply
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from ...syllabus_carry_backfill import CarryBatchError, backfill, new_batch, undo
from .relocate_twin_enrollment import run_plan

PREFIX = "syllabus_carry:"


class Command(BaseCommand):
    help = "Sahib 2026-11-08: təsdiqlənmiş sillabus müəllimin eyni fənn üzrə boş jurnallarına da (defolt dry-run)."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--undo", default="", help="Bu paketi geri qaytar (sylcarry-…)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")

    def handle(self, *args, **options):
        batch_to_undo = (options["undo"] or "").strip()
        batch = new_batch()

        def runner(organization, actor, counts):
            try:
                if batch_to_undo:
                    undo(organization, batch_to_undo, actor=actor, counts=counts)
                elif backfill(organization, actor=actor, batch=batch, counts=counts) and options["apply"]:
                    counts["batch"] = batch
            except CarryBatchError as exc:
                raise CommandError(f"syllabus_carry_{exc}") from None

        run_plan(self, options=options, prefix=PREFIX, runner=runner)
