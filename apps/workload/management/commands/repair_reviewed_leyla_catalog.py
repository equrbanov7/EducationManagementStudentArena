"""Exact two-row catalog relink; dry by default, receipt-bound undo, safe stdout only."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.rls import apply_rls_request_context, reset_rls_context
from core.rls_pooling import rls_worker_atomic

from ...services import reviewed_leyla_catalog_repair as repair
from ...services import reviewed_leyla_catalog_spec as spec
from ...services.reviewed_leyla_catalog_graph import RepairError, model


class Command(BaseCommand):
    help = "Only the two reviewed Leyla catalog load rows; preserve every academic record."

    def add_arguments(self, parser):
        parser.add_argument("--actor", required=True)
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--expected-baseline", default="")
        parser.add_argument("--undo", default="")
        parser.add_argument("--expected-schedule-sha", default="")

    @rls_worker_atomic()
    @transaction.atomic
    def handle(self, *args, **options):
        actor = get_user_model().objects.filter(username=options["actor"], is_active=True, is_superuser=True).first()
        if actor is None:
            raise CommandError("leyla_active_tenant_superadmin_required")
        apply_rls_request_context(user_id=actor.pk, org_id=spec.ORG, bypass=False, local=True)
        try:
            org = model("organizations.Organization").objects.get(pk=spec.ORG)
            result = repair.run(
                organization=org,
                actor=actor,
                apply=options["apply"],
                expected_baseline=options["expected_baseline"],
                expected_schedule_sha=options["expected_schedule_sha"],
                undo=options["undo"],
            )
        except RepairError as exc:
            # A fixed code, never arbitrary exception/SQL/path/body data.
            code = (
                exc.args[0]
                if len(exc.args) == 1 and isinstance(exc.args[0], str) and exc.args[0] in spec.SAFE_GUARDS
                else "leyla_reviewed_guard_failed"
            )
            raise CommandError(code) from None
        except Exception:
            raise CommandError("leyla_snapshot_or_schedule_failed") from None
        finally:
            reset_rls_context(local=True)
        self.stdout.write(
            f"reviewed_leyla_catalog: status={result['status']} rows={result['rows']} "
            f"schedule={result.get('schedule_source_sha256', 'none')} slots={result.get('schedule_slots', 0)} "
            f"applied={int(result['applied'])} baseline={result['baseline']} receipt={result['receipt'] or 'none'}"
        )
