"""``resolve_subgroup_families_20261108`` — ana qrup / alt qrup jurnal ailələri: birləşdir və ya ana jurnalı yığışdır.

Qaydalar: :mod:`apps.registrar.subgroup_family_resolve_2026_11_08`. Defolt dry-run. ``--undo`` YALNIZ ana jurnalın
yığışdırılmasını qaytarır (birləşmələr — ``merge_subgroup_journals_20261108 --undo``). Stdout-a yalnız saylar.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from ...subgroup_family_resolve_2026_11_08 import Resolver, discover
from ...subgroup_parent_retire_2026_11_08 import undo
from .relocate_twin_enrollment import run_plan

PREFIX = "subgroup_resolve:"


class Command(BaseCommand):
    help = "Sahib 2026-11-08: ana/alt qrup jurnal ailələri — birləşmə və ya ana jurnalın yığışdırılması (dry-run)."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--undo", action="store_true", help="Ana jurnalın yığışdırılmasını geri qaytar")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")

    def handle(self, *args, **options):
        report = []

        def runner(organization, actor, counts):
            if options["undo"]:
                undo(organization=organization, actor=actor, counts=counts)
                return
            families = discover(organization)
            counts["families_found"] = len(families)
            resolver = Resolver(organization=organization, actor=actor, counts=counts)
            resolver.run(families)
            report.extend(resolver.report)

        run_plan(self, options=options, prefix=PREFIX, runner=runner)
        for index, delta in report:
            pairs = " ".join(f"{key}={value}" for key, value in sorted(delta.items()))
            self.stdout.write(f"{PREFIX} family={index} {pairs}".rstrip())
