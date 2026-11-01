"""Fixed source-bound Gunel duplicate correction; default dry and exact receipt undo."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.rls import apply_rls_request_context, reset_rls_context
from core.rls_pooling import rls_worker_atomic

from ...services import reviewed_gunel_duplicate_repair as repair
from ...services import reviewed_gunel_duplicate_spec as spec
from ...services.reviewed_leyla_catalog_graph import RepairError, model


class Command(BaseCommand):
    prefix = "reviewed_gunel_duplicate"

    help = "Only fixed Gunel official75h canonical course and duplicate allocations; every academic record remains."

    def add_arguments(self, parser):
        parser.add_argument("--actor", required=True)
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--expected-baseline", default="")
        parser.add_argument("--undo", default="")

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
            raise CommandError("gunel_tenant_superadmin_required")
        apply_rls_request_context(user_id=actor.pk, org_id=spec.ORG, bypass=False, local=True)
        try:
            org = model("organizations.Organization").objects.get(pk=spec.ORG)
            result = repair.run(
                organization=org,
                actor=actor,
                apply=options["apply"],
                expected_baseline=options["expected_baseline"],
                undo=options["undo"],
            )
        except RepairError as exc:
            code = (
                exc.args[0] if len(exc.args) == 1 and exc.args[0] in spec.SAFE_GUARDS else "gunel_reviewed_guard_failed"
            )
            raise CommandError(code) from None
        except Exception:
            raise CommandError("gunel_snapshot_failed") from None
        finally:
            reset_rls_context(local=True)
        self.stdout.write(
            f"{self.prefix}: status={result['status']} rows={result['rows']} applied={int(result['applied'])} "
            f"baseline={result['baseline']} receipt={result['receipt'] or 'none'} graph={result['graph']} "
            f"models={result['models']} protected_rows={result['protected_rows']}"
        )
