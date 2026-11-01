"""Four exact chair courses; source-pinned dry-run, audit apply and bounded undo."""

import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.rls import apply_rls_request_context, reset_rls_context
from core.rls_pooling import rls_worker_atomic

from ...services.reviewed_chair_contacts import run, spec
from ...services.sbio235_state import RepairError, model


class Command(BaseCommand):
    help = "Only four reviewed source courses; no lesson, roster or grade writes."

    def add_arguments(self, parser):
        parser.add_argument("--actor", required=True)
        parser.add_argument("--selection", default="")
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--expected-baseline", default="")
        parser.add_argument("--undo", default="")
        parser.add_argument("--safe-summary", action="store_true")

    @rls_worker_atomic()
    @transaction.atomic
    def handle(self, *args, **options):
        user = get_user_model().objects.filter(username=options["actor"], is_active=True, is_superuser=True).first()
        if user is None:
            raise CommandError("active_tenant_superadmin_required")
        apply_rls_request_context(user_id=user.pk, org_id=spec.ORG, bypass=False)
        try:
            result = run(
                organization=model("organizations.Organization").objects.get(pk=spec.ORG, slug="qku"),
                user=user,
                selection=options["selection"],
                apply=options["apply"],
                expected_baseline=options["expected_baseline"],
                undo=options["undo"],
            )
        except RepairError as exc:
            raise CommandError(str(exc)) from exc
        finally:
            reset_rls_context()
        if options["safe_summary"]:
            impact = list(result.get("impact", {}).values())
            self.stdout.write(
                f"chair_contacts: status={result['status']} applied={int(result['applied'])} "
                f"baseline={result['baseline']} receipt={result.get('receipt') or 'none'} "
                f"attendance_changes={sum(i['derived_attendance_changes'] for i in impact)} "
                f"barred_changes={sum(i['derived_barred_changes'] for i in impact)}"
            )
        else:
            self.stdout.write(json.dumps(result, sort_keys=True))
