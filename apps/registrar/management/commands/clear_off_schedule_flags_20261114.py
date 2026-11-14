"""``clear_off_schedule_flags_20261114`` — «cədvəldən kənar» işarəsi BÜTÜN dərslərdən təmizlənir (sahib 2026-11-14,
MR-356; defolt dry-run).

Qaydalar: :mod:`apps.registrar.off_schedule_disable_2026_11_14`. ``--org`` təşkilatın slug-ı və ya ``all`` (hər
təşkilat ayrıca tranzaksiyada, sayları ayrıca sətirdə). ``--apply`` yazır və paket id-sini (``batch=offsched-…``)
çap edir; ``--undo --batch offsched-…`` həmin paketi audit izinə görə geri qaytarır. Stdout-a YALNIZ saylar
(``off_schedule_flags: açar=dəyər …``); prod-data-ops həmin sətirləri süzür.
"""

from __future__ import annotations

import re
from collections import Counter

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.rls import apply_rls_request_context, bypass_rls
from core.rls_pooling import rls_worker_atomic

from ...off_schedule_disable_2026_11_14 import new_batch_id, run, undo
from .relocate_twin_enrollment import superadmin

PREFIX = "off_schedule_flags:"
_BATCH = re.compile(r"^offsched-[0-9]{8}-[0-9]{6}-[0-9a-f]{4}$")
_COUNT_KEYS = ("offerings", "flagged", "cleared", "race_skipped")
_UNDO_KEYS = ("undo_entries", "undo_restored", "undo_already", "undo_lessons_missing", "undo_offering_missing")


def failure_code(exc: Exception) -> str:
    slug = re.sub(r"[^a-z0-9_]+", "_", f"{type(exc).__name__}_{exc}".lower()).strip("_")
    return f"off_schedule_disable_failed_{slug}"[:120]


class Command(BaseCommand):
    help = "Sahib 2026-11-14: «cədvəldən kənar» işarəsini bütün dərslərdən təmizləyir (defolt dry-run; --undo)."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku) və ya «all»")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")
        parser.add_argument("--undo", action="store_true", help="--batch paketini audit izinə görə geri qaytar")
        parser.add_argument("--batch", default="", help="Geri qaytarılacaq paket: offsched-YYYYMMDD-HHMMSS-xxxx")

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
            raise CommandError("off_schedule_batch_invalid")
        if batch and not options["undo"]:
            raise CommandError("off_schedule_batch_needs_undo")
        if not options["undo"]:
            batch = new_batch_id()
        actor = superadmin(options["actor"])
        slug = str(options["org"] or "").strip()
        Organization = django_apps.get_model("organizations", "Organization")
        mode = "apply" if options["apply"] else "dry_run"
        self.stdout.write(f"{PREFIX} mode={mode} step={'undo' if options['undo'] else 'clear'} batch={batch}")
        with rls_worker_atomic(), bypass_rls():
            organizations = Organization.objects.order_by("slug")
            if slug != "all":
                organizations = organizations.filter(slug=slug)
            organizations = list(organizations)
            if not organizations:
                raise CommandError("off_schedule_organization_unknown")
            for organization in organizations:
                counts = Counter()
                apply_rls_request_context(user_id=actor.pk, org_id=organization.pk)
                with transaction.atomic():
                    step = undo if options["undo"] else run
                    step(organization=organization, actor=actor, counts=counts, batch=batch)
                    if not options["apply"]:
                        transaction.set_rollback(True)
                keys = _UNDO_KEYS if options["undo"] else _COUNT_KEYS
                self.stdout.write(
                    f"{PREFIX} org={organization.slug} " + " ".join(f"{key}={counts[key]}" for key in keys)
                )
