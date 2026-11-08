"""``repair_legacy_identity_20261108`` — başqasının FİN-i ilə köçmüş xana / qeydiyyatların düzəlişi (defolt dry-run).

Qaydalar: :mod:`apps.registrar.legacy_identity_repair_2026_11_08`. Plan defolt olaraq modulun yanındakı JSON-dur
(yalnız id-lər). ``--undo`` bu əmrin dəyişdiklərini (sonradan dəyişməyibsə) geri qaytarır. Stdout-a YALNIZ saylar
(``legacy_identity: <hal>_<açar>=say …``).
"""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand

from ... import legacy_identity_repair_2026_11_08 as repair
from .relocate_twin_enrollment import run_plan

PREFIX = "legacy_identity:"
DEFAULT_PLAN = Path(repair.__file__).with_suffix(".json")


class Command(BaseCommand):
    help = "Sahib 2026-11-08: köhnə sistemdə başqasının FİN-i — xana və qeydiyyatlar düzgün adama (defolt dry-run)."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--file", default=str(DEFAULT_PLAN), help="legacy-identity/1 JSON planı")
        parser.add_argument("--undo", action="store_true", help="Bu əmrin dəyişdiklərini geri qaytar")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")

    def handle(self, *args, **options):
        cases = [] if options["undo"] else repair.load_plan(options["file"])

        def runner(organization, actor, counts):
            if options["undo"]:
                repair.undo(organization=organization, actor=actor, counts=counts)
            else:
                repair.run(organization=organization, actor=actor, counts=counts, cases=cases)

        run_plan(self, options=options, prefix=PREFIX, runner=runner)
