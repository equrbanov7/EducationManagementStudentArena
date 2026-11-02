"""One source-bound Asəf60h stream; dry default, full-grade preservation, exact undo."""

import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.rls import apply_rls_request_context, reset_rls_context
from core.rls_pooling import rls_worker_atomic

from ...services import reviewed_gunay_ethnography_repair as repair
from ...services import reviewed_gunay_ethnography_spec as spec
from ...services.reviewed_leyla_catalog_graph import RepairError, model


class Command(BaseCommand):
    help = "Restore official ethnography30L shared and15S per subgroup; preserve journal history."

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
            raise CommandError("gunay_active_tenant_superadmin_required")
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
            code = str(exc)
            if (
                not code.startswith(("gunay_", "two_catalog_", "leyla_"))
                or not code.replace("_", "").isalnum()
                or len(code) > 100
            ):
                code = "gunay_reviewed_guard_failed"
            raise CommandError(code) from None
        except Exception:
            raise CommandError("gunay_snapshot_or_repair_failed") from None
        finally:
            reset_rls_context(local=True)
        self.stdout.write("reviewed_gunay_ethnography: " + json.dumps(result, sort_keys=True))
