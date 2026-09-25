"""``legacy_repair_lesson_recovery`` — J12: dərs slotu olmayan köhnə bal/qayıb xanalarının bərpası.

Production 2026-08-27 run-undan qurulub, J12 onda yox idi (``is_legacy_synthesised``
= 0).  Qayda və qapıların tam təsviri: ``services/repair_lesson_recovery.py``
(plan) və ``services/repair_lesson_recovery_apply.py`` (tətbiq).

İki rejim — ağır mənbə oxunuşu YALNIZ lokalda::

    # 1) LOKAL: plan qur — mənbə (LEGACY_MARIADB_SOURCE_*) + production-un
    #    ATILABİLƏN nüsxəsi (emsarena.rehearsal_target='disposable' MƏCBURİ)
    manage.py legacy_repair_lesson_recovery --organization qku --actor <superadmin> \\
        --build-plan <çıxış>.jsonl.gz --source-dump ~/Downloads/myedudb.sql

    # 2) SERVER: plan yoxlanılır (dry-run DEFAULT), sonra tətbiq olunur
    manage.py legacy_repair_lesson_recovery --organization qku --actor <superadmin> \\
        --plan <fayl>.jsonl.gz --plan-sha256 <manifestdəki sha256>
    manage.py legacy_repair_lesson_recovery --organization qku --actor <superadmin> \\
        --plan <fayl>.jsonl.gz --plan-sha256 <sha256> --apply --i-know-this-is-production
"""

from __future__ import annotations

from collections import Counter

from django.conf import settings as django_settings
from django.core.management.base import BaseCommand, CommandError

from apps.legacy_import.services import repair_lesson_recovery_apply as applier
from apps.legacy_import.services.preflight import LegacySourcePreflightError, inspect_legacy_source
from apps.legacy_import.services.repair_lesson_recovery import REPAIR_KEY, build_plan, resolve_source_run
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

TITLE = "legacy_repair_lesson_recovery"


class Command(BaseCommand):
    help = "J12 dərs bərpası: lokalda plan qurur (mənbə ilə), serverdə planı yoxlayıb tətbiq edir."

    def add_arguments(self, parser):
        add_repair_arguments(parser)
        mode = parser.add_mutually_exclusive_group(required=True)
        mode.add_argument("--build-plan", default="", help="LOKAL: plan faylını bu yola yaz (atılabilən klon)")
        mode.add_argument("--plan", default="", help="SERVER: tətbiq olunacaq plan faylı (.jsonl.gz)")
        parser.add_argument("--plan-sha256", default="", help="Planın manifestdəki sha256-sı (MƏCBURİ)")
        parser.add_argument("--source-run", default="", help="Hədəfi quran import run-u (default: yeganə)")
        parser.add_argument("--source-dump", default="", help="Mənbə dump faylı — sha256/ölçü preflight-ı")
        parser.add_argument("--show", type=int, default=40, help="Cədvəldə göstəriləcək sətir sayı")

    def handle(self, *args, **options):
        with rls_worker_atomic():
            context = build_context(options)
            try:
                if options["build_plan"]:
                    self._build(context, options)
                else:
                    self._verify_and_apply(context, options)
            except RepairPlanError as error:
                raise CommandError(error.code) from None

    # ── LOKAL: plan ─────────────────────────────────────────────────────────

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
        self.stdout.write(f"J12 klonda işləyir (import run {source_run.pk}) …")
        built = build_plan(
            organization=context.organization,
            actor=context.actor,
            source_factory=factory,
            out_path=options["build_plan"],
            source_run_id=str(source_run.pk),
            note=self.stdout.write,
        )
        manifest = built.manifest
        summary = {
            "plan faylı": manifest.path,
            "sha256": manifest.sha256,
            "ölçü (bayt)": manifest.size_bytes,
            **{f"sətir · {kind}": count for kind, count in sorted(manifest.counts.items())},
            "plan run-u": built.planning_run_id,
            **{
                f"issue · {code}": count
                for (code, _severity), count in sorted(built.report.issue_counts.items())
                if count
            },
        }
        self.stdout.write(render_summary(f"{TITLE} — PLAN", context, summary))
        self.stdout.write(f"\nServerdə verin: --plan-sha256 {manifest.sha256}")

    # ── SERVER: yoxla + tətbiq et ───────────────────────────────────────────

    def _verify_and_apply(self, context, options):
        plan = read_plan(options["plan"], expected_sha256=options["plan_sha256"], repair=REPAIR_KEY)
        with scoped_atomic(context):
            decided = applier.decide(context.organization, plan, limit=context.limit)
        rows = [unit.as_row() for unit in decided.units if unit.action != "already_present"]
        self.stdout.write(render_table(applier.TABLE_HEADERS, rows, max_rows=int(options["show"])))
        written: Counter = Counter()
        if context.apply:
            written = applier.apply_decided(context, decided, plan=plan, plan_sha256=plan.sha256)
        summary = {
            "plan sha256": plan.sha256,
            "import run": plan.header.get("source_run_id"),
            **{key: value for key, value in sorted(decided.counters.items())},
            "yeni xana alan qeydiyyat": len(decided.enrollment_ids),
            **({f"FAKTİKİ {key}": value for key, value in sorted(written.items())} if context.apply else {}),
        }
        self.stdout.write(render_summary(TITLE, context, summary))
