"""``import_timetable_docx`` — məktəbin Word «əsas dərs cədvəli»ni canlı ``ScheduleSlot``-lara yükləyir.

Sahib 2026-10-12: «cədvəli oxu; orada dərsi olan hər kəsi sistemdə seç və yüklə — hamının cədvəlinə
düşsün; problemsiz olmalıdır». Oxuma/tutuşdurma/toqquşma qaydaları: ``apps.registrar.schedule_docx_*``.

* DEFOLT DRY-RUN — bazaya heç nə yazılmır; ``--apply`` ilə yazılır (bir tranzaksiya, semestr kilidi).
* Heç nə YARADILMIR: açılış, qrup, fənn, istifadəçi. Tapılmayan / çox mənalı / toqquşan hüceyrə
  hesabata düşür və yazılmır.
* İdempotent: təkrar işə salma 0 yaradır (mövcud slot «exists»).
* ``--replace-group-slots`` (defolt SÖNÜLÜ): fayldakı qrupların həmin semestrdəki digər slotları
  yumşaq silinir (bərpa olunur) — fayl o qruplar üçün TAM cədvəldirsə.
* Stdout-a YALNIZ saylar düşür (şəxs adları yox); tam sətir-sətir hesabat ``--report`` qovluğuna CSV
  kimi yazılır (``core.export_safety.safe_csv_writer``) — şəxsi məlumatdır, lokal/şifrəli saxlayın.

İstifadə::

    manage.py import_timetable_docx --file cədvəl.docx --org qku --period "Payız 2026/2027" --report /tmp/tt
    manage.py import_timetable_docx --file cədvəl.docx --org qku --period "Payız 2026/2027" --report /tmp/tt \\
        --apply --actor <istifadəçi> --i-know-this-is-production
"""

from __future__ import annotations

import pathlib
import re

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone

from apps.registrar.schedule_docx_import import ACTIONS, REPORT_HEADER, run_import
from apps.registrar.schedule_docx_parse import parse_docx
from core.export_safety import safe_csv_writer
from core.rls import apply_rls_request_context, bypass_rls
from core.rls_pooling import rls_worker_atomic

REHEARSAL_GUC = "emsarena.rehearsal_target"
REHEARSAL_VALUE = "disposable"


def _disposable_database() -> bool:
    if connection.vendor != "postgresql":
        return True
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_setting(%s, true)", [REHEARSAL_GUC])
            row = cursor.fetchone()
    except Exception:  # noqa: BLE001 — marker oxuna bilmirsə baza «real» sayılır (fail-closed)
        return False
    return bool(row) and str(row[0] or "").strip() == REHEARSAL_VALUE


def resolve_period(organization, raw: str):
    """«Payız 2026/2027» (ad + tədris ili) və ya dövrün UUID-i → ``AcademicPeriod``."""
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
    help = "Word dərs cədvəlini (.docx) canlı cədvəl slotlarına yükləyir: dry-run (defolt) və ya --apply."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Dərs cədvəli .docx faylı")
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--period", required=True, help="Semestr: «Payız 2026/2027» və ya dövrün UUID-i")
        parser.add_argument("--report", default="", help="Hesabat qovluğu (timetable_import.csv yazılır)")
        parser.add_argument(
            "--replace-group-slots",
            action="store_true",
            help="Fayldakı qrupların bu semestrdəki DİGƏR slotlarını yumşaq sil (defolt: sönülü)",
        )
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")
        parser.add_argument("--actor", default="", help="Aktorun istifadəçi adı (defolt: təşkilatın sahibi)")
        parser.add_argument("--i-know-this-is-production", action="store_true", help="Markersiz bazada icazə")

    def handle(self, *args, **options):
        path = pathlib.Path(options["file"]).expanduser()
        if not path.is_file():
            raise CommandError("timetable_file_not_found")
        try:
            parsed = parse_docx(path)
        except Exception as exc:  # noqa: BLE001 — pozuq/qeyri-docx fayl
            raise CommandError(f"timetable_docx_unreadable: {type(exc).__name__}") from None
        Organization = django_apps.get_model("organizations", "Organization")
        with rls_worker_atomic(), bypass_rls():
            organization = Organization.objects.filter(slug=str(options["org"]).strip()).first()
            if organization is None:
                raise CommandError("timetable_organization_unknown")
            period = resolve_period(organization, options["period"])
            if period is None:
                raise CommandError("timetable_period_unknown: «Ad YYYY/YYYY» (məs. «Payız 2026/2027») və ya UUID")
            if options["apply"]:
                if not (_disposable_database() or options["i_know_this_is_production"]):
                    raise CommandError(
                        f"timetable_target_not_disposable: bazada {REHEARSAL_GUC}='{REHEARSAL_VALUE}' markeri "
                        "yoxdur — real bazada --i-know-this-is-production verin."
                    )
                if period.end_date and period.end_date < timezone.localdate():
                    raise CommandError("timetable_period_closed")
            actor = self._actor(organization, options["actor"])
            if actor is not None:
                apply_rls_request_context(user_id=actor.pk, org_id=organization.pk)
            plan = run_import(
                organization=organization,
                period=period,
                parsed=parsed,
                actor=actor,
                apply=options["apply"],
                replace_group_slots=options["replace_group_slots"],
                source=f"timetable-docx:{path.name}"[:120],
            )
        self._summary(plan, parsed, options)
        if options["report"]:
            self._write_report(plan, options["report"])

    def _actor(self, organization, username):
        username = str(username or "").strip()
        if not username:
            return getattr(organization, "owner", None)
        user_model = django_apps.get_model("auth", "User")
        actor = user_model._default_manager.filter(username=username).first()
        if actor is None:
            raise CommandError("timetable_actor_unknown")
        return actor

    def _summary(self, plan, parsed, options):
        mode = "YAZILDI" if options["apply"] else "DRY-RUN"
        counts = plan.counts
        self.stdout.write(
            f"{mode}: cədvəl={parsed.tables} qrup_başlığı={len(set(parsed.groups))} hüceyrə={len(parsed.entries)}"
        )
        self.stdout.write(f"  oxunmayan sətir: {len(plan.skipped)}")
        for action in ACTIONS:
            self.stdout.write(f"  {action:<10} {counts.get(action, 0)}")
        self.stdout.write(
            f"  tapılmayan qrup başlığı: {sum(1 for row in plan.rows if 'group_not_found' in row.reasons)}"
        )
        self.stdout.write(f"  tələbəsi görünməyən açılış: {plan.invisible_offerings}")
        if options["replace_group_slots"]:
            self.stdout.write(f"  yumşaq silinən köhnə slot: {len(plan.replaced_ids)}")
        for action in ("create", "unmatched", "ambiguous", "clash", "skipped", "exists"):
            reasons = plan.reason_counts(action)
            if reasons:
                parts = ", ".join(f"{reason}={count}" for reason, count in reasons.most_common(12))
                self.stdout.write(f"  səbəb[{action}]: {parts}")
        if options["apply"]:
            self.stdout.write(f"  yaradıldı: {len(plan.created_ids)}")

    def _write_report(self, plan, directory):
        folder = pathlib.Path(directory).expanduser()
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / "timetable_import.csv"
        with target.open("w", encoding="utf-8", newline="") as handle:
            writer = safe_csv_writer(handle)
            writer.writerow(REPORT_HEADER)
            for row in plan.rows:
                writer.writerow(row.csv_row())
            for item in plan.skipped:
                writer.writerow([item.get("table"), item.get("row")] + [""] * 12 + ["skipped", item.get("reason")])
        self.stdout.write(f"Hesabat: {target.name} ({len(plan.rows) + len(plan.skipped)} sətir)")
