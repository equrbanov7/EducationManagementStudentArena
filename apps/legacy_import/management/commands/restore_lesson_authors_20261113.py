"""``restore_lesson_authors_20261113`` — keçilmiş dərsin müəllimi bərpası (sahib 2026-11-13; defolt dry-run).

Qaydalar: :mod:`apps.legacy_import.services.lesson_authors_2026_11_13`. Sübut faylı repodadır
(``apps/legacy_import/lesson_authors_2026_11_13.json`` — ad / FİN yoxdur; köhnə sistemin MariaDB nüsxəsindən
lokal çıxarılıb). ``--undo`` yalnız bu əmrin audit izinə görə geri qaytarır. Stdout-a YALNIZ saylar
(``twin_merge: açar=say …``); prod-data-ops həmin sətirləri süzür.
"""

from __future__ import annotations

import re
from collections import Counter

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.rls import apply_rls_request_context, bypass_rls
from core.rls_pooling import rls_worker_atomic

from ...services.lesson_authors_2026_11_13 import run, undo

PREFIX = "twin_merge:"


def failure_code(exc: Exception) -> str:
    slug = re.sub(r"[^a-z0-9_]+", "_", f"{type(exc).__name__}_{exc}".lower()).strip("_")
    return f"lesson_authors_failed_{slug}"[:120]


class Command(BaseCommand):
    help = "Sahib 2026-11-13: boş Lesson.instructor köhnə sistemin jurnal müəllimi / jurnal sahibi ilə; defolt dry-run."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--file", default="", help="Sübut faylı (defolt: repodakı lesson_authors_2026_11_13.json)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")
        parser.add_argument("--undo", action="store_true", help="Bu əmrin yazdıqlarını audit izinə görə geri qaytar")

    def handle(self, *args, **options):
        try:
            self._handle(options)
        except CommandError:
            raise
        except Exception as exc:  # noqa: BLE001 — prod-data-ops yalnız CommandError kodunu göstərir
            raise CommandError(failure_code(exc)) from None

    def _handle(self, options):
        step = undo if options["undo"] else run
        counts = Counter()
        with rls_worker_atomic(), bypass_rls():
            actor = (
                get_user_model().objects.filter(username=options["actor"], is_active=True, is_superuser=True).first()
            )
            if actor is None:
                raise CommandError("actor_must_be_active_superuser")
            organization = (
                django_apps.get_model("organizations", "Organization")
                .objects.filter(slug=str(options["org"]).strip())
                .first()
            )
            if organization is None:
                raise CommandError("lesson_authors_organization_unknown")
            apply_rls_request_context(user_id=actor.pk, org_id=organization.pk)
            with transaction.atomic():
                step(
                    organization=organization,
                    actor=actor,
                    counts=counts,
                    apply=options["apply"],
                    path=options["file"] or None,
                )
                if not options["apply"]:
                    transaction.set_rollback(True)
        self.stdout.write(f"{PREFIX} mode={'apply' if options['apply'] else 'dry_run'}")
        self.stdout.write(PREFIX + " " + " ".join(f"{key}={value}" for key, value in sorted(counts.items())))
