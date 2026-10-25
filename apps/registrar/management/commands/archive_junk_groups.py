"""``archive_junk_groups`` — test / zibil qrupları (istifadə olunmayanları) deaktiv edir (QA-2 F-16).

Qaydalar: :mod:`apps.registrar.junk_groups` — SİLİNMİR, ``is_active=False`` + ``settings.junk_archived``; istifadə
olunan (istənilən istinadı olan) vahidə toxunulmur.

* DEFOLT DRY-RUN — bir tranzaksiya, ``--apply`` verilməsə geri alınır.
* Stdout-a YALNIZ saylar; vahid-vahid CSV hesabat ``--report`` qovluğuna (qrup adları şəxsi data deyil).

İstifadə::

    manage.py archive_junk_groups --org qku [--report /tmp/junk-groups] [--apply]
"""

from __future__ import annotations

from pathlib import Path

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.registrar import junk_groups
from core.export_safety import safe_csv_writer
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

REPORT_NAME = "junk_groups.csv"
COUNTER_ORDER = ("candidates", "archive", "skip_in_use", "already_inactive")


class _DryRunRollback(Exception):
    pass


class Command(BaseCommand):
    help = "Test / zibil qrupları (istifadə olunmayan) deaktiv et — dry-run defolt, heç nə silinmir."

    def add_arguments(self, parser):
        parser.add_argument("--org", default="qku", help="Təşkilatın slug-ı")
        parser.add_argument("--report", default="", help=f"Hesabat qovluğu ({REPORT_NAME} yazılır)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")
        parser.add_argument(
            "--idle-under",
            default="",
            help="Bu adlı vahidin (fakültə) alt-ağacında aktiv tələbəsi və cari açılışı OLMAYAN qrupları deaktiv et",
        )

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
            if options["idle_under"]:
                rows = junk_groups.plan_idle_under(organization, options["idle_under"].strip())
            else:
                rows = junk_groups.plan(organization)
            junk_groups.apply(rows)
            self.counts = junk_groups.counters(rows)
            self.rows = [row.csv_row() for row in rows]
            if not options["apply"]:
                raise _DryRunRollback()

    def _write_report(self, directory):
        folder = Path(directory).expanduser()
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / REPORT_NAME
        with target.open("w", encoding="utf-8", newline="") as handle:
            writer = safe_csv_writer(handle)
            writer.writerow(junk_groups.REPORT_HEADER)
            writer.writerows(self.rows)
        self.stdout.write(f"Hesabat: {target.name} ({len(self.rows)} sətir)")
