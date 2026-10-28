"""``build_practical_flag_plan`` — «Praktiki məşğələ» bayrağının planını LOKAL qurur (sahib 2026-10-28; heç nə yazmır).

Mənbə: köhnə sistemin delta paketi (``--bundle``) VƏ YA birbaşa MariaDB (``--legacy-source myedu_new``,
``ems-legacy-delta-src`` 127.0.0.1:50330, parol ``LEGACY_DELTA_MARIADB_PASSWORD``); hədəf — ``DATABASE_URL`` (prod
nüsxəsi). Çıxış (0600): ``practical-offerings/1`` — YALNIZ açılış id-ləri (ad / FİN yoxdur) → registrar
``set_practical_offerings``. Qayda: :mod:`apps.legacy_import.services.practical_flag_plan`. Stdout-a YALNIZ saylar
(``practical_plan: açar=say …``).

    DATABASE_URL=postgres://…/ems_prod_copy python manage.py build_practical_flag_plan --org qku \\
        --legacy-source myedu_new --full-semester 14 --out ~/EMSArena-backups/practical-flag-20261028/plan.json
"""

from __future__ import annotations

import datetime
import json
import os

from django.apps import apps as django_apps
from django.core.management.base import CommandError
from django.db import transaction

from apps.legacy_import.services.practical_flag_plan import practical_plan
from apps.legacy_import.services.twin_repair_plans import PlanBuilder
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

from .build_twin_repair_plans import Command as TwinPlansCommand

PREFIX = "practical_plan:"


class Command(TwinPlansCommand):
    help = "«Praktiki məşğələ» bayrağının planı (köhnə sistemin kod 3 jurnalları → açılış id-ləri) — lokal."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--bundle", default="", help="legacy_delta_extract paketi (.json.gz)")
        parser.add_argument("--legacy-source", default="", help="MariaDB sxemi (məs. myedu_new) — paket əvəzinə")
        parser.add_argument("--host", default="127.0.0.1")
        parser.add_argument("--port", type=int, default=50330)
        parser.add_argument("--user", default="root")
        parser.add_argument("--full-semester", type=int, action="append", default=[], help="Tam semestr (məs. 14)")
        parser.add_argument("--out", required=True, help="Plan faylı (0600; qovluq 0700)")

    def handle(self, *args, **options):
        bundle = self._bundle(options)
        Organization = django_apps.get_model("organizations", "Organization")
        path = os.path.expanduser(options["out"])
        os.makedirs(os.path.dirname(path) or ".", mode=0o700, exist_ok=True)
        with rls_worker_atomic(), bypass_rls():
            organization = Organization.objects.filter(slug=str(options["org"]).strip()).first()
            if organization is None:
                raise CommandError("practical_plan_organization_unknown")
            with transaction.atomic():
                builder = PlanBuilder(organization=organization, bundle=bundle, until=datetime.date.today())
                plan = practical_plan(builder)
                transaction.set_rollback(True)  # qurucu yazmır; hər ehtimala qarşı
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(plan, handle, ensure_ascii=False, indent=1, sort_keys=True)
        os.chmod(path, 0o600)
        keys = ("journals_mapped", "practical_journals", "practical_journals_inactive", "practical_offerings")
        keys += ("offerings_skipped_shared_with_seminar_journal",)
        self.stdout.write(PREFIX + " " + " ".join(f"{key}={builder.counts.get(key, 0)}" for key in keys))
