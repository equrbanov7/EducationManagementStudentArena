"""``ensure_parent_groups`` — alt qruplar («234 K-1», «234 K-2») üçün ORTAQ ana qrup («234 K az»).

Sahib 2026-10-17: «234 K-1 var, 234 K-2 var, onların ortaq qrupu 234 K da olsun. Bəziləri var,
olmayanları doldur.» Qaydalar: :mod:`apps.registrar.parent_groups` (``group_split`` modeli — ana qrup
eyni ixtisas altında qardaşdır, alt qrupda ``settings.parent_group`` izi; tələbə KÖÇÜRÜLMÜR).

* DEFOLT DRY-RUN — bir tranzaksiya, ``--apply`` verilməsə geri alınır (heç nə yazılmır).
* İdempotent: təkrar ``--apply`` 0 yaradır, 0 bağlayır.
* Stdout-a YALNIZ saylar; ailə-ailə CSV hesabat ``--report`` qovluğuna (qrup adları şəxsi data deyil).

İstifadə::

    manage.py ensure_parent_groups --org qku [--report /tmp/parent-groups] [--apply]
"""

from __future__ import annotations

from pathlib import Path

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.registrar.parent_groups import REPORT_HEADER, ParentGroupPlanner, counters, report_rows
from core.export_safety import safe_csv_writer
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

REPORT_NAME = "parent_groups.csv"
COUNTER_ORDER = (
    "families",
    "parents_existing",
    "parents_created",
    "subgroups_linked",
    "subgroups_already_linked",
    "ambiguous",
)


class _DryRunRollback(Exception):
    pass


class Command(BaseCommand):
    help = "Alt qruplar üçün ortaq ana qrupu yarat / bağla (settings.parent_group) — dry-run defolt."

    def add_arguments(self, parser):
        parser.add_argument("--org", default="qku", help="Təşkilatın slug-ı")
        parser.add_argument("--report", default="", help=f"Hesabat qovluğu ({REPORT_NAME} yazılır)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")

    def handle(self, *args, **options):
        self.rows: list = []
        self.counts: dict = {}
        try:
            self._run(options)
        except _DryRunRollback:
            pass
        mode = "YAZILDI" if options["apply"] else "DRY-RUN (heç nə yazılmadı)"
        self.stdout.write(f"{mode}: " + " · ".join(f"{key}={self.counts.get(key, 0)}" for key in COUNTER_ORDER))
        if options["report"]:
            self._write_report(options["report"])

    def _run(self, options):
        Organization = django_apps.get_model("organizations", "Organization")
        with transaction.atomic(), rls_worker_atomic(), bypass_rls():
            organization = Organization.objects.filter(slug=str(options["org"]).strip()).first()
            if organization is None:
                raise CommandError("organization_not_found")
            planner = ParentGroupPlanner(organization)
            families = planner.plan()
            planner.apply(families)
            self.counts = counters(families)
            self.rows = list(report_rows(families))
            if not options["apply"]:
                raise _DryRunRollback()

    def _write_report(self, directory):
        folder = Path(directory).expanduser()
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / REPORT_NAME
        with target.open("w", encoding="utf-8", newline="") as handle:
            writer = safe_csv_writer(handle)
            writer.writerow(REPORT_HEADER)
            writer.writerows(self.rows)
        self.stdout.write(f"Hesabat: {target.name} ({len(self.rows)} sətir)")
