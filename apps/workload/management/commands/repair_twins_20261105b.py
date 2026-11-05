"""``repair_twins_20261105b`` — əkiz jurnallar MR-190 (235 İ ing) + MR-161 (234 M rus); sabit id-lər, defolt dry-run.

Qaydalar: :mod:`apps.registrar.twins_repair_2026_11_05b` (jurnal tərəfi — bal + imtahan bağı + birləşmə, boş
birləşmənin bərpası) və :mod:`apps.workload.services.twin_load_row` (yük sətrinin fənni). Əmr dərs yükü app-ındadır,
çünki registrar dərs yükünü import etmir (modul sərhədi). Plan faylı yoxdur. DRY-RUN: eyni yazılar icra olunub geri
qaytarılır. Stdout-a YALNIZ saylar (``twin_merge: açar=say …``); prod-data-ops həmin sətirləri süzür.
"""

from __future__ import annotations

from collections import Counter

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.registrar.public import twins_repair_2026_11_05b as dossier
from core.rls import apply_rls_request_context, bypass_rls
from core.rls_pooling import rls_worker_atomic

from ...services.twin_load_row import switch_load_row

PREFIX = "twin_merge:"
#: MR-161 yük sətrinin köhnə fənni — QKU-1817 «Təsərrüfatların intensiv idarə edilməsi».
MR161_OLD_SUBJECT = "47a26a97-b386-4e19-a494-85a3083631c9"


def run(*, organization, actor, counts) -> None:
    if dossier.run(organization=organization, actor=actor, counts=counts):
        switch_load_row(
            organization=organization,
            user=actor,
            row_id=dossier.MR161_ROW,
            offering_id=dossier.MR161_TWIN,
            old_subject_id=MR161_OLD_SUBJECT,
            counts=counts,
        )


class Command(BaseCommand):
    help = "Əkiz jurnallar 2026-11-05: MR-190 (235 İ ing, Midterm + imtahan bağı) və MR-161 (234 M rus) — dry-run."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")

    def handle(self, *args, **options):
        actor = get_user_model().objects.filter(username=options["actor"], is_active=True, is_superuser=True).first()
        if actor is None:
            raise CommandError("actor_must_be_active_superuser")
        Organization = django_apps.get_model("organizations", "Organization")
        counts = Counter()
        with rls_worker_atomic(), bypass_rls():
            organization = Organization.objects.filter(slug=str(options["org"]).strip()).first()
            if organization is None:
                raise CommandError("twin_merge_organization_unknown")
            apply_rls_request_context(user_id=actor.pk, org_id=organization.pk)
            with transaction.atomic():
                run(organization=organization, actor=actor, counts=counts)
                if not options["apply"]:
                    transaction.set_rollback(True)
        self.stdout.write(f"{PREFIX} mode={'apply' if options['apply'] else 'dry_run'}")
        self.stdout.write(PREFIX + " " + " ".join(f"{key}={value}" for key, value in sorted(counts.items())))
