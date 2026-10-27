"""``build_twin_repair_plans`` — RİM 2026-10-27 düzəliş planlarını LOKAL qurur (heç nə yazmır).

Mənbə: köhnə sistemin delta paketi (``--bundle``, ``legacy_delta_extract`` çıxışı) VƏ YA birbaşa MariaDB
(``--legacy-source myedu_new``, ``ems-legacy-delta-src`` konteyneri 127.0.0.1:50330, parol
``LEGACY_DELTA_MARIADB_PASSWORD``); hədəf — ``DATABASE_URL`` (prod nüsxəsi). Çıxış qovluğunda (0600):

* ``relocate.json`` → ``relocate_twin_enrollment``; ``merge.json`` → ``merge_twin_offerings``;
  ``lessonkinds.json`` → ``fix_legacy_lesson_kinds``.

Fayllarda YALNIZ id-lər var (ad / FİN yoxdur). Stdout-a YALNIZ saylar (``twin_plans: açar=say …``). Qaydalar:
:mod:`apps.legacy_import.services.twin_repair_plans`.

    DATABASE_URL=postgres://…/ems_prod_copy python manage.py build_twin_repair_plans --org qku \\
        --legacy-source myedu_new --full-semester 14 --out-dir ~/EMSArena-backups/rim-fix-20261027
"""

from __future__ import annotations

import datetime
import json
import os

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.legacy_import.services.delta.bundle import BundleError, read_bundle
from apps.legacy_import.services.twin_repair_plans import PlanBuilder
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

PREFIX = "twin_plans:"
FILES = (("relocate.json", "relocate"), ("merge.json", "merge"), ("lessonkinds.json", "lesson_kinds"))


class Command(BaseCommand):
    help = "RİM 2026-10-27 düzəliş planları (əkiz jurnal, əkiz açılış, lab dərsləri) — lokal, yalnız id-lər."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--bundle", default="", help="legacy_delta_extract paketi (.json.gz)")
        parser.add_argument("--legacy-source", default="", help="MariaDB sxemi (məs. myedu_new) — paket əvəzinə")
        parser.add_argument("--host", default="127.0.0.1")
        parser.add_argument("--port", type=int, default=50330)
        parser.add_argument("--user", default="root")
        parser.add_argument("--full-semester", type=int, action="append", default=[], help="Tam semestr (məs. 14)")
        parser.add_argument("--until", default="2026-10-23", help="Bərpa olunan qayıbların son tarixi (YYYY-MM-DD)")
        parser.add_argument("--out-dir", required=True, help="Plan fayllarının qovluğu (0700)")

    def handle(self, *args, **options):
        try:
            until = datetime.date.fromisoformat(options["until"])
        except ValueError:
            raise CommandError("twin_plans_bad_until") from None
        bundle = self._bundle(options)
        Organization = django_apps.get_model("organizations", "Organization")
        out_dir = os.path.expanduser(options["out_dir"])
        os.makedirs(out_dir, mode=0o700, exist_ok=True)
        with rls_worker_atomic(), bypass_rls():
            organization = Organization.objects.filter(slug=str(options["org"]).strip()).first()
            if organization is None:
                raise CommandError("twin_plans_organization_unknown")
            with transaction.atomic():
                builder = PlanBuilder(organization=organization, bundle=bundle, until=until)
                plans = {name: getattr(builder, method)() for name, method in FILES}
                transaction.set_rollback(True)  # qurucu yazmır; hər ehtimala qarşı
        for name, plan in plans.items():
            path = os.path.join(out_dir, name)
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(plan, handle, ensure_ascii=False, indent=1, sort_keys=True)
        self.stdout.write(PREFIX + " " + " ".join(f"{k}={v}" for k, v in sorted(builder.counts.items())))

    def _bundle(self, options) -> dict:
        if options["bundle"]:
            try:
                return read_bundle(options["bundle"])
            except BundleError as error:
                raise CommandError(str(error)) from None
        if not options["legacy_source"] or not options["full_semester"]:
            raise CommandError("twin_plans_source_required: --bundle və ya --legacy-source + --full-semester")
        import pymysql

        from apps.legacy_import.services.delta.extract import DeltaExtractor, build_bundle

        try:
            connection = pymysql.connect(
                host=options["host"],
                port=options["port"],
                user=options["user"],
                password=os.environ.get("LEGACY_DELTA_MARIADB_PASSWORD", ""),
                charset="utf8mb4",
                read_timeout=600,
            )
        except pymysql.MySQLError as error:
            raise CommandError(f"twin_plans_legacy_unavailable: {error.__class__.__name__}") from None
        with connection.cursor() as cursor:
            cursor.execute("SET SESSION TRANSACTION READ ONLY")
            cursor.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT")
            extractor = DeltaExtractor(cursor, source=options["legacy_source"], full_semesters=options["full_semester"])
            bundle = build_bundle(extractor, snapshot={"source_schema": options["legacy_source"]}, since="")
            cursor.execute("ROLLBACK")
        connection.close()
        return bundle
