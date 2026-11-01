"""Fixed audit-backed Aydin provenance FK cut; dry by default."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from core.rls import apply_rls_request_context, reset_rls_context
from core.rls_pooling import rls_worker_atomic

from ...services import reviewed_aydin_lineage_repair as repair
from ...services import reviewed_aydin_lineage_spec as spec
from ...services.reviewed_leyla_catalog_graph import RepairError, model


class Command(BaseCommand):
    help = "One fixed Aydin provenance edge; no bodies, status, author or academic record writes."

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
            raise CommandError("aydin_scoped_superadmin_required")
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
                else "aydin_reviewed_guard_failed"
            )
            raise CommandError(code) from None
        except Exception:
            raise CommandError("aydin_snapshot_or_repair_failed") from None
        finally:
            reset_rls_context(local=True)
        self.stdout.write(
            f"reviewed_aydin_lineage: status={result['status']} applied={int(result['applied'])} baseline={result['baseline']} receipt={result['receipt'] or 'none'}"
        )
