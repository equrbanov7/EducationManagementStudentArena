"""``import_students_atis`` — ATİS qəbul ixracını («Bakalavr. 08.09.26.xlsx» formatı)
tələbə idxalı boru xətti ilə (`services.intake`) toplu yükləyir.

Sahibin qərarı (2026-09-19): UI-dakı «Tələbə idxalı» ilə EYNİ plan qurucusu
(`build_plans`) və EYNİ tətbiq (`apply_plans`) — ayrıca parser yoxdur. Qrup faylda
olmadığı üçün ixtisas şifri + tədris dili + qəbul ilinə görə avtomatik təklif
olunur (yalnız həmin qəbul ilinin qrupları); təklif tapılmayan sətir «qrup yoxdur»
kimi hesabatda qalır və UI-dan tamamlanır.

Dry-run DEFOLTDUR; ``--apply`` yazır. İstehsalda yalnız icra-başına ACK ilə
(`MANAGEMENT_COMMAND_PRODUCTION_ACK=import_students_atis`). İlkin parollar
YALNIZ ``--credentials`` faylına yazılır (ekranda görünmür).

    manage.py import_students_atis --file /tmp/bakalavr.xlsx --org qku --actor superadmin \\
        --report /tmp/atis_report.csv
    ... --apply --credentials /tmp/atis_creds.csv
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.services import intake
from apps.organizations.models import Organization
from core.export_safety import safe_csv_writer
from core.management.command_safety import ProductionCommandSafetyMixin
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic


class _Upload:
    """`intake.read_rows` üçün minimal fayl obyekti (ad + ölçü + read)."""

    def __init__(self, path: Path):
        self.name = path.name
        self.size = path.stat().st_size
        self._path = path

    def read(self) -> bytes:
        return self._path.read_bytes()


class Command(ProductionCommandSafetyMixin, BaseCommand):
    help = "ATİS qəbul ixracını tələbə idxalı boru xətti ilə yükləyir (dry-run defolt)."
    safety_command_name = "import_students_atis"

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True)
        parser.add_argument("--org", default="qku")
        parser.add_argument("--actor", required=True, help="İdxalı edən superadmin istifadəçi adı (audit)")
        parser.add_argument("--report", default="", help="Sətir-sətir nəticə CSV (parolsuz)")
        parser.add_argument("--credentials", default="", help="--apply: username/ilkin parol CSV (yalnız fayla)")
        parser.add_argument("--only-program", action="append", default=[], help="Yalnız bu rəsmi şifr(lər)")
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        path = Path(options["file"])
        if not path.is_file():
            raise CommandError(f"file_not_found: {path}")
        if options["apply"] and not options["credentials"]:
            raise CommandError("--apply üçün --credentials faylı tələb olunur (parollar yalnız oraya yazılır)")

        with rls_worker_atomic(), bypass_rls():
            organization = Organization.objects.filter(slug=options["org"]).first()
            if organization is None:
                raise CommandError(f"organization_not_found: {options['org']}")
            actor = get_user_model().objects.filter(username=options["actor"], is_active=True).first()
            if actor is None or not actor.is_superuser:
                raise CommandError("actor_must_be_active_superuser")
            rows = intake.read_rows(_Upload(path))
            wanted = {code.strip() for code in options["only_program"] if code.strip()}
            if wanted:
                rows = [row for row in rows if str(row.get("program_code") or "").strip() in wanted]
            plans = intake.build_plans(organization, rows)
            summary = intake.summarize(plans)
            codes = Counter(plan.code for plan in plans)
            no_group = sum(1 for plan in plans if plan.status == "create" and plan.targets.get("group") is None)
            self.stdout.write(
                f"Sətir: {summary['total']} · yaradılacaq: {summary['create']} · ötürülən: {summary['skip']} · "
                f"xəta: {summary['error']} · qrupsuz (təklif yoxdur): {no_group}"
            )
            for code, count in codes.most_common():
                self.stdout.write(f"  {code}: {count}")
            groups = Counter(plan.group_name for plan in plans if plan.status == "create" and plan.group_name)
            self.stdout.write("Qrup bölgüsü: " + ", ".join(f"{name}={n}" for name, n in sorted(groups.items())))

            if options["report"]:
                self._write_report(Path(options["report"]), plans)

            if not options["apply"]:
                self.stdout.write(self.style.WARNING("DRY-RUN — heç nə yazılmadı (--apply ilə yazılır)."))
                return

            # Qrupsuz sətirlər YAZILMIR (reyestr qrup tələb edir) — hesabatda qalır.
            for plan in plans:
                if plan.status == "create" and plan.targets.get("group") is None:
                    plan.skip("group_unassigned", "Qrup təklifi yoxdur — UI-dan qrup seçin.")
            with transaction.atomic():
                result = intake.apply_plans(organization=organization, plans=plans, actor=actor)
            creds = Path(options["credentials"])
            creds.parent.mkdir(parents=True, exist_ok=True)
            with creds.open("w", newline="", encoding="utf-8") as handle:
                writer = safe_csv_writer(handle)
                writer.writerow(["username", "ilkin_parol", "ad_soyad", "fin", "qrup"])
                for item in result.get("credentials", []):
                    writer.writerow([item["username"], item["password"], item["full_name"], item["fin"], item["group"]])
            self.stdout.write(
                self.style.SUCCESS(
                    f"Yazıldı: yaradıldı={result['summary']['created']} · xəta={result['summary']['error']} · "
                    f"ötürüldü={result['summary']['skip']} · parollar: {creds}"
                )
            )

    def _write_report(self, path: Path, plans) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = safe_csv_writer(handle)
            writer.writerow(["setir", "status", "kod", "mesaj", "fin", "ad_soyad", "username", "qrup", "xeberdarliq"])
            for plan in plans:
                writer.writerow(
                    [
                        plan.row,
                        plan.status,
                        plan.code,
                        plan.message,
                        plan.fin,
                        plan.full_name,
                        plan.username,
                        plan.group_name,
                        " | ".join(plan.warnings),
                    ]
                )
        self.stdout.write(f"Hesabat: {path}")
