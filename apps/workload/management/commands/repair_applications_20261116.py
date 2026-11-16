"""``repair_applications_20261116`` — RİM müraciətləri MR-000393 / MR-000395 / MR-000396 (2026-11-16).

Qaydalar: :mod:`apps.workload.services.applications_repair_2026_11_16` (+ ``_elective`` / ``_people``). Prod id-ləri
yoxdur — hər obyekt ad + əlaqə ilə tapılır, təkliyi yoxlanılır. DEFOLT DRY-RUN (eyni kod, geri qaytarılır). Hər
qaçışın ``batch`` id-si var (apply ``apps16: batch=apps16-…`` çap edir); ``--undo --batch <id>`` yalnız həmin qaçışı
geri qaytarır. Əmr dərs yükü app-ındadır, çünki registrar dərs yükünü import etmir (modul sərhədi) — gövdə
``relocate_twin_enrollment.run_plan`` ilə eynidir (``rls_worker_atomic()`` + ``bypass_rls()`` + RLS konteksti).
Stdout-a YALNIZ saylar; gözlənilməz xəta ``CommandError: applications_repair_failed_<sinif>_<mətn>``.
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

from ...services import applications_repair_2026_11_16 as repair

PREFIX = "apps16:"
_BATCH = re.compile(r"^apps16-\d{8}-\d{6}-[0-9a-f]{4}$")


def failure_code(exc: Exception) -> str:
    slug = re.sub(r"[^a-z_]+", "_", f"{type(exc).__name__}_{exc}".lower()).strip("_")
    return f"applications_repair_failed_{slug}"[:120]


class Command(BaseCommand):
    help = "RİM müraciətləri 2026-11-16 (MR-393 seçmə fənn, MR-395 proqram, MR-396 jurnal köçürməsi); defolt dry-run."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")
        parser.add_argument("--batch", default="", help="Qaçış id-si (apps16-…); --undo üçün məcburi")
        parser.add_argument("--undo", action="store_true", help="--batch qaçışını geri qaytar")

    def handle(self, *args, **options):
        batch = str(options["batch"] or "").strip()
        if batch and not _BATCH.match(batch):
            raise CommandError("applications_repair_batch_invalid")
        if options["undo"] and not batch:
            raise CommandError("applications_repair_undo_needs_batch")
        actor = get_user_model().objects.filter(username=options["actor"], is_active=True, is_superuser=True).first()
        if actor is None:
            raise CommandError("actor_must_be_active_superuser")
        counts, used = Counter(), {}
        try:
            self._run(options, actor=actor, batch=batch, counts=counts, used=used)
        except CommandError:
            raise
        except Exception as exc:  # noqa: BLE001 — prod-data-ops yalnız CommandError kodunu göstərir
            raise CommandError(failure_code(exc)) from None
        self.stdout.write(f"{PREFIX} mode={'apply' if options['apply'] else 'dry_run'}")
        # prod-data-ops yalnız ``[a-z_]+=`` açarlarını buraxır — xəta kodundakı nöqtə/rəqəm sətri gizlətməsin.
        self.stdout.write(
            PREFIX + " " + " ".join(f"{re.sub(r'[^a-z_]', '_', key)}={value}" for key, value in sorted(counts.items()))
        )
        if used.get("batch") and options["apply"]:
            self.stdout.write(f"{PREFIX} batch={used['batch']}")

    @staticmethod
    def _run(options, *, actor, batch, counts, used) -> None:
        Organization = django_apps.get_model("organizations", "Organization")
        with rls_worker_atomic(), bypass_rls():
            organization = Organization.objects.filter(slug=str(options["org"]).strip()).first()
            if organization is None:
                raise CommandError("applications_repair_organization_unknown")
            apply_rls_request_context(user_id=actor.pk, org_id=organization.pk)
            with transaction.atomic():
                if options["undo"]:
                    repair.undo(organization=organization, actor=actor, counts=counts, batch=batch)
                else:
                    used["batch"] = repair.run(organization=organization, actor=actor, counts=counts, batch=batch)
                if not options["apply"]:
                    transaction.set_rollback(True)
