"""``chair_journal_health`` — kafedranın jurnal sağlamlığı, hər müəllim üçün bir sətir (YALNIZ OXU; sahib 2026-10-27).

Sütunlar və qaydalar: :mod:`apps.legacy_import.services.chair_journal_health`. Müəllim YALNIZ istifadəçi id-si ilə
(ad yoxdur). Köhnə sistemə bağlı sütunlar (yanlış səviyyə, siyahıda olmayan, bölünmüş səviyyə jurnalı, köçməmiş
xanalar) yalnız ``--bundle`` verildikdə doldurulur (lokal; prod-da paket yoxdur — sütunlar boş qalır).

    manage.py chair_journal_health --org qku [--chair <uuid|slug> …] [--bundle delta.json.gz] [--format csv|md]
        [--out hesabat.csv] [--xlsx ~/EMSArena-backups/…/kafedra.xlsx]

``--xlsx`` (defolt söndürülüb) — sahib üçün ADLI Excel; yalnız repodan KƏNAR lokal yola (0600). Son sətir həmişə
``chair_health: açar=say …``.
"""

from __future__ import annotations

import os

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.legacy_import.services.chair_journal_health import (
    ChairHealth,
    outside_repo,
    resolve_chairs,
    totals,
    write_table,
    write_xlsx,
)
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

PREFIX = "chair_health:"


class Command(BaseCommand):
    help = "Kafedra jurnal sağlamlığı: hər müəllim üçün saylar (yalnız oxu; müəllim id-ləri, ad yoxdur)."

    def add_arguments(self, parser):
        parser.add_argument("--org", default="qku", help="Təşkilatın slug-ı")
        parser.add_argument("--chair", action="append", default=[], help="Kafedra (uuid və ya slug); boş = hamısı")
        parser.add_argument("--bundle", default="", help="legacy_delta_extract paketi (köhnə sistem sütunları üçün)")
        parser.add_argument("--format", choices=("csv", "md"), default="csv")
        parser.add_argument("--out", default="", help="Cədvəli fayla yaz (boş = stdout)")
        parser.add_argument("--xlsx", default="", help="ADLI Excel — yalnız repodan kənar lokal yol (defolt: yox)")

    def handle(self, *args, **options):
        if options["xlsx"] and not outside_repo(options["xlsx"]):
            raise CommandError("chair_health_xlsx_inside_repo")
        bundle = self._bundle(options["bundle"])
        Organization = django_apps.get_model("organizations", "Organization")
        AcademicPeriod = django_apps.get_model("organizations", "AcademicPeriod")
        with rls_worker_atomic(), bypass_rls():
            organization = Organization.objects.filter(slug=str(options["org"]).strip()).first()
            if organization is None:
                raise CommandError("chair_health_organization_unknown")
            with transaction.atomic():
                period = AcademicPeriod.objects.filter(organization=organization, is_current=True).first()
                if period is None:
                    raise CommandError("chair_health_no_current_period")
                try:
                    units = resolve_chairs(organization, options["chair"])
                except LookupError:
                    raise CommandError("chair_health_chair_unknown") from None
                index = None
                if bundle is not None:
                    from apps.legacy_import.services.level_journal_index import LegacyIndex

                    index = LegacyIndex(organization=organization, bundle=bundle, period=period)
                report = ChairHealth(organization, period, index=index)
                rows = report.rows(units or None)
                if options["xlsx"]:
                    write_xlsx(options["xlsx"], rows)
                transaction.set_rollback(True)  # yalnız oxu; hər ehtimala qarşı
        if options["out"]:
            descriptor = os.open(os.path.expanduser(options["out"]), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
                write_table(handle, rows, options["format"])
        else:
            write_table(self.stdout, rows, options["format"])
        summary = {**report.counts, **totals(rows), "legacy": int(index is not None)}
        self.stdout.write(PREFIX + " " + " ".join(f"{key}={value}" for key, value in sorted(summary.items())))

    @staticmethod
    def _bundle(path: str):
        if not path:
            return None
        from apps.legacy_import.services.delta.bundle import BundleError, read_bundle

        try:
            return read_bundle(os.path.expanduser(path))
        except BundleError as error:
            raise CommandError(str(error)) from None
