"""``import_teaching_task_workbook`` — rəsmi TAPŞIRIQ kitabçasını (kafedra
başına bir vərəq) 2026/2027 tədris ilinə idxal edir.

Sahibin qərarı (2026-09-19): kitabçadakı hər sətir kafedranın tapşırıq sənədinə
düşür; fənn kataloqda yoxdursa YARADILIR; qrup yoxdursa ixtisas altında YARADILIR;
müəllim sütunu olan vərəqdə (Proqramlaşdırma) müəllimlər tapılır (yoxdursa
YARIM MƏLUMATLA yaradılır), bölgü təsdiqlənir → ``CourseOffering`` + tələbə
qeydiyyatları yaranır ki, müəllim dərhal sillabus yazıb jurnal apara bilsin.

Dry-run DEFOLTDUR; ``--apply`` yazır. İdempotentdir: mövcud sətir/təyinat/açılış
təkrarlanmır. Hesabat CSV ``--report`` qovluğuna yazılır (şəxs adları/istifadəçi adları var —
yalnız lokal/şifrəli saxlanılır); stdout-a YALNIZ saylar düşür.

2026-10-12 (paylanmış oktyabr kitabçası): seçmə blokunda seçilən bənd QALIN şriftlə
(zəngin mətn ikinci keçidlə oxunur); işarəsiz blok ``--choice LINE=N`` (və ya
``LINE=Fənn adı``) ilə operator tərəfindən seçilə bilər, yoxsa ötürülür;
``--reassign`` — tutuşan sətrin müəllimi fayldakından fərqlidirsə düzəliş axını ilə
dəyişdirilir; ``--no-create-teachers`` — heç bir hesab/üzvlük yaradılmır (prod workflow).

    manage.py import_teaching_task_workbook --file backups/data_private/qku_tapsiriq_2026_2027.xlsx \\
        --org qku --year 2026/2027 --actor superadmin --report /tmp/tapsiriq
    ... --apply
"""

from __future__ import annotations

from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.organizations.models import Organization
from apps.workload.services.task_workbook_choice import (
    CHOSEN_OVERRIDE,
    ChoiceError,
    choose_block_subject,
    parse_choice_overrides,
    rich_subject_map,
)
from apps.workload.services.task_workbook_import import Importer
from apps.workload.services.task_workbook_parsing import is_block, parse_sheet, slug_name
from core.export_safety import safe_csv_writer
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic


def parse_teacher_map(values) -> dict:
    """``["MURAD=murad.x,VƏFA=vefa.y"]`` → ``{"murad": "murad.x", "vefa": "vefa.y"}``."""
    result = {}
    for value in values or []:
        for part in value.split(","):
            token, sep, username = part.partition("=")
            if not sep or not slug_name(token) or not username.strip():
                raise CommandError(f"--teacher formatı AD=istifadəçi.adı olmalıdır: {part!r}")
            result[slug_name(token)] = username.strip()
    return result


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
        parser.add_argument(
            "--reassign", action="store_true", help="Tutuşan sətrin fərqli müəllimini düzəliş axını ilə dəyiş"
        )
        parser.add_argument(
            "--no-create-teachers",
            action="store_true",
            help="Müəllim hesabı/üzvlüyü YARATMA — yalnız kafedranın aktiv müəllimləri; qalanı hesabatda",
        )
        parser.add_argument(
            "--choice",
            action="append",
            default=[],
            help="İşarəsiz seçmə bloku üçün operator seçimi: LINE=N (bənd nömrəsi) və ya LINE=Fənn adı; "
            "vergüllə də olar: 144=1,145=1. Yalnız tək vərəqlə (--sheet) işləyir.",
        )
        parser.add_argument(
            "--teacher",
            action="append",
            default=[],
            help="Qeyri-müəyyən ad işarəsinin açıq həlli: AD=istifadəçi.adı (vergüllə bir neçəsi).",
        )

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
        sheets = self._apply_choices(path, sheets, options["choice"])

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
                create_teachers=not options["no_create_teachers"],
                reassign=options["reassign"],
            )
            importer.teacher_map = parse_teacher_map(options["teacher"])
            importer.ensure_periods()
            self.stdout.write(f"Təşkilat: {organization.name} · il {options['year']} · vərəq: {len(sheets)}")
            for title, records in sheets:
                importer.import_sheet(title, records)
            self.importer = importer
            if not options["apply"]:
                raise _DryRunRollback()

    def _apply_choices(self, path, sheets, raw_choices):
        """Zəngin mətn keçidi: blok xanalarının seçimi (qalın > «+» > tək bənd > --choice)."""
        try:
            overrides = parse_choice_overrides(raw_choices)
        except ChoiceError as exc:
            raise CommandError(str(exc)) from exc
        if overrides and len(sheets) != 1:
            raise CommandError("--choice yalnız TƏK vərəqlə (--sheet) işlənir")
        rich = rich_subject_map(path, {title for title, _ in sheets})
        result = []
        for title, records in sheets:
            cells = rich.get(title, {})
            used = set()
            for record in records:
                if not is_block(record["subject_text"]):
                    record.update(chosen_subject="", chosen_by="")
                    continue
                override = overrides.get(record["line"], "")
                try:
                    chosen, how = choose_block_subject(cells.get(record["line"], record["subject_text"]), override)
                except ChoiceError as exc:
                    raise CommandError(f"--choice {record['line']}: {exc}") from exc
                if override:
                    if how != CHOSEN_OVERRIDE:
                        raise CommandError(f"--choice {record['line']}: xanada artıq seçim işarəsi var ({how})")
                    used.add(record["line"])
                record.update(chosen_subject=chosen, chosen_by=how)
            unknown = sorted(set(overrides) - used)
            if unknown:
                raise CommandError(f"--choice: bu sətirlər seçmə bloku deyil və ya vərəqdə yoxdur: {unknown}")
            result.append((title, records))
        return result

    def _write_report(self, options):
        importer = self.importer
        if options["report"]:
            out = Path(options["report"])
            out.mkdir(parents=True, exist_ok=True)
            fields = [
                "sheet", "line", "season", "groups_raw", "subject_raw", "chosen_subject", "chosen_by",
                "subject_action", "subject_resolved", "groups", "teacher_raw", "teachers", "row", "assignment",
            ]  # fmt: skip
            with (out / "tapsiriq_import.csv").open("w", newline="", encoding="utf-8") as handle:
                writer = safe_csv_writer(handle)
                writer.writerow(fields)
                for item in importer.report_rows:
                    writer.writerow([item.get(f, "") for f in fields])
            self.stdout.write(f"Hesabat: {out / 'tapsiriq_import.csv'}")
        counters = importer.counters + importer.applier.counters
        for item in importer.report_rows:
            if item.get("chosen_by"):
                counters[f"chosen_by_{item['chosen_by']}"] += 1
        summary = " · ".join(f"{k}={v}" for k, v in sorted(counters.items()))
        self.stdout.write(summary)
        # Loga ŞƏXS ADI düşməsin (prod workflow logu) — yalnız saylar; adlar CSV hesabatdadır.
        for label, items in (
            ("Yaradılan ixtisaslar", importer.created_specialties),
            ("Yaradılan qruplar", importer.created_groups),
            ("Yaradılan fənlər", importer.created_subjects),
            ("Yaradılan müəllimlər", importer.created_teachers),
            ("Qeyri-müəyyən müəllim (ambiguous)", importer.ambiguous_teachers),
        ):
            if items:
                self.stdout.write(f"{label}: {len(set(items))}")
        if not options["apply"]:
            self.stdout.write(self.style.WARNING("DRY-RUN — heç nə yazılmadı (--apply ilə yazılır)."))
