"""``recover_mr230_lessons`` — RİM MR-000230: 236 İT «İnformasiya texnologiyalarının əsasları» dərsləri + xanaları.

Qaydalar: :mod:`apps.registrar.mr230_lesson_recovery` (köhnə sistem 15209 ilə tutuşdurulmuş sabit spesifikasiya; plan
faylı yoxdur). DEFOLT DRY-RUN; ``--undo`` yalnız bu əmrin audit izinə görə geri qaytarır. Stdout-a YALNIZ saylar
(``twin_merge: açar=say …``); prod-data-ops həmin sətirləri süzür.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from ...mr230_lesson_recovery import recover, undo
from .relocate_twin_enrollment import run_plan

PREFIX = "twin_merge:"


class Command(BaseCommand):
    help = "MR-000230: 236 İT «İT əsasları» jurnalına köhnə sistemin çatışmayan dərsləri və xanaları (defolt dry-run)."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")
        parser.add_argument("--undo", action="store_true", help="Bu əmrin yazdıqlarını audit izinə görə geri qaytar")

    def handle(self, *args, **options):
        step = undo if options["undo"] else recover

        def runner(organization, actor, counts):
            step(organization=organization, actor=actor, counts=counts)

        run_plan(self, options=options, prefix=PREFIX, runner=runner)
