"""``legacy_delta_extract`` — köhnə sistemin MariaDB nüsxəsindən DELTA paketi qurur (YALNIZ OXUYUR).

Lokal, izolə MariaDB konteynerində (dump-lar yüklənmiş) işlədilir; Django bazasına TOXUNMUR::

    manage.py legacy_delta_extract --port 50330 --password-file <fayl> \\
        --source myedu_new --baseline myedu_old --since 2026-08-01 \\
        --snapshot-file "~/Desktop/myedudb (1).sql" --out ~/EMSArena-backups/legacy-delta/delta.json.gz

Çıxış 0600 rejimli JSON.gz-dir (şəxsi məlumat var) — serverə yalnız ŞİFRƏLİ release asset kimi
gedir (bax ``docs/migration/LEGACY_DELTA_2026_10.md``). Ekrana yalnız SAYLAR çıxır.
"""

from __future__ import annotations

import os

from django.core.management.base import BaseCommand, CommandError

from apps.legacy_import.services.delta.bundle import file_sha256, write_bundle
from apps.legacy_import.services.delta.extract import DeltaExtractor, build_bundle
from core.rls_pooling import rls_worker_atomic


class Command(BaseCommand):
    help = "Köhnə sistemin (MariaDB) yeni snapshot-ından cutover-dən sonrakı DELTA paketini qurur (yalnız oxuyur)."

    def add_arguments(self, parser):
        parser.add_argument("--host", default="127.0.0.1")
        parser.add_argument("--port", type=int, default=50330)
        parser.add_argument("--user", default="root")
        parser.add_argument(
            "--password-file", default="", help="MariaDB parolu olan fayl (yoxsa LEGACY_DELTA_MARIADB_PASSWORD)"
        )
        parser.add_argument("--source", required=True, help="Yeni snapshot-ın sxemi (məs. myedu_new)")
        parser.add_argument("--baseline", default="", help="Cutover snapshot-ının sxemi (məs. myedu_old)")
        parser.add_argument(
            "--full-semester",
            type=int,
            action="append",
            default=[],
            help="Bütöv köçürülən semestr id-si (semestr_jurnal.id); verilməsə baseline-da olmayanlar",
        )
        parser.add_argument(
            "--since", default="2026-08-01", help="Üzrlü qayıb pəncərələri bu tarixdən (YYYY-MM-DD) götürülür"
        )
        parser.add_argument("--snapshot-file", default="", help="Mənbə dump faylı — yalnız sha256/ölçü provenansı")
        parser.add_argument("--out", required=True, help="Paket faylı (.json.gz, 0600)")

    def handle(self, *args, **options):
        import pymysql

        password = os.environ.get("LEGACY_DELTA_MARIADB_PASSWORD", "")
        if options["password_file"]:
            with open(os.path.expanduser(options["password_file"]), encoding="utf-8") as handle:
                password = handle.read().strip()
        snapshot = {"source_schema": options["source"], "baseline_schema": options["baseline"]}
        if options["snapshot_file"]:
            path = os.path.expanduser(options["snapshot_file"])
            snapshot.update(sha256=file_sha256(path), size_bytes=os.path.getsize(path))
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
            raise CommandError(f"legacy_delta_source_unavailable: {error.__class__.__name__}") from None
        # Django bazasına toxunulmur; rls_worker_atomic yalnız entry-point qaydası üçündür (tranzaksiya boşdur).
        with rls_worker_atomic(), connection.cursor() as cursor:
            cursor.execute("SET SESSION TRANSACTION READ ONLY")
            cursor.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT")
            extractor = DeltaExtractor(
                cursor,
                source=options["source"],
                baseline=options["baseline"],
                full_semesters=options["full_semester"],
            )
            bundle = build_bundle(extractor, snapshot=snapshot, since=options["since"])
            cursor.execute("ROLLBACK")
        connection.close()
        digest = write_bundle(options["out"], bundle)
        self.stdout.write(f"Tam semestrlər: {bundle['snapshot']['full_semesters']}")
        for name in (
            "periods",
            "departments",
            "specialities",
            "groups",
            "subjects",
            "workers",
            "students",
            "journals",
            "lesson_dates",
            "points",
            "excuse_windows",
            "syllabi",
        ):
            self.stdout.write(f"  {name:15s}: {len(bundle[name])}")
        self.stdout.write(f"Paket: sha256={digest} (0600; şəxsi məlumat — yalnız şifrəli ötürün)")
