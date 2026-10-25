"""``freeze_duplicate_accounts`` — dublikat heyət hesablarını tapır, jurnallı hesabı saxlayıb digərlərini dondurur.

Sahib (2026-10-25): «Dublikat hesabdırsa — hal-hazırda jurnalı yazdığı hesabı saxla, digərlərini dondur.»
Qaydalar: ``apps.accounts.services.duplicate_accounts.plan`` (eyni şəxs, saxlanılan hesabın seçimi, xüsusi hal).
Dublikatları DB-dən özü tapır — giriş faylı lazım deyil.

* defolt — DRY-RUN, stdout-a YALNIZ saylar; ``--report DIR`` → ``duplicate_accounts.csv`` + ``.md`` (0600),
  ``--markdown FAYL`` → adlı Markdown hesabat (0600);
* ``--apply`` — rollar/rəhbərlik saxlanılana, cari jurnallar rəsmi «Fənn təhvili» ilə saxlanılana, dublikatın
  üzvlükləri deaktiv, hesab «Hesabı dayandır» ilə dondurulur (paket ``dupacct-…``);
* ``--undo <paket>`` — paketi geri qaytarır. Təkrar ``--apply`` → 0 yazı (idempotent).

Qapılar: repetisiya markeri olmayan bazada yazı üçün ``--i-know-this-is-production``; ``--actor`` «Fənn təhvili»
icazəsi (``journal.reassign``) olan hesab olmalıdır (defolt: təşkilatın sahibi).
"""

from __future__ import annotations

import io
import pathlib

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.services.duplicate_accounts import apply as dup_apply
from apps.accounts.services.duplicate_accounts import plan as dup_plan
from apps.accounts.services.duplicate_accounts import report as dup_report
from apps.accounts.services.staff_placement.report import write_private
from apps.accounts.services.teacher_roster.apply import RosterError
from core.rls import apply_rls_request_context, bypass_rls
from core.rls_pooling import rls_worker_atomic

from .reconcile_teacher_roster import _disposable_database

CSV_NAME = "duplicate_accounts.csv"
MD_NAME = "duplicate_accounts.md"


def _counts(data: dict) -> str:
    return " · ".join(f"{key}={value}" for key, value in data.items())


class Command(BaseCommand):
    help = "Dublikat heyət hesabları: jurnallı hesab saxlanılır, digərləri dondurulur (dry-run defolt)."

    def add_arguments(self, parser):
        parser.add_argument("--org", "--organization", dest="org", required=True, help="Təşkilatın slug-ı (qku)")
        parser.add_argument("--academic-year", default="2026/2027", help="Dərs yükünün tədris ili")
        parser.add_argument("--report", default="", help="Hesabat qovluğu (CSV + Markdown, 0600)")
        parser.add_argument("--markdown", default="", help="Adlı Markdown hesabatın yolu (0600)")
        parser.add_argument("--apply", action="store_true", help="Dəyişiklikləri YAZ (defolt: yalnız hesabat)")
        parser.add_argument("--undo", default="", help="dupacct-… paketini geri qaytar")
        parser.add_argument("--reason", default="", help="Səbəb (≥20 simvol; defolt — sahibin 2026-10-25 qərarı)")
        parser.add_argument("--actor", default="", help="Aktorun istifadəçi adı (defolt: təşkilatın sahibi)")
        parser.add_argument("--i-know-this-is-production", action="store_true", help="Markersiz bazada icazə")

    def handle(self, *args, **options):
        organization = (
            django_apps.get_model("organizations", "Organization")
            .objects.filter(slug=str(options["org"]).strip())
            .first()
        )
        if organization is None:
            raise CommandError(f"dupacct_organization_unknown: {options['org']!r}")
        user_model = django_apps.get_model("auth", "User")
        username = str(options["actor"] or "").strip()
        actor = user_model._default_manager.filter(username=username).first() if username else organization.owner
        if actor is None:
            raise CommandError("dupacct_actor_unknown")
        if (options["apply"] or options["undo"]) and not (
            _disposable_database() or options["i_know_this_is_production"]
        ):
            raise CommandError("dupacct_target_not_disposable: real bazada --i-know-this-is-production verin.")
        with rls_worker_atomic(), bypass_rls():
            apply_rls_request_context(user_id=actor.pk, org_id=organization.pk)
            if options["undo"]:
                try:
                    result = dup_apply.undo(options["undo"].strip(), actor=actor, reason=options["reason"])
                except RosterError as error:
                    raise CommandError(f"dupacct_{error.code}") from None
                self.stdout.write(f"YAZILDI: {_counts(result)}")
                return
            self._run(organization, actor, options)

    def _run(self, organization, actor, options):
        plan = dup_plan.build(organization, academic_year=options["academic_year"])
        counts = dup_plan.summary(plan)
        batch = ""
        if options["apply"]:
            try:
                result = dup_apply.execute(plan, actor=actor, reason=options["reason"])
            except RosterError as error:
                raise CommandError(f"dupacct_{error.code}") from None
            batch = result["batch"]
            written = {
                "pairs": len(result["pairs"]),
                "frozen": sum(1 for item in result["pairs"] if item["blocked"]),
                "roles_moved": sum(len(item["roles"]) for item in result["pairs"]),
                "heads_moved": sum(len(item["heads"]) for item in result["pairs"]),
                "journals_moved": sum(len(item["handovers"]) for item in result["pairs"]),
                "memberships_off": sum(len(item["deactivated"]) for item in result["pairs"]),
                "failed": len(result["failed"]),
            }
            self.stdout.write(f"YAZILDI: {_counts(written)}")
            self.stdout.write(f"Paket: {batch}")
        else:
            self.stdout.write(f"DRY-RUN (heç nə yazılmadı): {_counts(counts)}")
        self._write_reports(plan, options, batch)

    def _write_reports(self, plan, options, batch):
        suffix = " — YAZILDI" if batch else " — dry-run"
        markdown = dup_report.render_markdown(plan, batch=batch, title_suffix=suffix)
        if options["markdown"]:
            write_private(options["markdown"], markdown)
            self.stdout.write("Hesabat yazıldı (0600).")
        if options["report"]:
            from core.export_safety import safe_csv_writer

            folder = pathlib.Path(options["report"]).expanduser()
            folder.mkdir(parents=True, exist_ok=True, mode=0o700)
            rows = dup_report.csv_rows(plan)
            buffer = io.StringIO()
            safe_csv_writer(buffer).writerows(rows)
            write_private(folder / CSV_NAME, buffer.getvalue())
            write_private(folder / MD_NAME, markdown)
            self.stdout.write(f"Hesabat: {CSV_NAME} ({len(rows) - 1} sətir)")
