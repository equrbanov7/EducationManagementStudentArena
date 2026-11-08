"""``fix_ydk236_subject_20261106`` — QKU-2693 → «Ümumi xarici dil» + səhv bağlanmış VoİP jurnalları (defolt dry-run).

Qaydalar: :mod:`apps.registrar.ydk236_subject_fix_2026_11_06`. Stdout-a YALNIZ saylar (``twin_merge: açar=say …``).
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from ...ydk236_subject_fix_2026_11_06 import run
from .relocate_twin_enrollment import run_plan

PREFIX = "twin_merge:"


class Command(BaseCommand):
    help = "236 YDK: QKU-2693 kartını «Ümumi xarici dil» et, səhv bağlanmış VoİP jurnallarını QKU-2577-yə keçir."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")

    def handle(self, *args, **options):
        def runner(organization, actor, counts):
            run(organization=organization, actor=actor, counts=counts, apply=options["apply"])

        run_plan(self, options=options, prefix=PREFIX, runner=runner)
