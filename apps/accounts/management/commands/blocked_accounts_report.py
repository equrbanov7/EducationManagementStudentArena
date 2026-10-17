"""``blocked_accounts_report`` — bloklanmış / deaktiv hesabların hesabatı (sahib 2026-10-17).

Qaydalar: :mod:`apps.accounts.services.blocked_accounts`. Şübhəli hallar: cari semestrdə yükü olan
bloklanmış MÜƏLLİM, aktiv akademik qeydi / qeydiyyatı olan bloklanmış TƏLƏBƏ. QA hesabları (``qa.*``)
hesabata düşmür.

* DEFOLT YALNIZ HESABAT — heç nə yazılmır (tranzaksiya geri alınır).
* ``--apply-unblock-teachers-with-load`` — YALNIZ bloklanmış + cari yükü olan müəllimləri rəsmi
  ``account_deletion.unblock_account`` (audit) ilə açır. Tələbələr HEÇ VAXT avtomatik açılmır.
* Stdout-a YALNIZ saylar; istifadəçi adları olan CSV ``--report`` qovluğuna (ŞƏXSİ DATA — şifrəli saxlayın).

İstifadə::

    manage.py blocked_accounts_report --org qku --report /tmp/blocked [--apply-unblock-teachers-with-load --actor ad]
"""

from __future__ import annotations

from pathlib import Path

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.services.blocked_accounts import REPORT_HEADER, BlockedAccountsReport
from core.export_safety import safe_csv_writer
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

REPORT_NAME = "blocked_accounts.csv"
COUNTER_ORDER = (
    "total",
    "blocked",
    "deleted",
    "archived",
    "staged",
    "membership_inactive",
    "teacher_with_load",
    "teacher_with_load_blocked",
    "student_enrolled",
    "archived_record_enrolled",
    "unblocked",
    "qa_skipped",
    "no_current_period",
)


class _ReportOnly(Exception):
    pass


class Command(BaseCommand):
    help = "Bloklanmış/deaktiv hesablar: hesabat (defolt) + yükü olan müəllimlərin blokunu açmaq (bayraqla)."

    def add_arguments(self, parser):
        parser.add_argument("--org", default="qku", help="Təşkilatın slug-ı")
        parser.add_argument("--report", default="", help=f"Hesabat qovluğu ({REPORT_NAME} yazılır)")
        parser.add_argument(
            "--apply-unblock-teachers-with-load",
            action="store_true",
            dest="unblock",
            help="Cari semestrdə yükü olan BLOKLANMIŞ müəllimləri rəsmi servislə aç (tələbələrə toxunmur)",
        )
        parser.add_argument("--actor", default="", help="Audit üçün aktiv superadmin istifadəçi adı (opsional)")

    def handle(self, *args, **options):
        self.report = None
        try:
            self._run(options)
        except _ReportOnly:
            pass
        counts = self.report.counters()
        mode = "YAZILDI" if options["unblock"] else "HESABAT (heç nə yazılmadı)"
        self.stdout.write(f"{mode}: " + " · ".join(f"{key}={counts.get(key, 0)}" for key in COUNTER_ORDER))
        if options["report"]:
            self._write_report(options["report"])

    def _run(self, options):
        Organization = django_apps.get_model("organizations", "Organization")
        with transaction.atomic(), rls_worker_atomic(), bypass_rls():
            organization = Organization.objects.filter(slug=str(options["org"]).strip()).first()
            if organization is None:
                raise CommandError("organization_not_found")
            actor = None
            if options["actor"]:
                actor = get_user_model().objects.filter(username=options["actor"], is_active=True).first()
                if actor is None or not actor.is_superuser:
                    raise CommandError("actor_must_be_active_superuser")
            self.report = BlockedAccountsReport(organization)
            if not options["unblock"]:
                raise _ReportOnly()
            self.report.unblock_teachers_with_load(actor=actor)

    def _write_report(self, directory):
        folder = Path(directory).expanduser()
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / REPORT_NAME
        with target.open("w", encoding="utf-8", newline="") as handle:
            writer = safe_csv_writer(handle)
            writer.writerow(REPORT_HEADER)
            for row in self.report.rows:
                writer.writerow(row.csv_row())
        self.stdout.write(f"Hesabat: {target.name} ({len(self.report.rows)} sətir)")
