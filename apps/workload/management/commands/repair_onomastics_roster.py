"""Append ten fixed Onomastics home-roster links after reviewed contacts repair."""

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, connection, transaction

from core.rls import apply_rls_request_context
from core.rls_pooling import rls_worker_atomic

from ...services.onomastics_roster_repair import repair
from ...services.reviewed_chair_contacts import spec
from ...services.sbio235_state import RepairError, model


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--org", default="qku")
        parser.add_argument("--actor", required=True)
        parser.add_argument("--baseline", default="")
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--undo", default="")

    @rls_worker_atomic()
    @transaction.atomic(savepoint=False)
    def handle(self, *args, **options):
        try:
            if connection.vendor != "postgresql":
                raise RepairError("postgresql_required")
            if not options["apply"]:
                with connection.cursor() as cursor:
                    cursor.execute("SET TRANSACTION READ ONLY")
            apply_rls_request_context(user_id=None, org_id=spec.ORG, bypass=False, local=True)
            actor = (
                get_user_model()
                .objects.filter(username=options["actor"], is_active=True, is_superuser=True)
                .only("id", "is_active", "is_superuser")
                .first()
            )
            if actor is None:
                raise RepairError("active_superadmin_required")
            apply_rls_request_context(user_id=actor.pk, org_id=spec.ORG, bypass=False, local=True)
            organization = model("organizations.Organization").objects.get(pk=spec.ORG)
            if options["org"] not in (spec.ORG, organization.slug):
                raise RepairError("fixed_tenant_required")
            actor.set_active_organization_context(organization)
            result = repair(
                organization=organization,
                actor=actor,
                expected_baseline=options["baseline"],
                apply=options["apply"],
                undo=options["undo"],
            )
        except RepairError as exc:
            raise CommandError(str(exc)) from None
        except (ObjectDoesNotExist, ValidationError, DatabaseError, OSError, ValueError):
            raise CommandError("onomastics_roster_scope_conflict") from None
        mode = "apply" if options["apply"] else "dry_run"
        self.stdout.write(
            "onomastics_roster: mode="
            + mode
            + " "
            + " ".join(f"{key}={value}" for key, value in sorted(result.items()))
        )
