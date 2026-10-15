"""``backfill_teacher_lessons`` — müəllimin keçmiş dərslərini cədvəldən yaradır və hamıya «iə» yazır.

Sahib 2026-10-15: «15.09-dan bu günə qədər bütün fənlərim üçün cədvəlimə görə dərsləri yarat, bütün
tələbələrə i/e qoy — sonra özüm dəyişəcəyəm». Qaydalar: :mod:`apps.registrar.lesson_backfill`.

* DEFOLT DRY-RUN — hər şey bir tranzaksiyada hesablanır və GERİ QAYTARILIR; ``--apply`` ilə yazılır.
* Slotlar: müəllimin canlı cədvəli, və ya ``--slots-file`` (JSON: ``[{group, subject_contains, weekday,
  start, end, kind, week_type, room}]``) — ``--replace-teacher-slots`` ilə müəllimin cədvəli spesifikasiya
  ilə EYNİLƏŞDİRİLİR (digər slotları yumşaq silinir).
* İdempotent: mövcud dərs (eyni saat, yoxsa eyni növ) təkrar yaradılmır, mövcud işarəyə toxunulmur.
* Stdout-a YALNIZ saylar + açılış (fənn · qrup) üzrə saylar düşür — tələbə adı yoxdur. Sətir-sətir hesabat
  ``--report`` qovluğuna CSV (``core.export_safety.safe_csv_writer``).
* DİQQƏT: yeni işarə yaranışdan sonra ``journal.mark_edit_hours`` (defolt 2 saat) ərzində dəyişdirilə bilər —
  sonra yalnız rəsmi düzəliş axını ilə (DB trigger də qoruyur).

İstifadə::

    manage.py backfill_teacher_lessons --org qku --teacher ad.soyad --period "Payız 2026/2027" \\
        --from 2026-09-15 --to 2026-10-15 --mark present [--slots-file spec.json [--replace-teacher-slots]] \\
        --actor <superuser> --report /tmp/backfill [--apply --i-know-this-is-production]
"""

from __future__ import annotations

import datetime as dt
import pathlib

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand, CommandError

from apps.registrar.lesson_backfill import (
    LESSON_ACTIONS,
    LESSON_REPORT_HEADER,
    SLOT_ACTIONS,
    SLOT_REPORT_HEADER,
    SpecError,
    load_slot_spec,
    run_backfill,
)
from apps.registrar.management.commands.import_timetable_docx import _disposable_database, resolve_period
from core.export_safety import safe_csv_writer
from core.rls import apply_rls_request_context, bypass_rls
from core.rls_pooling import rls_worker_atomic

MAX_SPEC_BYTES = 256 * 1024


def _date(raw: str, name: str) -> dt.date:
    try:
        return dt.date.fromisoformat(str(raw).strip())
    except (TypeError, ValueError):
        raise CommandError(f"backfill_bad_date: --{name} YYYY-MM-DD olmalıdır") from None


class Command(BaseCommand):
    help = "Müəllimin keçmiş dərslərini cədvəl slotlarından yaradır və aktiv tələbələrə «iə» yazır (dry-run defolt)."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--teacher", required=True, help="Müəllimin istifadəçi adı (ad.soyad)")
        parser.add_argument("--period", required=True, help="Semestr: «Payız 2026/2027» və ya dövrün UUID-i")
        parser.add_argument("--from", dest="date_from", required=True, help="Başlanğıc tarix (YYYY-MM-DD)")
        parser.add_argument("--to", dest="date_to", required=True, help="Son tarix (YYYY-MM-DD, bu gündən sonra yox)")
        parser.add_argument("--mark", choices=["present"], default="present", help="Yazılacaq işarə (yalnız iə)")
        parser.add_argument("--slots-file", default="", help="Slot spesifikasiyası (JSON); verilməsə canlı cədvəl")
        parser.add_argument(
            "--replace-teacher-slots",
            action="store_true",
            help="(--slots-file ilə) müəllimin bu semestrdəki DİGƏR slotlarını yumşaq sil",
        )
        parser.add_argument("--actor", required=True, help="Aktor — aktiv superuser-in istifadəçi adı")
        parser.add_argument("--report", default="", help="Hesabat qovluğu (lesson_backfill_*.csv)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")
        parser.add_argument("--i-know-this-is-production", action="store_true", help="Markersiz bazada icazə")

    def handle(self, *args, **options):
        date_from, date_to = _date(options["date_from"], "from"), _date(options["date_to"], "to")
        if date_from > date_to:
            raise CommandError("backfill_bad_range: --from --to-dan sonra ola bilməz")
        if options["replace_teacher_slots"] and not options["slots_file"]:
            raise CommandError("backfill_replace_needs_spec: --replace-teacher-slots yalnız --slots-file ilə")
        specs = self._specs(options["slots_file"])
        user_model = django_apps.get_model("auth", "User")
        Organization = django_apps.get_model("organizations", "Organization")
        with rls_worker_atomic(), bypass_rls():
            organization = Organization.objects.filter(slug=str(options["org"]).strip()).first()
            if organization is None:
                raise CommandError("backfill_organization_unknown")
            period = resolve_period(organization, options["period"])
            if period is None:
                raise CommandError("backfill_period_unknown: «Ad YYYY/YYYY» (məs. «Payız 2026/2027») və ya UUID")
            teacher = user_model._default_manager.filter(username=str(options["teacher"]).strip()).first()
            if teacher is None:
                raise CommandError("backfill_teacher_unknown")
            actor = user_model._default_manager.filter(
                username=str(options["actor"]).strip(), is_superuser=True, is_active=True
            ).first()
            if actor is None:
                raise CommandError("backfill_actor_not_superuser")
            if options["apply"] and not (_disposable_database() or options["i_know_this_is_production"]):
                raise CommandError(
                    "backfill_target_not_disposable: real bazada --apply üçün --i-know-this-is-production verin."
                )
            apply_rls_request_context(user_id=actor.pk, org_id=organization.pk)
            result = run_backfill(
                organization=organization,
                period=period,
                teacher=teacher,
                date_from=date_from,
                date_to=date_to,
                actor=actor,
                specs=specs,
                replace_slots=options["replace_teacher_slots"],
                apply=options["apply"],
            )
        self._summary(result, options)
        if options["report"]:
            self._write_report(result, options["report"])

    def _specs(self, path_text):
        if not path_text:
            return None
        path = pathlib.Path(path_text).expanduser()
        if not path.is_file():
            raise CommandError("backfill_slots_file_not_found")
        if path.stat().st_size > MAX_SPEC_BYTES:
            raise CommandError("backfill_slots_file_too_large")
        try:
            return load_slot_spec(path.read_text(encoding="utf-8"))
        except (SpecError, UnicodeDecodeError) as exc:
            raise CommandError(f"backfill_slots_file_invalid: {exc}") from None

    def _summary(self, result, options):
        mode = "YAZILDI" if options["apply"] else "DRY-RUN"
        source = "spec" if options["slots_file"] else "live"
        self.stdout.write(f"{mode}: aralıq={result.date_from}..{result.date_to} slot_mənbəyi={source}")
        slot_counts, lesson_counts = result.slot_counts, result.lesson_counts
        self.stdout.write("  slot: " + " · ".join(f"{a}={slot_counts.get(a, 0)}" for a in SLOT_ACTIONS))
        self.stdout.write("  dərs: " + " · ".join(f"{a}={lesson_counts.get(a, 0)}" for a in LESSON_ACTIONS))
        reasons = result.skip_reasons
        if reasons:
            self.stdout.write("  səbəb[skipped]: " + ", ".join(f"{r}={n}" for r, n in reasons.most_common(12)))
        self.stdout.write(f"  işarə iə: yazıldı={result.marks_written} yazılmadı={result.marks_rejected}")
        for label, counter in result.per_offering():
            parts = " · ".join(f"{a}={counter.get(a, 0)}" for a in LESSON_ACTIONS)
            self.stdout.write(f"  açılış [{label[:90]}]: {parts} · iə={counter.get('marks', 0)}")

    def _write_report(self, result, directory):
        folder = pathlib.Path(directory).expanduser()
        folder.mkdir(parents=True, exist_ok=True)
        for name, header, rows in (
            ("lesson_backfill_lessons.csv", LESSON_REPORT_HEADER, result.lesson_rows),
            ("lesson_backfill_slots.csv", SLOT_REPORT_HEADER, result.slot_rows),
        ):
            with (folder / name).open("w", encoding="utf-8", newline="") as handle:
                writer = safe_csv_writer(handle)
                writer.writerow(header)
                for row in rows:
                    writer.writerow(row.csv_row())
        self.stdout.write(f"Hesabat: {len(result.lesson_rows)} dərs + {len(result.slot_rows)} slot sətri")
