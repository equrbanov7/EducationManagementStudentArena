"""``reassign_dean_office_laborants_20261127`` — fakültəyə bağlı laborantlar «Dekanlıq laborantı» rolunu alır.

Qayda: :mod:`apps.organizations.dean_office_laborants` (``lab_assistant`` @ ``faculty``/``deanery`` →
``dean_office_assistant``; kafedra laborantları toxunulmur). DEFOLT DRY-RUN — heç nə yazmır, yalnız sayları və
bölmə + üzvlük id siyahısını göstərir (``--names`` ilə istifadəçi adları da). ``--apply`` ilə bir tranzaksiyada,
hər üzvlük üçün AuditLog. İdempotent — təkrar işlədiləndə namizəd qalmır.

İstifadə::

    manage.py reassign_dean_office_laborants_20261127 --org qku [--names] [--apply]
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

from ...dean_office_laborants import apply, plan

PREFIX = "dean_office_laborants:"


class Command(BaseCommand):
    help = "Fakültəyə / dekanlığa bağlı «lab_assistant» üzvlüklərini «Dekanlıq laborantı» roluna keçirir (dry-run)."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--names", action="store_true", help="Siyahıda istifadəçi adlarını da göstər")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")

    def handle(self, *args, **options):
        Organization = django_apps.get_model("organizations", "Organization")
        lines = []
        try:
            with rls_worker_atomic(), bypass_rls():
                organization = Organization.objects.filter(slug=str(options["org"]).strip()).first()
                if organization is None:
                    raise CommandError("dean_office_laborants_organization_unknown")
                counts, rows = plan(organization)
                for membership, target in rows:
                    who = f" user={membership.user.username}" if options["names"] else ""
                    action = "reactivate" if target is not None else "switch"
                    lines.append(
                        f"{PREFIX} {action} membership={membership.pk} unit={membership.scope_unit.name!r}{who}"
                    )
                if options["apply"]:
                    with transaction.atomic():
                        counts["written"] = apply(organization, rows)
        except CommandError:
            raise
        except Exception as exc:  # noqa: BLE001 — prod-data-ops yalnız `CommandError: <kod>` sətrini göstərir
            raise CommandError(f"dean_office_laborants_failed_{type(exc).__name__.lower()}") from exc
        self.stdout.write(f"{PREFIX} mode={'apply' if options['apply'] else 'dry_run'}")
        for line in lines:
            self.stdout.write(line)
        self.stdout.write(PREFIX + " " + " ".join(f"{key}={value}" for key, value in sorted(counts.items())))
