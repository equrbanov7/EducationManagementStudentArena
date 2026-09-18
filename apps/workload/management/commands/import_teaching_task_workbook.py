"""``import_teaching_task_workbook`` — rəsmi TAPŞIRIQ kitabçasını (kafedra
başına bir vərəq) 2026/2027 tədris ilinə idxal edir.

Sahibin qərarı (2026-09-19): kitabçadakı hər sətir kafedranın tapşırıq sənədinə
düşür; fənn kataloqda yoxdursa YARADILIR; qrup yoxdursa ixtisas altında YARADILIR;
müəllim sütunu olan vərəqdə (Proqramlaşdırma) müəllimlər tapılır (yoxdursa
YARIM MƏLUMATLA yaradılır), bölgü təsdiqlənir → ``CourseOffering`` + tələbə
qeydiyyatları yaranır ki, müəllim dərhal sillabus yazıb jurnal apara bilsin.

Dry-run DEFOLTDUR; ``--apply`` yazır. İdempotentdir: mövcud sətir/təyinat/açılış
təkrarlanmır. Hesabat CSV ``--report`` qovluğuna yazılır (sirr yoxdur).

    manage.py import_teaching_task_workbook --file scripts/data/qku_tapsiriq_2026_2027.xlsx \\
        --org qku --year 2026/2027 --actor superadmin --report /tmp/tapsiriq
    ... --apply
"""

from __future__ import annotations

from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.organizations.models import Organization
from apps.workload.services.task_workbook_import import Importer
from apps.workload.services.task_workbook_parsing import parse_sheet, slug_name
from core.export_safety import safe_csv_writer
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic


class _DryRunRollback(Exception):
    """Dry-run: transaction-ı geri almaq üçün daxili siqnal."""


class Command(BaseCommand):
    help = "TAPŞIRIQ kitabçasını (kafedra vərəqləri) tədris ilinə idxal edir — dry-run defolt."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True)
        parser.add_argument("--org", default="qku")
        parser.add_argument("--year", default="2026/2027")
        parser.add_argument("--actor", required=True, help="Bölgünü təsdiqləyən superadmin istifadəçi adı")
        parser.add_argument("--report", default="", help="Hesabat CSV qovluğu")
        parser.add_argument("--sheet", action="append", default=[], help="Yalnız bu vərəq(lər) (prefiks)")
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        from openpyxl import load_workbook

        path = Path(options["file"])
        if not path.is_file():
            raise CommandError(f"file_not_found: {path}")
        workbook = load_workbook(path, read_only=True, data_only=True)
        sheets = [parse_sheet(ws) for ws in workbook.worksheets]
        workbook.close()
        wanted = [slug_name(s) for s in options["sheet"]]
        if wanted:
            sheets = [(t, r) for t, r in sheets if any(slug_name(t).startswith(w) for w in wanted)]

        # Bütün idxal BİR transaction-dadır: dry-run sonda geri alınır, --apply-də
        # istənilən xəta hər şeyi geri qaytarır (yarımçıq idxal qalmır).
        try:
            self._run(sheets, options)
        except _DryRunRollback:
            pass
        self._write_report(options)

    def _run(self, sheets, options):
        with transaction.atomic(), rls_worker_atomic(), bypass_rls():
            organization = Organization.objects.filter(slug=options["org"]).first()
            if organization is None:
                raise CommandError(f"organization_not_found: {options['org']}")
            actor_user = get_user_model().objects.filter(username=options["actor"], is_active=True).first()
            if actor_user is None or not actor_user.is_superuser:
                raise CommandError("actor_must_be_active_superuser")
            importer = Importer(
                organization=organization,
                year=options["year"],
                actor_user=actor_user,
                apply=options["apply"],
                stdout=self.stdout,
            )
            importer.ensure_periods()
            self.stdout.write(f"Təşkilat: {organization.name} · il {options['year']} · vərəq: {len(sheets)}")
            for title, records in sheets:
                importer.import_sheet(title, records)
            self.importer = importer
            if not options["apply"]:
                raise _DryRunRollback()

    def _write_report(self, options):
        importer = self.importer
        if options["report"]:
            out = Path(options["report"])
            out.mkdir(parents=True, exist_ok=True)
            fields = [
                "sheet", "line", "season", "subject_raw", "subject_action", "subject_resolved",
                "groups_raw", "groups", "teacher_raw", "teachers", "row",
            ]  # fmt: skip
            with (out / "tapsiriq_import.csv").open("w", newline="", encoding="utf-8") as handle:
                writer = safe_csv_writer(handle)
                writer.writerow(fields)
                for item in importer.report_rows:
                    writer.writerow([item.get(f, "") for f in fields])
            self.stdout.write(f"Hesabat: {out / 'tapsiriq_import.csv'}")
        summary = " · ".join(f"{k}={v}" for k, v in sorted(importer.counters.items()))
        self.stdout.write(summary)
        for label, items in (
            ("Yaradılan ixtisaslar", importer.created_specialties),
            ("Yaradılan qruplar", importer.created_groups),
            ("Yaradılan fənlər", importer.created_subjects),
            ("Yaradılan müəllimlər", importer.created_teachers),
            ("Qeyri-müəyyən müəllim (vakant qaldı, ambiguous)", importer.ambiguous_teachers),
        ):
            if items:
                self.stdout.write(f"{label} ({len(items)}): " + " | ".join(sorted(set(items)))[:4000])
        if not options["apply"]:
            self.stdout.write(self.style.WARNING("DRY-RUN — heç nə yazılmadı (--apply ilə yazılır)."))
