"""``legacy_delta_extract`` — köhnə sistemin MariaDB nüsxəsindən DELTA paketi qurur (YALNIZ OXUYUR).

Lokal, izolə MariaDB konteynerində (dump-lar yüklənmiş) işlədilir; Django bazasına TOXUNMUR::

    manage.py legacy_delta_extract --port 50330 --password-file <fayl> \\
        --source myedu_new --baseline myedu_old --since 2026-08-01 \\
        --snapshot-file "~/Desktop/myedudb (1).sql" --out ~/EMSArena-backups/legacy-delta/delta.json.gz

TARİXİ boşluq paketi (sahib 2026-10-25, ``services/delta/history.py``) — Django bazası prod NÜSXƏSİ olmalıdır
(cutover ledger-i yalnız OXUNUR: köçmüş (jurnal, tələbə) cütləri paketə düşmür)::

    DATABASE_URL=postgres://…/ems_prodlive_1025 manage.py legacy_delta_extract --port 50330 \
        --password-file <fayl> --source myedu_new --history-semester 1-6 --phases history \
        --organization qku --out ~/EMSArena-backups/legacy-delta/delta-hist-a.json.gz

Yaddaş üçün (əmr app konteynerində işləyir, limit 2 GB) paketlər ayrıdır: boşluqlar semestr dəstələri ilə
(``1-6``, ``7-13``; ``--phases history``), tarixi mövzu/otaq ayrıca (``--history-semester 1-13 --phases
history_topics``). Hesab qərarının sübutu bütün jurnallardan qurulur — bölgü nəticəni dəyişmir.

Çıxış 0600 rejimli JSON.gz-dir (şəxsi məlumat var) — serverə yalnız ŞİFRƏLİ release asset kimi
gedir (bax ``docs/migration/LEGACY_DELTA_2026_10.md``). Ekrana yalnız SAYLAR çıxır.
"""

from __future__ import annotations

import os

from django.core.management.base import BaseCommand, CommandError

from apps.legacy_import.services.delta.apply import PHASES
from apps.legacy_import.services.delta.bundle import file_sha256, write_bundle
from apps.legacy_import.services.delta.extract import DeltaExtractor, build_bundle
from apps.legacy_import.services.delta.history import HISTORY_PHASES
from apps.legacy_import.services.delta.history_extract import build_history_bundle, ledger_sets, parse_semesters
from apps.legacy_import.services.repair_support import resolve_organization
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
        parser.add_argument(
            "--create-ambiguous",
            action="store_true",
            help="Adaşlardan HEÇ BİRİ tutmayan legacy tələbə yeni hesab kimi yaradılır (sahibin açıq qərarı)",
        )
        parser.add_argument(
            "--history-semester",
            default="",
            help="TARİXİ boşluq paketi (məs. 1-6): yalnız cutover ledger-ində köçməmiş (jurnal, tələbə) cütləri; "
            "ledger Django bazasından (prod NÜSXƏSİ, yalnız oxu) oxunur — --organization tələb olunur; "
            "--phases history (default) və/və ya history_topics",
        )
        parser.add_argument("--organization", default="", help="--history-semester: ledger-in təşkilatı (slug)")
        parser.add_argument(
            "--phases",
            nargs="+",
            choices=PHASES,
            default=[],
            help="Paketin tətbiqdə işlədəcəyi fazalar (snapshot.phases; məs. offerings topics) — default: hamısı",
        )

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
        history = self._history_options(options)
        # Adi delta Django bazasına toxunmur; tarixi paket yalnız ledger-i OXUYUR (rls_worker_atomic + tenant konteksti).
        with rls_worker_atomic(), connection.cursor() as cursor:
            cursor.execute("SET SESSION TRANSACTION READ ONLY")
            cursor.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT")
            extractor = DeltaExtractor(
                cursor,
                source=options["source"],
                baseline=options["baseline"],
                full_semesters=options["full_semester"],
            )
            if history:
                bundle = self._history_bundle(extractor, snapshot, history, options)
            else:
                bundle = build_bundle(extractor, snapshot=snapshot, since=options["since"])
            if options["phases"]:
                bundle["snapshot"]["phases"] = list(options["phases"])
            if options["create_ambiguous"]:
                bundle["snapshot"]["create_ambiguous"] = True
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
            "lesson_topics",
        ):
            self.stdout.write(f"  {name:15s}: {len(bundle[name])}")
        for name, rows in sorted((bundle.get("history") or {}).items()):
            if isinstance(rows, list) and name != "semesters":
                self.stdout.write(f"  history.{name:22s}: {len(rows)}")
        for name, value in sorted(((bundle.get("history") or {}).get("stats") or {}).items()):
            self.stdout.write(f"  history.stats.{name:30s}: {value}")
        if history:
            self.stdout.write(f"Fazalar: {bundle['snapshot'].get('phases')}")
        self.stdout.write(f"Paket: sha256={digest} (0600; şəxsi məlumat — yalnız şifrəli ötürün)")

    @staticmethod
    def _history_options(options):
        if not options["history_semester"]:
            return None
        if options["baseline"] or options["full_semester"]:
            raise CommandError(
                "legacy_delta_history_exclusive: --history-semester --baseline/--full-semester ilə birgə verilmir"
            )
        if not options["organization"]:
            raise CommandError("legacy_delta_history_organization_required")
        try:
            semesters = parse_semesters(options["history_semester"])
        except ValueError as error:
            raise CommandError(str(error)) from None
        allowed = set(HISTORY_PHASES)
        phases = list(options["phases"]) or ["history"]
        if set(phases) - allowed:
            raise CommandError("legacy_delta_history_bundle_phase_mismatch: yalnız history / history_topics")
        options["phases"] = phases
        return semesters

    @staticmethod
    def _history_bundle(extractor, snapshot, semesters, options):
        from core.rls import apply_rls_request_context

        organization = resolve_organization(options["organization"])
        apply_rls_request_context(user_id=0, org_id=organization.pk)
        pairs, journals = ledger_sets(organization)
        return build_history_bundle(
            extractor,
            snapshot={**snapshot, "organization": organization.slug},
            semesters=semesters,
            migrated_pairs=pairs,
            migrated_journals=journals,
            gaps="history" in options["phases"],
            topics="history_topics" in options["phases"],
        )
