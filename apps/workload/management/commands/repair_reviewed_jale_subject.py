"""Fixed source535 relink, existing own8668 approved share, dry by default."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from core.rls import apply_rls_request_context, reset_rls_context
from core.rls_pooling import rls_worker_atomic

from ...services import reviewed_jale_subject_repair as repair
from ...services import reviewed_jale_subject_spec as spec
from ...services.reviewed_leyla_catalog_graph import RepairError, model


class Command(BaseCommand):
    help = "One fixed Jale subject correction; no grades, content, account or teacher writes."

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
            raise CommandError("jale_scoped_superadmin_required")
        apply_rls_request_context(user_id=actor.pk, org_id=spec.ORG, bypass=False, local=True)
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL lock_timeout = '5s'")
                cursor.execute("SET LOCAL statement_timeout = '120s'")
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
                else "jale_reviewed_guard_failed"
            )
            raise CommandError(code) from None
        except Exception:
            raise CommandError("jale_snapshot_or_rebind_failed") from None
        finally:
            reset_rls_context(local=True)
        self.stdout.write(
            f"reviewed_jale_subject: status={result['status']} applied={int(result['applied'])} baseline={result['baseline']} receipt={result['receipt'] or 'none'}"
        )
