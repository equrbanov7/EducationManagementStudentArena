"""``build_journal_share_plans`` — bölünmüş jurnal payları + səviyyə artığı çıxarışları + səviyyə jurnalı birləşməsi
planlarını LOKAL qurur (heç nə yazmır; sahib 2026-10-27).

Mənbə: köhnə sistemin delta paketi (``--bundle``, ``legacy_delta_extract`` çıxışı); hədəf — ``DATABASE_URL`` (prod
nüsxəsi). Çıxış qovluğunda (0600):

* ``shares.json`` (``journal-shares/1``) → ``apply_journal_shares`` (paylar + ``drop_enrollments``);
* ``levelmerge.json`` (``level-merge/1``) → ``merge_level_journals``.

Fayllarda YALNIZ id-lər var (ad / FİN yoxdur). Stdout-a YALNIZ saylar (``share_plans: açar=say …``). Qaydalar:
:mod:`apps.legacy_import.services.journal_share_plan`, :mod:`apps.legacy_import.services.level_merge_plan`.

    DATABASE_URL=postgres://…/ems_prod_copy python manage.py build_journal_share_plans --org qku \\
        --bundle ~/EMSArena-backups/legacy-delta-2026-10/delta5-….json.gz --out-dir ~/EMSArena-backups/shares-20261027
"""

from __future__ import annotations

import json
import os
import re

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.legacy_import.services.delta.bundle import BundleError, read_bundle
from apps.legacy_import.services.journal_share_plan import SharePlan
from apps.legacy_import.services.level_journal_index import LegacyIndex
from apps.legacy_import.services.level_merge_plan import LevelMergePlan
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

PREFIX = "share_plans:"
PAIR_RE = re.compile(r"^[0-9a-f-]{36}:[0-9]+$")


def write_private(path: str, data: dict) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=1, sort_keys=True)


def current_period(organization):
    """``is_current`` dövr (``apply_journal_shares`` də yalnız onu qəbul edir)."""
    AcademicPeriod = django_apps.get_model("organizations", "AcademicPeriod")
    return AcademicPeriod.objects.filter(organization=organization, is_current=True).order_by("-start_date").first()


class Command(BaseCommand):
    help = "Bölünmüş jurnal payları + səviyyə birləşməsi planları (lokal, yalnız id-lər; heç nə yazmır)."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--bundle", required=True, help="legacy_delta_extract paketi (.json.gz)")
        parser.add_argument("--out-dir", required=True, help="Plan fayllarının qovluğu (0700)")
        parser.add_argument(
            "--host-via-share",
            action="store_true",
            help="Sahibi başqa müəllim olan bölünmüş səviyyə jurnalında evi müəllimin PAYI olan açılışdan seç",
        )
        parser.add_argument(
            "--deactivate",
            action="append",
            default=[],
            help="«açılış_uuid:müəllim_id» — həmin köhnə sistem payı söndürülür (təkrarlana bilər)",
        )

    def handle(self, *args, **options):
        pairs = []
        for raw in options["deactivate"]:
            if not PAIR_RE.match(str(raw).strip()):
                raise CommandError("share_plans_bad_deactivate")
            offering, teacher = str(raw).strip().split(":")
            pairs.append((offering, int(teacher)))
        try:
            bundle = read_bundle(os.path.expanduser(options["bundle"]))
        except BundleError as error:
            raise CommandError(str(error)) from None
        Organization = django_apps.get_model("organizations", "Organization")
        out_dir = os.path.expanduser(options["out_dir"])
        os.makedirs(out_dir, mode=0o700, exist_ok=True)
        with rls_worker_atomic(), bypass_rls():
            organization = Organization.objects.filter(slug=str(options["org"]).strip()).first()
            if organization is None:
                raise CommandError("share_plans_organization_unknown")
            with transaction.atomic():
                period = current_period(organization)
                if period is None:
                    raise CommandError("share_plans_no_current_period")
                index = LegacyIndex(organization=organization, bundle=bundle, period=period)
                shares = SharePlan(index, deactivate=pairs)
                merge = LevelMergePlan(index, host_via_share=options["host_via_share"])
                plans = {"shares.json": shares.build(), "levelmerge.json": merge.build()}
                transaction.set_rollback(True)  # qurucu yazmır; hər ehtimala qarşı
        for name, plan in plans.items():
            write_private(os.path.join(out_dir, name), plan)
        counts = {**{f"index_{k}": v for k, v in index.counts.items()}, **shares.counts}
        counts.update({f"merge_{key}": value for key, value in merge.counts.items()})
        self.stdout.write(PREFIX + " " + " ".join(f"{key}={value}" for key, value in sorted(counts.items())))
