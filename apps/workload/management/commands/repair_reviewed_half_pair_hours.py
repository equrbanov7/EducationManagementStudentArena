"""Exactly two source-proven hours-only corrections; never modify a journal cell."""

import json

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, connection, transaction

from core.rls import apply_rls_request_context
from core.rls_pooling import rls_worker_atomic

from ...services import reviewed_half_pair_spec as spec
from ...services.four_cell_diagnostics import describe, render
from ...services.reviewed_half_pair_repair import repair, source
from ...services.sbio235_state import RepairError, model
from ...services.syllabus_content_export.limits import query_budget


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--actor", required=True)
        parser.add_argument("--org", default="qku")
        parser.add_argument("--file", required=True)
        parser.add_argument("--sha256", required=True)
        parser.add_argument("--baseline", default="")
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--undo", default="")

    @rls_worker_atomic()
    @transaction.atomic(savepoint=False)
    def handle(self, *args, **options):
        try:
            if connection.vendor != "postgresql":
                raise RepairError("half_pair_postgresql_required")
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL statement_timeout = '15s'")
                cursor.execute("SET LOCAL lock_timeout = '5s'")
                if not options["apply"]:
                    cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            apply_rls_request_context(user_id=None, org_id=spec.ORG, bypass=False, local=True)
            actor = get_user_model().objects.get(username=options["actor"], is_active=True, is_superuser=True)
            apply_rls_request_context(user_id=actor.pk, org_id=spec.ORG, bypass=False, local=True)
            org = model("organizations.Organization").objects.get(pk=spec.ORG)
            if options["org"] not in (spec.ORG, org.slug):
                raise RepairError("half_pair_fixed_tenant_required")
            actor.set_active_organization_context(org)
            source(options["file"], options["sha256"])
            with query_budget():
                result = repair(
                    organization=org,
                    actor=actor,
                    expected_baseline=options["baseline"],
                    apply=options["apply"],
                    undo=options["undo"],
                )
        except RepairError as exc:
            token = (
                exc.args[0]
                if exc.args and type(exc.args[0]) is str and exc.args[0] in spec.GUARDS
                else "half_pair_review_refused"
            )
            self.stderr.write("reviewed_half_pair_guard: " + token)
            self.stderr.write("reviewed_half_pair_diagnostic: " + render(describe(exc, "capture")))
            # Only code-owned finite refusal tokens, never arbitrary source/SQL values.
            raise CommandError("half_pair_review_refused") from exc
        except (ObjectDoesNotExist, ValidationError, DatabaseError, OSError, ValueError) as exc:
            self.stderr.write("reviewed_half_pair_diagnostic: " + render(describe(exc, "capture")))
            raise CommandError("half_pair_current_scope_unavailable") from exc
        self.stdout.write("reviewed_half_pair_hours: " + json.dumps(result, sort_keys=True))
