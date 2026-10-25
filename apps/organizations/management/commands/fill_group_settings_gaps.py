"""``fill_group_settings_gaps`` — qrup kartının boş dil / forma xanalarını doldurur (sahib 2026-10-26).

Qayda: :mod:`apps.organizations.group_settings_gaps` (alt qrup ana qrupdan; köhnə datanın ``sector`` açarı;
qrup kodu qaydası). Yalnız BOŞ xana yazılır. DEFOLT DRY-RUN; ``--apply`` ilə bir tranzaksiyada, hər qrup üçün
AuditLog. İdempotent. Stdout-a YALNIZ saylar.

İstifadə::

    manage.py fill_group_settings_gaps --org qku [--apply]
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

from ...group_settings_gaps import apply, plan

PREFIX = "group_settings_gaps:"


class Command(BaseCommand):
    help = "Qrupların boş dil sektoru / təhsil forması xanalarını doldurur (alt qrup ana qrupdan)."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")

    def handle(self, *args, **options):
        Organization = django_apps.get_model("organizations", "Organization")
        with rls_worker_atomic(), bypass_rls():
            organization = Organization.objects.filter(slug=str(options["org"]).strip()).first()
            if organization is None:
                raise CommandError("group_settings_gaps_organization_unknown")
            counts, changes = plan(organization)
            if options["apply"]:
                with transaction.atomic():
                    counts["written"] = apply(organization, changes)
        self.stdout.write(f"{PREFIX} mode={'apply' if options['apply'] else 'dry_run'}")
        self.stdout.write(
            PREFIX + " " + " ".join(f"{key.replace('.', '_')}={value}" for key, value in sorted(counts.items()))
        )
