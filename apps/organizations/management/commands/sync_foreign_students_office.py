"""``sync_foreign_students_office`` — şöbə əməkdaşlarına hər aktiv əcnəbi qrupu üçün əhatə (sahib 2026-11-25).

Qayda: :mod:`apps.organizations.foreign_office_sync`. DEFOLT DRY-RUN; ``--apply`` ilə bir tranzaksiyada, hər üzvlük
üçün AuditLog. İdempotent — yeni əcnəbi qrupu açılandan sonra təkrar işlədilir. Stdout-a YALNIZ saylar.

İstifadə::

    manage.py sync_foreign_students_office --org qku [--apply]
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

from ...foreign_office_sync import apply, ensure_roles, plan

PREFIX = "foreign_students_office:"


class Command(BaseCommand):
    help = "Əcnəbi tələbələrlə iş şöbəsinin əməkdaşlarına hər aktiv əcnəbi qrupu üçün rol əhatəsi verir."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")

    def handle(self, *args, **options):
        Organization = django_apps.get_model("organizations", "Organization")
        try:
            with rls_worker_atomic(), bypass_rls():
                organization = Organization.objects.filter(slug=str(options["org"]).strip()).first()
                if organization is None:
                    raise CommandError("foreign_students_office_organization_unknown")
                counts, wanted = plan(organization)
                if options["apply"]:
                    with transaction.atomic():
                        ensure_roles(organization)
                        counts["written"] = apply(organization, wanted)
        except CommandError:
            raise
        except Exception as exc:  # noqa: BLE001 — prod-data-ops yalnız `CommandError: <kod>` sətrini göstərir
            raise CommandError(f"foreign_students_office_failed_{type(exc).__name__.lower()}") from exc
        self.stdout.write(f"{PREFIX} mode={'apply' if options['apply'] else 'dry_run'}")
        self.stdout.write(PREFIX + " " + " ".join(f"{key}={value}" for key, value in sorted(counts.items())))
