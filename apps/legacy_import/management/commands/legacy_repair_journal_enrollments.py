"""``legacy_repair_journal_enrollments`` — HAZIRDA OXUYANLARIN atılmış jurnal yazılışlarının bərpası.

Kateqoriyalar: K9 (qrup uyğunsuzluğu → qonaq yazılış), fake=1 jurnalları
(yeganə nəticə daşıyıcısı olduqda) və qrupu mənbədə silinmiş jurnallar (qrup yalnız
eyni dövrün TƏK qrup sübutu ilə).  Qaydalar: ``services/repair_enrollments_select.py``;
klonda təkrar: ``services/repair_enrollments_replay.py``; tətbiq:
``services/repair_enrollments_apply.py``.  J12 təmirindən SONRA işlədilir.

İki rejim — ağır mənbə oxunuşu YALNIZ lokalda::

    # 1) LOKAL: plan qur (mənbə + production nüsxəsi, J12 planı tətbiq olunmuş, marker MƏCBURİ)
    manage.py legacy_repair_journal_enrollments --organization qku --actor <superadmin> \\
        --build-plan <çıxış>.jsonl.gz --source-dump ~/Downloads/myedudb.sql [--skipped-csv <csv>]

    # 2) SERVER: plan yoxlanılır (dry-run DEFAULT), sonra tətbiq olunur
    manage.py legacy_repair_journal_enrollments --organization qku --actor <superadmin> \\
        --plan <fayl>.jsonl.gz --plan-sha256 <sha256> [--apply --i-know-this-is-production]
"""

from __future__ import annotations

from django.conf import settings as django_settings
from django.core.management.base import BaseCommand, CommandError

from apps.legacy_import.services import repair_enrollments_apply as applier
from apps.legacy_import.services.preflight import LegacySourcePreflightError, inspect_legacy_source
from apps.legacy_import.services.repair_enrollments_plan import build_plan
from apps.legacy_import.services.repair_enrollments_replay import REPAIR_KEY
from apps.legacy_import.services.repair_lesson_recovery import resolve_source_run
from apps.legacy_import.services.repair_plan_file import RepairPlanError, read_plan
from apps.legacy_import.services.repair_support import (
    add_repair_arguments,
    build_context,
    render_summary,
    render_table,
    scoped_atomic,
)
from apps.legacy_import.services.table_plan import EXPECTED_TABLE_COUNT, SOURCE_SNAPSHOT_SHA256
from core.rls_pooling import rls_worker_atomic

TITLE = "legacy_repair_journal_enrollments"


class Command(BaseCommand):
    help = "Hazırda oxuyanların atılmış (K9 / fake / silinmiş qrup) jurnal yazılışları: lokalda plan, serverdə tətbiq."

    def add_arguments(self, parser):
        add_repair_arguments(parser)
        mode = parser.add_mutually_exclusive_group(required=True)
        mode.add_argument("--build-plan", default="", help="LOKAL: plan faylını bu yola yaz (atılabilən klon)")
        mode.add_argument("--plan", default="", help="SERVER: tətbiq olunacaq plan faylı (.jsonl.gz)")
        mode.add_argument(
            "--reextract-run", default="", help="LOKAL: bitmiş plan run-undan planı yenidən çıxar (--out ilə)"
        )
        parser.add_argument("--out", default="", help="--reextract-run üçün çıxış plan faylı")
        parser.add_argument(
            "--header-from", default="", help="--reextract-run: başlıq (seçim) məlumatını bu plan faylından götür"
        )
        parser.add_argument(
            "--with-current",
            action="store_true",
            help="--reextract-run: hazırda oxuyanlar siyahısını mənbədən yenidən hesabla (MariaDB lazımdır)",
        )
        parser.add_argument(
            "--exclude-not-in-roster",
            action="store_true",
            help="--reextract-run: jurnal siyahısında olmayan tələbənin cütünü plana salma (MariaDB lazımdır)",
        )
        parser.add_argument("--plan-sha256", default="", help="Planın manifestdəki sha256-sı (MƏCBURİ)")
        parser.add_argument("--source-run", default="", help="Hədəfi quran import run-u (default: yeganə)")
        parser.add_argument("--source-dump", default="", help="Mənbə dump faylı — sha256/ölçü preflight-ı")
        parser.add_argument("--skipped-csv", default="", help="LOKAL: bərpa olunmayan cütlərin CSV-si (0600)")
        parser.add_argument("--show", type=int, default=60, help="Cədvəldə göstəriləcək sətir sayı")

    def handle(self, *args, **options):
        with rls_worker_atomic():
            context = build_context(options)
            try:
                if options["build_plan"]:
                    self._build(context, options)
                elif options["reextract_run"]:
                    self._reextract(context, options)
                else:
                    self._verify_and_apply(context, options)
            except RepairPlanError as error:
                raise CommandError(error.code) from None

    def _build(self, context, options):
        if context.apply:
            raise CommandError("legacy_repair_plan_mode_conflict: --build-plan ilə --apply verilmir")
        source_run = resolve_source_run(context.organization, options["source_run"])
        if options["source_dump"]:
            try:
                result = inspect_legacy_source(
                    source=options["source_dump"],
                    expected_sha256=SOURCE_SNAPSHOT_SHA256,
                    expected_size_bytes=int(source_run.snapshot_size_bytes),
                    expected_table_count=EXPECTED_TABLE_COUNT,
                )
            except LegacySourcePreflightError as error:
                raise CommandError(f"legacy_repair_source_preflight_failed: {error.code}") from None
            self.stdout.write(f"Mənbə dump: {result.basename} · sha256 {result.digest} · {result.size} bayt")
        from apps.legacy_import.services.rehearsal_phase_a import default_source_factory

        try:
            factory = default_source_factory(django_settings)
        except Exception as error:  # noqa: BLE001
            raise CommandError(f"legacy_repair_source_unavailable: {error}") from None
        manifest, header, counts = build_plan(
            organization=context.organization,
            actor=context.actor,
            source_factory=factory,
            out_path=options["build_plan"],
            source_run_id=str(source_run.pk),
            note=self.stdout.write,
            skipped_csv=options["skipped_csv"],
        )
        summary = {
            "plan faylı": manifest.path,
            "sha256": manifest.sha256,
            "ölçü (bayt)": manifest.size_bytes,
            "hazırda oxuyan": header["current_students"],
            **{f"  sübut · {key}": value for key, value in header["current_evidence"].items()},
            **{f"seçilən cüt · {key}": value for key, value in header["selected_pairs"].items()},
            **{f"  dilim · {key}": value for key, value in header["slice_rules"].items()},
            **{f"atlanan · {key}": value for key, value in header["skipped"].items()},
            **{f"sətir · {kind}": count for kind, count in sorted(counts.items())},
            **{
                f"klonda yad/yenilənən · {name}": f"{row['foreign_new']}/{row['updated_existing']}"
                for name, row in header["extraction"].items()
                if row["foreign_new"] or row["updated_existing"]
            },
        }
        self.stdout.write(render_summary(f"{TITLE} — PLAN", context, summary))
        self.stdout.write(f"\nServerdə verin: --plan-sha256 {manifest.sha256}")

    def _reextract(self, context, options):
        if context.apply or not options["out"]:
            raise CommandError("legacy_repair_plan_mode_conflict: --reextract-run --out tələb edir, --apply yox")
        base = None
        if options["header_from"]:
            from apps.legacy_import.services.repair_plan_file import _records

            base = next(iter(_records(options["header_from"])), None)
            base = {
                key: value for key, value in (base or {}).items() if key not in ("kind", "format", "format_version")
            }
        from apps.legacy_import.services.repair_enrollments_plan import reextract_plan

        current = self._current_students(context) if options["with_current"] else None
        rosters = self._rosters(context) if options["exclude_not_in_roster"] else None
        manifest, header, counts = reextract_plan(
            organization=context.organization,
            planning_run_id=options["reextract_run"],
            out_path=options["out"],
            base_header=base,
            current=current,
            rosters=rosters,
        )
        summary = {
            "plan faylı": manifest.path,
            "sha256": manifest.sha256,
            "ölçü (bayt)": manifest.size_bytes,
            "hazırda oxuyan (başlıqda)": len(header.get("current_legacy_students") or {}),
            **{f"istisna · {key}": value for key, value in (header.get("excluded_after_replay") or {}).items()},
            **{f"sətir · {kind}": count for kind, count in sorted(counts.items())},
            **{
                f"klonda yad/yenilənən · {name}": f"{row['foreign_new']}/{row['updated_existing']}"
                for name, row in header["extraction"].items()
                if row["foreign_new"] or row["updated_existing"]
            },
        }
        self.stdout.write(render_summary(f"{TITLE} — YENİDƏN ÇIXARIŞ", context, summary))
        self.stdout.write(f"\nServerdə verin: --plan-sha256 {manifest.sha256}")

    @staticmethod
    def _read_context(context):
        from apps.legacy_import.services.rehearsal_authorizer import build_rehearsal_authorizer
        from apps.legacy_import.services.rehearsal_phase_a import default_source_factory
        from apps.legacy_import.services.repair_enrollments_replay import _context, replay_policy
        from apps.legacy_import.services.table_plan import load_legacy_table_plan

        source_run = resolve_source_run(context.organization, "")
        return source_run, _context(
            run_id=source_run.pk,
            organization=context.organization,
            actor=context.actor,
            authorize=build_rehearsal_authorizer(),
            policy=replay_policy(),
            table_plan=load_legacy_table_plan(),
            source_factory=default_source_factory(django_settings),
            note=lambda _text: None,
        )

    def _rosters(self, context):
        """Mənbə jurnallarının ``students_id`` siyahısı (yalnız ``journals`` oxunur)."""

        from apps.legacy_import.services.repair_enrollments_select import _source_journals

        _run, read_context = self._read_context(context)
        return {uniqid: info["roster"] for uniqid, info in _source_journals(read_context).items()}

    @staticmethod
    def _current_students(context):
        """Seçimin YALNIZ hazırda oxuyan hissəsi üçün mənbə + klon oxunuşu (yazı yoxdur)."""

        from apps.legacy_import.services.repair_enrollments_select import select_pairs

        source_run, read_context = Command._read_context(context)
        return select_pairs(read_context, source_run=source_run).current

    def _verify_and_apply(self, context, options):
        plan = read_plan(options["plan"], expected_sha256=options["plan_sha256"], repair=REPAIR_KEY)
        with scoped_atomic(context):
            decided = applier.decide(context.organization, plan, limit=context.limit)
        self.stdout.write(render_table(applier.TABLE_HEADERS, decided.rows(), max_rows=int(options["show"])))
        written = {}
        if context.apply:
            written = applier.apply_decided(context, decided, plan=plan, plan_sha256=plan.sha256)
        restored = [d for d in decided.decisions if d.kind == "registrar.enrollment" and d.action == "create"]
        summary = {
            "plan sha256": plan.sha256,
            "import run": plan.header.get("source_run_id"),
            "yazılış (yeni)": len(restored),
            "tələbə (yeni yazılışı olan)": len({d.values["student_id"] for d in restored}),
            **{key: value for key, value in sorted(decided.counters.items())},
            **({f"FAKTİKİ {key}": value for key, value in sorted(written.items())} if context.apply else {}),
        }
        self.stdout.write(render_summary(TITLE, context, summary))
