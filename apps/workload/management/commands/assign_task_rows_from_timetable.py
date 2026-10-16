"""``assign_task_rows_from_timetable`` — Word dərs cədvəlindəki müəllimi tapşırığın BOŞ sətir fəaliyyətinə bağlar.

Forma 1 göndərməyən kafedraların tapşırıq sətirləri müəllimsiz qalıb → açılış (jurnal) yoxdur →
``import_timetable_docx`` həmin hüceyrələri ``subject_not_in_group`` kimi atır. Bu əmr cədvəldəki
«Soyad İ.» müəllimini yalnız BOŞ (bölgüsüz və ya «Vakant») fəaliyyətə yazır — rəsmi servislərlə
(``RowPlanApplier`` → düzəliş axını, açılış sinxronu, bölgü təsdiqi + tələbə qeydiyyatı). Sonra
``import_timetable_docx`` slotları yarada bilir. Qaydalar: :mod:`apps.workload.services.timetable_task_assign`.

* DEFOLT DRY-RUN — bir tranzaksiya, ``--apply`` verilməsə geri alınır (heç nə yazılmır).
* İdempotent: təkrar işə salma ``already_assigned`` verir, 0 yazı.
* Stdout-a YALNIZ saylar düşür; şəxs adları olan tam hesabat ``--report`` qovluğuna CSV kimi
  (``core.export_safety.safe_csv_writer``) — lokal/şifrəli saxlayın.

İstifadə::

    manage.py assign_task_rows_from_timetable --file cədvəl.docx --org qku --period "Payız 2026/2027" \\
        --year 2026/2027 --actor superadmin --report /tmp/tt-assign [--allow-outside-chair] [--apply]
"""

from __future__ import annotations

import re
from pathlib import Path

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.registrar.public import schedule_docx_parse
from apps.workload.services.plan_calendar import normalize_year
from apps.workload.services.task_workbook_import import Importer
from apps.workload.services.timetable_task_assign import REPORT_HEADER, TimetableTaskAssigner, parse_teacher_map
from core.export_safety import safe_csv_writer
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

REPORT_NAME = "timetable_task_assign.csv"


class _DryRunRollback(Exception):
    pass


def resolve_period(organization, raw: str):
    """«Payız 2026/2027» (ad + tədris ili) və ya dövrün UUID-i → ``AcademicPeriod`` (``import_timetable_docx`` kimi)."""
    AcademicPeriod = django_apps.get_model("organizations", "AcademicPeriod")
    value = " ".join(str(raw or "").split())
    periods = AcademicPeriod.objects.filter(organization=organization)
    if re.fullmatch(r"[0-9a-fA-F-]{36}", value):
        return periods.filter(pk=value).first()
    match = re.fullmatch(r"(.+?)\s+(\d{4})\s*[/-]\s*(\d{4})", value)
    if not match:
        return None
    name, start, end = match.groups()
    found = [
        period
        for period in periods.filter(name__iexact=name.strip())
        if re.sub(r"\D", "", period.academic_year or "") == f"{start}{end}"
    ]
    return found[0] if len(found) == 1 else None


class Command(BaseCommand):
    help = "Dərs cədvəli (.docx) → tapşırığın boş sətir fəaliyyətinə cədvəldəki müəllim — dry-run defolt."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Dərs cədvəli .docx faylı")
        parser.add_argument("--org", default="qku", help="Təşkilatın slug-ı")
        parser.add_argument("--period", required=True, help="Semestr: «Payız 2026/2027» və ya dövrün UUID-i")
        parser.add_argument("--year", default="", help="Tapşırığın tədris ili (defolt: semestrin ili)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı")
        parser.add_argument("--report", default="", help=f"Hesabat qovluğu ({REPORT_NAME} yazılır)")
        parser.add_argument(
            "--allow-outside-chair",
            action="store_true",
            help="Kafedrada tapılmayan müəllim üçün təşkilatda TƏK uyğun aktiv hesabı qəbul et (kafedraya əlavə üzv)",
        )
        parser.add_argument(
            "--teacher",
            action="append",
            default=[],
            help="Açıq müəllim xəritəsi «Soyad İ.=istifadəçi.adı» (vergüllə də olar); soyad yazılışı fərqlidirsə",
        )
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")

    def handle(self, *args, **options):
        path = Path(options["file"]).expanduser()
        if not path.is_file():
            raise CommandError("timetable_file_not_found")
        try:
            parsed = schedule_docx_parse.parse_docx(path)
        except Exception as exc:  # noqa: BLE001 — pozuq/qeyri-docx fayl
            raise CommandError(f"timetable_docx_unreadable: {type(exc).__name__}") from None
        self.assigner = None
        try:
            self._run(parsed, path, options)
        except _DryRunRollback:
            pass
        self._summary(parsed, options)
        if options["report"]:
            self._write_report(options["report"])

    def _run(self, parsed, path, options):
        Organization = django_apps.get_model("organizations", "Organization")
        with transaction.atomic(), rls_worker_atomic(), bypass_rls():
            organization = Organization.objects.filter(slug=str(options["org"]).strip()).first()
            if organization is None:
                raise CommandError("organization_not_found")
            actor_user = get_user_model().objects.filter(username=options["actor"], is_active=True).first()
            if actor_user is None or not actor_user.is_superuser:
                raise CommandError("actor_must_be_active_superuser")
            period = resolve_period(organization, options["period"])
            if period is None:
                raise CommandError("period_unknown: «Ad YYYY/YYYY» (məs. «Payız 2026/2027») və ya UUID")
            year = normalize_year(options["year"] or period.academic_year or "")
            if normalize_year(period.academic_year or "") != year:
                raise CommandError("period_year_mismatch: semestrin tədris ili --year ilə eyni olmalıdır")
            if options["apply"] and period.end_date and period.end_date < timezone.localdate():
                raise CommandError("period_closed")
            importer = Importer(
                organization=organization,
                year=year,
                actor_user=actor_user,
                apply=options["apply"],
                stdout=self.stdout,
                create_teachers=False,
                reassign=False,
            )
            importer.applier.note = f"Dərs cədvəli ({path.name[:60]}) {year} — cədvəldəki müəllim boş sətrə bağlandı"
            self.assigner = TimetableTaskAssigner(
                importer=importer,
                period=period,
                allow_outside_chair=options["allow_outside_chair"],
                teacher_map=parse_teacher_map(options["teacher"]),
            )
            self.assigner.run(parsed)
            if not options["apply"]:
                raise _DryRunRollback()

    def _summary(self, parsed, options):
        mode = "YAZILDI" if options["apply"] else "DRY-RUN"
        self.stdout.write(f"{mode}: cədvəl={parsed.tables} hüceyrə={len(parsed.entries)}")
        # Loga ŞƏXS ADI düşməsin — yalnız saylar; adlar CSV hesabatdadır.
        counters = self.assigner.all_counters()
        for key, value in sorted(counters.items()):
            self.stdout.write(f"  {key}={value}")
        if not options["apply"]:
            self.stdout.write(self.style.WARNING("DRY-RUN — heç nə yazılmadı (--apply ilə yazılır)."))

    def _write_report(self, directory):
        folder = Path(directory).expanduser()
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / REPORT_NAME
        with target.open("w", encoding="utf-8", newline="") as handle:
            writer = safe_csv_writer(handle)
            writer.writerow(REPORT_HEADER)
            for cell in self.assigner.cells:
                writer.writerow(cell.csv_row())
        self.stdout.write(f"Hesabat: {target.name} ({len(self.assigner.cells)} sətir)")
