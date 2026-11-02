"""One source-bound Elşən duplicate345h allocations; dry default, full-grade preservation, exact undo."""

import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.rls import apply_rls_request_context, reset_rls_context
from core.rls_pooling import rls_worker_atomic

from ...services import reviewed_elshen_duplicates_repair as repair
from ...services import reviewed_elshen_duplicates_spec as spec
from ...services.reviewed_leyla_catalog_graph import RepairError, model


class Command(BaseCommand):
    help = "Restore 10 official-source duplicate rows;18 contributions removed, academic history unchanged; no journal cell changes."

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
            raise CommandError("elshen_active_tenant_superadmin_required")
        apply_rls_request_context(user_id=actor.pk, org_id=spec.PINS["organization"], bypass=False, local=True)
        try:
            org = model("organizations.Organization").objects.get(pk=spec.PINS["organization"])
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
                not code.startswith(("elshen_", "two_catalog_", "leyla_"))
                or not code.replace("_", "").isalnum()
                or len(code) > 100
            ):
                code = "elshen_reviewed_guard_failed"
            raise CommandError(code) from None
        except Exception:
            raise CommandError("elshen_snapshot_or_repair_failed") from None
        finally:
            reset_rls_context(local=True)
        self.stdout.write("reviewed_elshen_duplicates: " + json.dumps(result, sort_keys=True))
