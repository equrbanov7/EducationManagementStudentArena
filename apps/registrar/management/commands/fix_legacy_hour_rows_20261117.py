"""``fix_legacy_hour_rows_20261117`` — köhnə sistem jurnallarında ikiqat saat: saat-saat yazılmış dərslər 1 saata
endirilir, boş artıq sətirlər silinir, qayıb saatı yenidən hesablanır (sahib 2026-11-17, MR-000482; defolt dry-run).

Qaydalar: :mod:`apps.registrar.legacy_hour_rows_rule` (sətir tanınması) və
:mod:`apps.registrar.legacy_hour_rows_2026_11_17` (əhatə, yazı, undo). ``--apply`` yazır və paket id-sini
(``batch=lghours-…``) çap edir; ``--undo --batch lghours-…`` həmin paketi geri qaytarır. Stdout-a YALNIZ saylar
(``legacy_hours: açar=dəyər …``) — ümumi sətir + hər semestr üçün bir sətir (``period=YYYY-MM-DD``); prod-data-ops
həmin sətirləri süzür.
"""

from __future__ import annotations

import re
from collections import Counter

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.rls import apply_rls_request_context, bypass_rls
from core.rls_pooling import rls_worker_atomic

from ...legacy_hour_rows_2026_11_17 import new_batch_id, run, undo
from .relocate_twin_enrollment import superadmin

PREFIX = "legacy_hours:"
_BATCH = re.compile(r"^lghours-[0-9]{8}-[0-9]{6}-[0-9a-f]{4}$")
_COUNT_KEYS = (
    "no_current_period",
    "offerings",
    "offerings_hour_mode",
    "offerings_window_mode",
    "offerings_frozen",
    "offerings_no_plan",
    "inactive_offerings_skipped",
    "corrected_lessons_skipped",
    "lessons_one_hour",
    "lessons_empty_deleted",
    "empty_kept_inactive_instructor",
    "tiny_gap_rows",
    "plan_fit_before",
    "plan_fit_after",
    "under_plan_before",
    "under_plan_after",
    "enrollments",
    "enrollments_absence_changed",
    "enrollments_barred_before",
    "enrollments_barred_after",
    "enrollments_unbarred",
    "enrollments_newly_barred",
    "unbarred_with_final_grade",
    "students_unbarred",
)
_PERIOD_KEYS = (
    "offerings",
    "offerings_hour_mode",
    "offerings_window_mode",
    "offerings_frozen",
    "lessons_one_hour",
    "lessons_empty_deleted",
    "plan_fit_before",
    "plan_fit_after",
    "enrollments_unbarred",
)
_UNDO_KEYS = (
    "undo_entries",
    "undo_hours_restored",
    "undo_hours_changed",
    "undo_lessons_recreated",
    "undo_lesson_exists",
    "undo_instructor_is_journal_teacher",
    "undo_instructor_dropped",
    "undo_offering_missing",
)


def failure_code(exc: Exception) -> str:
    slug = re.sub(r"[^a-z0-9_]+", "_", f"{type(exc).__name__}_{exc}".lower()).strip("_")
    return f"legacy_hours_failed_{slug}"[:120]


class Command(BaseCommand):
    help = "Sahib 2026-11-17: köhnə sistem jurnallarında ikiqat saat düzəlişi (defolt dry-run; --undo --batch)."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")
        parser.add_argument("--undo", action="store_true", help="--batch paketini audit izinə görə geri qaytar")
        parser.add_argument("--batch", default="", help="Geri qaytarılacaq paket: lghours-YYYYMMDD-HHMMSS-xxxx")

    def handle(self, *args, **options):
        try:
            self._handle(options)
        except CommandError:
            raise
        except Exception as exc:  # noqa: BLE001 — prod-data-ops yalnız CommandError kodunu göstərir
            raise CommandError(failure_code(exc)) from None

    def _handle(self, options):
        batch = str(options["batch"] or "").strip()
        if options["undo"] and not _BATCH.match(batch):
            raise CommandError("legacy_hours_batch_invalid")
        if batch and not options["undo"]:
            raise CommandError("legacy_hours_batch_needs_undo")
        if not options["undo"]:
            batch = new_batch_id()
        actor = superadmin(options["actor"])
        Organization = django_apps.get_model("organizations", "Organization")
        mode = "apply" if options["apply"] else "dry_run"
        self.stdout.write(f"{PREFIX} mode={mode} step={'undo' if options['undo'] else 'fix'} batch={batch}")
        counts, period_counts = Counter(), {}
        with rls_worker_atomic(), bypass_rls():
            organization = Organization.objects.filter(slug=str(options["org"] or "").strip()).first()
            if organization is None:
                raise CommandError("legacy_hours_organization_unknown")
            apply_rls_request_context(user_id=actor.pk, org_id=organization.pk)
            with transaction.atomic():
                if options["undo"]:
                    undo(organization=organization, actor=actor, counts=counts, batch=batch)
                else:
                    run(organization=organization, actor=actor, counts=counts, batch=batch, period_counts=period_counts)
                if not options["apply"]:
                    transaction.set_rollback(True)
        keys = _UNDO_KEYS if options["undo"] else _COUNT_KEYS
        self.stdout.write(f"{PREFIX} org={organization.slug} " + " ".join(f"{key}={counts[key]}" for key in keys))
        for period in sorted(period_counts):
            values = period_counts[period]
            self.stdout.write(
                f"{PREFIX} period={period} " + " ".join(f"{key}={values.get(key, 0)}" for key in _PERIOD_KEYS)
            )
