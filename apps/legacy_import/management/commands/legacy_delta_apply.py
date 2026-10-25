"""``legacy_delta_apply`` — köhnə sistemin DELTA paketini hədəfə tətbiq edir (dry-run DEFAULT).

    manage.py legacy_delta_apply --bundle delta.json.gz --organization qku               # dry-run (geri qaytarılır)
    manage.py legacy_delta_apply --bundle delta.json.gz --organization qku --apply \\
        --i-know-this-is-production --report-out /tmp/delta_report.json --names-out /tmp/delta_names.csv

Qaydalar ``apps/legacy_import/services/delta/__init__.py``-dadır: yeni sistem qalibdir (yalnız boş
doldurulur), idempotentdir (ikinci qaçış 0 yazı), bütün fazalar BİR tranzaksiyadadır. Ekrana və
``--report-out``-a yalnız SAYLAR çıxır; adlar yalnız ``--names-out`` faylına (0600) yazılır.
"""

from __future__ import annotations

import datetime
import json
import os

from django.core.management.base import BaseCommand, CommandError

from apps.legacy_import.services.delta.apply import DEFAULT_PHASES, PHASES, execute
from apps.legacy_import.services.delta.bundle import BundleError, file_sha256, read_bundle
from apps.legacy_import.services.delta.history import HistoryPhaseMismatch
from apps.legacy_import.services.repair_support import (
    add_repair_arguments,
    assert_writable_target,
    resolve_actor,
    resolve_organization,
)
from core.export_safety import safe_csv_writer
from core.rls_pooling import rls_worker_atomic


def _open_private(path: str):
    fd = os.open(os.path.expanduser(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    return os.fdopen(fd, "w", encoding="utf-8", newline="")


class Command(BaseCommand):
    help = "Köhnə sistemin cutover-dən sonrakı DELTA paketini tətbiq edir (yeni sistem qalibdir; dry-run default)."

    def add_arguments(self, parser):
        add_repair_arguments(parser)
        parser.add_argument("--bundle", required=True, help="legacy_delta_extract paketi (.json.gz)")
        parser.add_argument("--expected-sha256", default="", help="Paketin gözlənilən sha256-sı (fail-closed)")
        parser.add_argument(
            "--lessons-until",
            default="",
            help="Bu tarixdən (YYYY-MM-DD) SONRAKI dərs/xanalar atılır (default: bu gün)",
        )
        parser.add_argument(
            "--phase",
            action="append",
            choices=PHASES,
            default=[],
            help="Yalnız bu faza(lar) (default: paketin snapshot.phases-i, yoxdursa opt-in fazalardan — registry_sync, graduation, history* — başqa hamısı)",
        )
        parser.add_argument("--report-out", default="", help="Saylar (JSON, adsız)")
        parser.add_argument("--names-out", default="", help="Adlı siyahı (CSV, 0600) — yaradılan/ambiqü hesablar")

    def handle(self, *args, **options):
        if options["apply"] and options["dry_run"]:
            raise CommandError("legacy_repair_mode_conflict: --apply və --dry-run birlikdə verilə bilməz")
        path = options["bundle"]
        if options["expected_sha256"] and file_sha256(path) != options["expected_sha256"].strip().lower():
            raise CommandError("legacy_delta_bundle_digest_mismatch")
        try:
            bundle = read_bundle(path)
        except BundleError as error:
            raise CommandError(str(error)) from None
        until = datetime.date.today()
        if options["lessons_until"]:
            try:
                until = datetime.date.fromisoformat(options["lessons_until"])
            except ValueError:
                raise CommandError("legacy_delta_until_invalid") from None
        with rls_worker_atomic():
            if options["apply"]:
                assert_writable_target(allow_production=bool(options["i_know_this_is_production"]))
            organization = resolve_organization(options["organization"])
            actor = resolve_actor(organization, options["actor"])
            try:
                run = execute(
                    organization=organization,
                    actor=actor,
                    bundle=bundle,
                    apply=bool(options["apply"]),
                    until=until,
                    phases=tuple(options["phase"] or (bundle.get("snapshot") or {}).get("phases") or DEFAULT_PHASES),
                )
            except HistoryPhaseMismatch as error:
                raise CommandError(str(error)) from None
        summary = run.summary()
        summary.update(
            mode="APPLY" if options["apply"] else "DRY-RUN (geri qaytarıldı)",
            organization=organization.slug,
            lessons_until=until.isoformat(),
            snapshot=bundle.get("snapshot", {}),
        )
        self.stdout.write(f"=== legacy_delta_apply — {summary['mode']} — {run.tag} ===")
        for key, value in summary["counters"].items():
            self.stdout.write(f"  {key:52s} {value}")
        self.stdout.write("  yaradılan: " + ", ".join(f"{k}={v}" for k, v in summary["created"].items()))
        if options["report_out"]:
            with _open_private(options["report_out"]) as handle:
                json.dump(summary, handle, ensure_ascii=False, indent=2, default=str)
        if options["names_out"]:
            with _open_private(options["names_out"]) as handle:
                writer = safe_csv_writer(handle)
                writer.writerow(["növ", "ad", "qeyd"])
                writer.writerows(run.name_rows)
