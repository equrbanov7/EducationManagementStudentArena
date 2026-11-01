"""Fixed source535 relink, existing own8668 approved share, dry by default."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.rls import apply_rls_request_context, reset_rls_context
from core.rls_pooling import rls_worker_atomic

from ...services import reviewed_ilahe_subject_repair as repair
from ...services import reviewed_ilahe_subject_spec as spec
from ...services.reviewed_leyla_catalog_graph import RepairError, model


class Command(BaseCommand):
    help = "One fixed Ilahe subject correction and exact existing approved8668 reuse; no grades or new approval."

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
            .objects.filter(username=options["actor"], is_active=True, is_superuser=True)
            .only("id", "is_active", "is_superuser")
            .first()
        )
        if actor is None:
            raise CommandError("ilahe_scoped_superadmin_required")
        apply_rls_request_context(user_id=actor.pk, org_id=spec.ORG, bypass=False, local=True)
        try:
            org = model("organizations.Organization").objects.only("id", "is_active", "status").get(pk=spec.ORG)
            result = repair.run(
                organization=org,
                actor=actor,
                apply=options["apply"],
                expected_baseline=options["expected_baseline"],
                undo=options["undo"],
            )
        except RepairError as exc:
            code = (
                exc.args[0]
                if len(exc.args) == 1 and isinstance(exc.args[0], str) and exc.args[0] in spec.SAFE_GUARDS
                else "ilahe_reviewed_guard_failed"
            )
            raise CommandError(code) from None
        except Exception:
            raise CommandError("ilahe_snapshot_or_rebind_failed") from None
        finally:
            reset_rls_context(local=True)
        self.stdout.write(
            f"reviewed_ilahe_subject: status={result['status']} applied={int(result['applied'])} baseline={result['baseline']} receipt={result['receipt'] or 'none'}"
        )
