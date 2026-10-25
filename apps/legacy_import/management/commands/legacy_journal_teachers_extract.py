"""``legacy_journal_teachers_extract`` — köhnə sistemin cari semestr jurnallarından «kim hansı növü keçir» faylı.

Lokal işlədilir: MariaDB nüsxəsi (``ems-legacy-delta-src``) + Django bazası prod NÜSXƏSİ (açarlar — fənn / qrup
UUID-ləri və istifadəçi id-ləri — prod ilə eynidir). Hər iki baza YALNIZ OXUNUR; hesab yaradılmır. Qaydalar:
:mod:`apps.legacy_import.services.delta.journal_teachers`. Çıxış 0600 JSON-dur (ad / FİN YOXDUR, amma müəllim ↔
fənn bağlantısı var) — serverə ŞİFRƏLİ release asset kimi gedir (``prod-data-ops`` → ``fill_vacant_from_journals``)::

    DATABASE_URL=postgres://…/ems_prodlive_1025b manage.py legacy_journal_teachers_extract --port 50330 \\
        --password-file <fayl> --source myedu_new --organization qku \\
        --out ~/EMSArena-backups/workload-audit-20261025/legacy_journals.json

Ekrana yalnız SAYLAR çıxır.
"""

from __future__ import annotations

import os

from django.core.management.base import BaseCommand, CommandError

from apps.legacy_import.services.delta.journal_teachers import current_semester, extract, write
from apps.legacy_import.services.repair_support import resolve_organization
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic


class Command(BaseCommand):
    help = "Köhnə sistemin cari semestr jurnallarından müəllim × fəaliyyət sübut faylı (adsız, yalnız oxuyur)."

    def add_arguments(self, parser):
        parser.add_argument("--host", default="127.0.0.1")
        parser.add_argument("--port", type=int, default=50330)
        parser.add_argument("--user", default="root")
        parser.add_argument("--password-file", default="", help="MariaDB parolu (yoxsa LEGACY_DELTA_MARIADB_PASSWORD)")
        parser.add_argument("--source", required=True, help="Snapshot sxemi (məs. myedu_new)")
        parser.add_argument("--semester", type=int, default=0, help="semestr_jurnal.id (defolt: is_current=1)")
        parser.add_argument("--organization", default="qku", help="Hədəf təşkilatın slug-ı")
        parser.add_argument("--out", required=True, help="Çıxış JSON faylı (0600)")

    def handle(self, *args, **options):
        import pymysql

        password = os.environ.get("LEGACY_DELTA_MARIADB_PASSWORD", "")
        if options["password_file"]:
            with open(os.path.expanduser(options["password_file"]), encoding="utf-8") as handle:
                password = handle.read().strip()
        try:
            connection = pymysql.connect(
                host=options["host"],
                port=options["port"],
                user=options["user"],
                password=password,
                charset="utf8mb4",
                read_timeout=600,
            )
        except pymysql.MySQLError as error:
            raise CommandError(f"legacy_source_unavailable: {error.__class__.__name__}") from None
        with rls_worker_atomic(), bypass_rls(), connection.cursor() as cursor:
            cursor.execute("SET SESSION TRANSACTION READ ONLY")
            cursor.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT")
            organization = resolve_organization(options["organization"])
            semester = options["semester"] or int(current_semester(cursor, options["source"]).get("id") or 0)
            if not semester:
                raise CommandError("legacy_current_semester_unknown: --semester verin")
            data = extract(cursor, source=options["source"], semester=semester, organization=organization)
            cursor.execute("ROLLBACK")
        connection.close()
        write(options["out"], data)
        stats = " ".join(f"{key}={value}" for key, value in sorted(data["stats"].items()))
        self.stdout.write(f"legacy_journals: semester={semester} {stats}")
