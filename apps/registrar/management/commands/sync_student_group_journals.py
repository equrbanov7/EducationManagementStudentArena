"""``sync_student_group_journals`` — tələbəni öz qrupunun cari jurnallarına sal (defolt dry-run).

Qaydalar: :mod:`apps.registrar.student_group_journals`. ``--students`` vergüllə ayrılmış hesab id-ləri.
Stdout-a YALNIZ saylar (``twin_merge: açar=say …``); prod-data-ops həmin sətirləri süzür.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from ...student_group_journals import run
from .relocate_twin_enrollment import run_plan

PREFIX = "twin_merge:"


class Command(BaseCommand):
    help = "Tələbəni öz qrupunun cari jurnallarına əlavə edir (yalnız əlavə; defolt dry-run)."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--students", required=True, help="Vergüllə ayrılmış tələbə hesab id-ləri")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")

    def handle(self, *args, **options):
        try:
            ids = [int(part) for part in str(options["students"]).split(",") if part.strip()]
        except ValueError:
            raise CommandError("students_invalid") from None
        if not ids or len(ids) > 50:
            raise CommandError("students_invalid")

        def runner(organization, actor, counts):
            run(organization=organization, actor=actor, counts=counts, student_ids=ids)

        run_plan(self, options=options, prefix=PREFIX, runner=runner)
