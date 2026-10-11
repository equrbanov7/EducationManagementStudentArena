"""``import_teaching_load_form1`` — kafedranın «Forma 1» dərs yükü cədvəlindən (Word)
müəllim bölgüsü (sahib 2026-10-12: Təbiət elmləri, İnformasiya texnologiyaları).

Sətir/fənn/hesab YARADILMIR: Forma 1 sətri kafedranın 2026/2027 tapşırıq sətrinə tutuşdurulur
(:mod:`apps.workload.services.task_form1_import`), müəllim yalnız bu kafedranın aktiv
müəllimlərindən tam adla tapılır. Bölgüsüz sətir — ilk təyinat; fərqli müəllim — yalnız
``--reassign`` ilə (düzəliş axını, blokerlər — :mod:`.task_load_reassign`).

Dry-run DEFOLTDUR. Hesabat CSV-də (``--report``) şəxs adları var — yalnız lokal/şifrəli;
stdout-a YALNIZ saylar düşür.

    manage.py import_teaching_load_form1 --file forma1.docx --chair "Təbiət elmləri kafedrası" \\
        --year 2026/2027 --actor superadmin --report /tmp/forma1 [--choice 20=1] [--reassign] [--apply]
"""

from __future__ import annotations

from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.organizations.models import Organization
from apps.workload.models import TeachingTask
from apps.workload.services.task_form1_import import Form1Importer, find_chair
from apps.workload.services.task_form1_parsing import parse_form1
from apps.workload.services.task_workbook_choice import ChoiceError, parse_choice_overrides
from apps.workload.services.task_workbook_import import Importer
from core.export_safety import safe_csv_writer
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

REPORT_FIELDS = [
    "line", "season", "teacher", "teacher_action", "username", "hourly", "groups", "subject",
    "chosen_subject", "chosen_by", "hours", "rows", "score", "assignment",
]  # fmt: skip


class _DryRunRollback(Exception):
    pass


def parse_teacher_names(values) -> dict:
    """``["Soyad Ad=istifadəçi", …]`` (vergüllə də) → ``{"Soyad Ad": "istifadəçi"}``."""
    result = {}
    for value in values or []:
        for part in value.split(","):
            name, sep, username = part.partition("=")
            if not sep or not name.strip() or not username.strip():
                raise CommandError(f"--teacher formatı «Soyad Ad=istifadəçi.adı» olmalıdır: {part!r}")
            result[name.strip()] = username.strip()
    return result


class Command(BaseCommand):
    help = "«Forma 1» dərs yükü (docx) → kafedranın tapşırıq sətirlərinə müəllim bölgüsü — dry-run defolt."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True)
        parser.add_argument("--chair", required=True, help="Kafedra adı («Təbiət elmləri kafedrası»)")
        parser.add_argument("--org", default="qku")
        parser.add_argument("--year", default="2026/2027")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı")
        parser.add_argument("--report", default="", help="Hesabat CSV qovluğu")
        parser.add_argument(
            "--choice", action="append", default=[], help="İşarəsiz blok: SƏTİR=N (cədvəl sətri, 0-dan)"
        )
        parser.add_argument("--teacher", action="append", default=[], help="«Soyad Ad=istifadəçi.adı»")
        parser.add_argument("--reassign", action="store_true")
        parser.add_argument(
            "--allow-outside-chair",
            action="store_true",
            help="Kafedrada tapılmayan müəllim üçün təşkilatda TƏK uyğun aktiv hesabı qəbul et (başqa kafedra/rol)",
        )
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        from docx import Document

        path = Path(options["file"])
        if not path.is_file():
            raise CommandError(f"file_not_found: {path}")
        try:
            overrides = parse_choice_overrides(options["choice"])
            entries, skipped = parse_form1(Document(str(path)), overrides)
        except (ChoiceError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        teacher_map = parse_teacher_names(options["teacher"])
        try:
            self._run(entries, skipped, teacher_map, options)
        except _DryRunRollback:
            pass
        self._write_report(options)

    def _run(self, entries, skipped, teacher_map, options):
        with transaction.atomic(), rls_worker_atomic(), bypass_rls():
            organization = Organization.objects.filter(slug=options["org"]).first()
            if organization is None:
                raise CommandError(f"organization_not_found: {options['org']}")
            actor_user = get_user_model().objects.filter(username=options["actor"], is_active=True).first()
            if actor_user is None or not actor_user.is_superuser:
                raise CommandError("actor_must_be_active_superuser")
            chair = find_chair(organization, options["chair"])
            if chair is None:
                raise CommandError("chair_not_found_or_ambiguous")
            task = TeachingTask.objects.filter(
                organization=organization, chair=chair, academic_year=options["year"]
            ).first()
            if task is None:
                raise CommandError("teaching_task_not_found: əvvəlcə TAPŞIRIQ kitabçası idxal olunmalıdır")
            importer = Importer(
                organization=organization,
                year=options["year"],
                actor_user=actor_user,
                apply=options["apply"],
                stdout=self.stdout,
                create_teachers=False,
                reassign=options["reassign"],
            )
            importer.applier.note = f"«Forma 1» dərs yükü {options['year']} — müəllim bölgüsü sənədə uyğunlaşdırıldı"
            form1 = Form1Importer(
                importer=importer,
                chair=chair,
                teacher_map=teacher_map,
                allow_outside_chair=options["allow_outside_chair"],
            )
            self.stdout.write(f"Forma 1: {len(entries)} yük sətri · tapşırıq sətri {task.rows.count()}")
            form1.run(task, entries, skipped)
            self.form1 = form1
            if not options["apply"]:
                raise _DryRunRollback()

    def _write_report(self, options):
        form1 = self.form1
        if options["report"]:
            out = Path(options["report"])
            out.mkdir(parents=True, exist_ok=True)
            with (out / "forma1_import.csv").open("w", newline="", encoding="utf-8") as handle:
                writer = safe_csv_writer(handle)
                writer.writerow(REPORT_FIELDS)
                for item in form1.report_rows:
                    writer.writerow([item.get(f, "") for f in REPORT_FIELDS])
            self.stdout.write(f"Hesabat: {out / 'forma1_import.csv'}")
        counters = form1.counters + form1.applier.counters + form1.importer.counters
        for item in form1.report_rows:
            if item.get("chosen_by"):
                counters[f"chosen_by_{item['chosen_by']}"] += 1
        # Loga ŞƏXS ADI düşməsin — yalnız saylar; adlar CSV hesabatdadır.
        self.stdout.write(" · ".join(f"{k}={v}" for k, v in sorted(counters.items())))
        if not options["apply"]:
            self.stdout.write(self.style.WARNING("DRY-RUN — heç nə yazılmadı (--apply ilə yazılır)."))
