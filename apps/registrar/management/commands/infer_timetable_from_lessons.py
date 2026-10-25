"""``infer_timetable_from_lessons`` — müəllimlərin faktiki keçdiyi dərslərdən canlı dərs cədvəli slotları.

Sahib 2026-10-24: «hər müəllimin keçdiyi dərs saatlarını nəzərə alaraq dərs cədvəlini rəsmiləşdir — dəqiq
bilək ki, bu müəllim bu saatda dərs deyir; üst/alt həftə, mühazirə, seminar; patok bölünməsin; otaq
çətindirsə boş qalsın». Qaydalar: :mod:`apps.registrar.timetable_inference` (analiz) və
:mod:`apps.registrar.timetable_inference_plan` (toqquşma / yazı).

* DEFOLT DRY-RUN — bazaya heç nə yazılmır; ``--apply`` ilə bir tranzaksiyada, semestr kilidi altında.
* Heç nə SİLİNMİR və DƏYİŞDİRİLMİR: mövcud slot ``exists``, toqquşan vahid ``conflict`` — yazılmır.
* İdempotent: təkrar işə salma 0 yaradır.
* Stdout-a YALNIZ saylar düşür (``timetable_infer: açar=say …`` sətirləri; şəxs adı yoxdur). Sətir-sətir
  hesabat ``--report`` faylına CSV (``core.export_safety.safe_csv_writer``) — müəllim adları var, lokal /
  şifrəli saxlayın.

İstifadə::

    manage.py infer_timetable_from_lessons --org qku --period "Payız 2026/2027" [--teacher ad.soyad] \\
        [--date-from 2026-09-15] [--date-to 2026-10-24] [--min-occurrences 2] [--parity-tolerance 0.25] \\
        [--snap-minutes 25] [--no-hours-cap] [--no-fill-rooms] [--recent-days 14] [--report /tmp/tt.csv] \\
        [--apply --actor <istifadəçi> --i-know-this-is-production]
"""

from __future__ import annotations

import datetime as dt
import pathlib

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.registrar.management.commands.import_timetable_docx import _disposable_database, resolve_period
from apps.registrar.timetable_inference import (
    DEFAULT_MIN_OCCURRENCES,
    DEFAULT_PARITY_TOLERANCE,
    DEFAULT_RECENT_DAYS,
    DEFAULT_SNAP_MINUTES,
    FACT_KEYS,
    Rules,
)
from apps.registrar.timetable_inference_plan import ACTIONS, REPORT_HEADER, run_inference, usernames_for
from core.export_safety import safe_csv_writer
from core.rls import apply_rls_request_context, bypass_rls
from core.rls_pooling import rls_worker_atomic

PREFIX = "timetable_infer:"
MAX_REASONS = 16


def _date(raw, name: str):
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return dt.date.fromisoformat(text)
    except ValueError:
        raise CommandError(f"timetable_infer_bad_date: --{name} YYYY-MM-DD olmalıdır") from None


def _line(pairs) -> str:
    return PREFIX + " " + " ".join(f"{key}={value}" for key, value in pairs)


class Command(BaseCommand):
    help = "Jurnalın keçirilmiş dərslərindən həftəlik cədvəl slotları çıxarır: dry-run (defolt) və ya --apply."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--period", required=True, help="Semestr: «Payız 2026/2027» və ya dövrün UUID-i")
        parser.add_argument("--teacher", default="", help="Yalnız bu müəllim (istifadəçi adı); boş = hamısı")
        parser.add_argument("--date-from", default="", help="Başlanğıc (YYYY-MM-DD; defolt: semestrin əvvəli)")
        parser.add_argument("--date-to", default="", help="Son (YYYY-MM-DD; defolt: bu gün / semestrin sonu)")
        parser.add_argument(
            "--min-occurrences",
            type=int,
            default=DEFAULT_MIN_OCCURRENCES,
            help="Slot üçün minimum fərqli tarix (defolt 2 — birdəfəlik/kompensasiya dərsi slot olmasın)",
        )
        parser.add_argument(
            "--parity-tolerance",
            type=float,
            default=DEFAULT_PARITY_TOLERANCE,
            help="Çoxluq qaydası: azlıq paritetin payı bundan çox deyilsə üst/alt (defolt 0.25 — 3 üst + 1 alt = üst)",
        )
        parser.add_argument(
            "--snap-minutes",
            type=int,
            default=DEFAULT_SNAP_MINUTES,
            help="Standartdan kənar başlamanı bu qədər dəqiqə daxilində ən yaxın zəngə çək (0 = çəkmə; defolt 25)",
        )
        parser.add_argument(
            "--no-hours-cap",
            action="store_true",
            help="Plan / yük saatına görə həftəlik slot həddini SÖNDÜR (defolt: artıq vahid kompensasiya sayılır)",
        )
        parser.add_argument(
            "--no-fill-rooms",
            action="store_true",
            help="Bu əmrin əvvəl yazdığı otaqsız slotlara otaq YAZMA (defolt: yazılır; rəsmi slotlara toxunulmur)",
        )
        parser.add_argument(
            "--recent-days",
            type=int,
            default=DEFAULT_RECENT_DAYS,
            help="Son N gündə başlamış açılışın tək dərsi də slot olur (0 = söndür; defolt 14)",
        )
        parser.add_argument("--report", default="", help="Sətir-sətir CSV hesabat faylının yolu")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")
        parser.add_argument("--actor", default="", help="Aktorun istifadəçi adı (defolt: təşkilatın sahibi)")
        parser.add_argument("--i-know-this-is-production", action="store_true", help="Markersiz bazada icazə")

    def handle(self, *args, **options):
        if not 1 <= int(options["min_occurrences"]) <= 52:
            raise CommandError("timetable_infer_bad_min_occurrences: 1..52")
        if not 0 <= float(options["parity_tolerance"]) < 0.5:
            raise CommandError("timetable_infer_bad_parity_tolerance: 0 <= x < 0.5")
        if not 0 <= int(options["snap_minutes"]) <= 45:
            raise CommandError("timetable_infer_bad_snap_minutes: 0..45")
        if not 0 <= int(options["recent_days"]) <= 60:
            raise CommandError("timetable_infer_bad_recent_days: 0..60")
        rules = Rules(
            min_occurrences=int(options["min_occurrences"]),
            parity_tolerance=float(options["parity_tolerance"]),
            snap_minutes=int(options["snap_minutes"]),
            hours_cap=not options["no_hours_cap"],
            fill_rooms=not options["no_fill_rooms"],
            recent_days=int(options["recent_days"]),
        )
        Organization = django_apps.get_model("organizations", "Organization")
        user_model = django_apps.get_model("auth", "User")
        with rls_worker_atomic(), bypass_rls():
            organization = Organization.objects.filter(slug=str(options["org"]).strip()).first()
            if organization is None:
                raise CommandError("timetable_infer_organization_unknown")
            period = resolve_period(organization, options["period"])
            if period is None:
                raise CommandError("timetable_infer_period_unknown: «Ad YYYY/YYYY» (məs. «Payız 2026/2027») və ya UUID")
            teacher = None
            if str(options["teacher"]).strip():
                teacher = user_model._default_manager.filter(username=str(options["teacher"]).strip()).first()
                if teacher is None:
                    raise CommandError("timetable_infer_teacher_unknown")
            date_from, date_to = self._range(period, options)
            if options["apply"]:
                if not (_disposable_database() or options["i_know_this_is_production"]):
                    raise CommandError(
                        "timetable_infer_target_not_disposable: real bazada --apply üçün "
                        "--i-know-this-is-production verin."
                    )
                if period.end_date and period.end_date < timezone.localdate():
                    raise CommandError("timetable_infer_period_closed")
            actor = self._actor(organization, options["actor"], user_model)
            if actor is not None:
                apply_rls_request_context(user_id=actor.pk, org_id=organization.pk)
            plan = run_inference(
                organization=organization,
                period=period,
                date_from=date_from,
                date_to=date_to,
                teacher=teacher,
                rules=rules,
                actor=actor,
                apply=options["apply"],
            )
            usernames = usernames_for(plan) if options["report"] else {}
        self._summary(plan, options, date_from, date_to)
        if options["report"]:
            self._write_report(plan, options["report"], usernames)

    def _range(self, period, options):
        date_from = _date(options["date_from"], "date-from") or period.start_date
        date_to = _date(options["date_to"], "date-to") or timezone.localdate()
        date_from = max(date_from, period.start_date) if period.start_date else date_from
        date_to = min(date_to, timezone.localdate())
        if period.end_date:
            date_to = min(date_to, period.end_date)
        if date_from > date_to:
            raise CommandError("timetable_infer_bad_range: --date-from --date-to-dan sonra ola bilməz")
        return date_from, date_to

    def _actor(self, organization, username, user_model):
        username = str(username or "").strip()
        if not username:
            return getattr(organization, "owner", None)
        actor = user_model._default_manager.filter(username=username, is_active=True).first()
        if actor is None:
            raise CommandError("timetable_infer_actor_unknown")
        return actor

    def _summary(self, plan, options, date_from, date_to):
        mode = "apply" if options["apply"] else "dry_run"
        write = self.stdout.write
        write(_line([("mode", mode), ("from", date_from.isoformat()), ("to", date_to.isoformat())]))
        write(_line((key, plan.facts.get(key, 0)) for key in FACT_KEYS))
        write(_line(sorted(plan.unit_counts().items(), key=lambda item: item[0])))
        write(_line((action, plan.counts.get(action, 0)) for action in ACTIONS))
        write(_line(sorted(plan.created_counts().items())))
        reasons = plan.reason_counts().most_common(MAX_REASONS)
        if reasons:
            write(_line((f"reason_{reason}", count) for reason, count in reasons))
        if options["apply"]:
            write(_line([("written", len(plan.created_ids)), ("rooms_filled", len(plan.filled_ids))]))

    def _write_report(self, plan, path_text, usernames):
        target = pathlib.Path(path_text).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8", newline="") as handle:
            writer = safe_csv_writer(handle)
            writer.writerow(REPORT_HEADER)
            for row in plan.rows:
                writer.writerow(row.csv_row(usernames))
        self.stdout.write(_line([("report_rows", len(plan.rows))]))
