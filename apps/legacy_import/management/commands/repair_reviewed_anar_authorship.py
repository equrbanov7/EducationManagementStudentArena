"""One reviewed instructor-only repair; native RLS, no arbitrary target/source."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.rls import apply_rls_request_context, reset_rls_context
from core.rls_pooling import rls_worker_atomic

from ...services import reviewed_anar_authorship as repair
from ...services import reviewed_anar_state as state


class Command(BaseCommand):
    help = "Restore only 28 fixed reviewed Anar lesson instructors; dry by default."

    def add_arguments(self, parser):
        parser.add_argument("--actor", required=True)
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--expected-baseline", default="")
        parser.add_argument("--undo", default="")

    @rls_worker_atomic()
    @transaction.atomic
    def handle(self, *args, **options):
        actor = get_user_model().objects.filter(username=options["actor"], is_active=True, is_superuser=True).first()
        if actor is None:
            raise CommandError("anar_actor_required")
        apply_rls_request_context(user_id=actor.pk, org_id=state.ORG, bypass=False, local=True)
        try:
            organization = state.model("organizations.Organization").objects.get(pk=state.ORG)
            result = repair.run(
                organization=organization,
                actor=actor,
                apply=options["apply"],
                expected_baseline=options["expected_baseline"],
                undo=options["undo"],
            )
        except state.RepairError as exc:
            code = str(exc)
            # Only our own fixed machine tokens; never raw traces, row values or PII.
            if code not in state.PINS["safe_guards"]:
                code = "anar_reviewed_guard_failed"
            raise CommandError(code) from None
        except Exception:
            raise CommandError("anar_snapshot_or_repair_failed") from None
        finally:
            reset_rls_context(local=True)
        self.stdout.write(
            f"reviewed_anar_authorship: status={result['status']} applied={int(result['applied'])} count={result['count']} baseline={result['baseline']} receipt={result['receipt'] or 'none'}"
        )
