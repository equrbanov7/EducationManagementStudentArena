"""Fixed atomic Nigar/Aruz then Vefa load-only batch; no arbitrary source selectors."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.rls import apply_rls_request_context, reset_rls_context
from core.rls_pooling import rls_worker_atomic

from ...services import reviewed_catalog_load_chain as repair
from ...services import reviewed_two_catalog_spec as spec
from ...services.reviewed_leyla_catalog_graph import RepairError, model


class Command(BaseCommand):
    help = "Exactly3 reviewed load FKs, both official contexts then explicit Vefa legacy fallback; all-or-nothing."

    def add_arguments(self, parser):
        parser.add_argument("--actor", required=True)
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--expected-baseline", default="")

    @rls_worker_atomic()
    @transaction.atomic
    def handle(self, *args, **options):
        actor = (
            get_user_model()
            .objects.only("id", "is_active", "is_superuser")
            .filter(username=options["actor"], is_active=True, is_superuser=True)
            .first()
        )
        if actor is None:
            raise CommandError("two_catalog_tenant_superadmin_required")
        apply_rls_request_context(user_id=actor.pk, org_id=spec.ORG, bypass=False, local=True)
        try:
            result = repair.run(
                organization=model("organizations.Organization").objects.get(pk=spec.ORG),
                actor=actor,
                apply=options["apply"],
                expected_baseline=options["expected_baseline"],
            )
        except RepairError as exc:
            code = (
                exc.args[0]
                if len(exc.args) == 1 and exc.args[0] in spec.SAFE_GUARDS
                else "catalog_chain_reviewed_guard_failed"
            )
            raise CommandError(code) from None
        except Exception:
            raise CommandError("catalog_chain_snapshot_failed") from None
        finally:
            reset_rls_context(local=True)
        self.stdout.write(
            f"reviewed_catalog_load_chain: status={result['status']} rows={result['rows']} "
            f"applied={int(result['applied'])} baseline={result['baseline']} receipt={result['receipt'] or 'none'} "
            f"graph={result['graph']} models={result['models']} protected_rows={result['protected_rows']}"
        )
