"""Fixed ten Master classification corrections; dry-run by default, guarded audit undo."""

import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.rls import apply_rls_request_context, reset_rls_context
from core.rls_pooling import rls_worker_atomic

from ...services import master_degree_repair as repair


class Command(BaseCommand):
    help = "Only ten reviewed Master degree metadata rows; exact baseline, no teaching/content changes."

    def add_arguments(self, parser):
        parser.add_argument("--actor", required=True)
        parser.add_argument("--expected-baseline", default="")
        parser.add_argument("--undo", default="")
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--safe-summary", action="store_true")

    @rls_worker_atomic()
    @transaction.atomic
    def handle(self, *args, **options):
        user = get_user_model().objects.filter(username=options["actor"], is_active=True, is_superuser=True).first()
        if user is None:
            raise CommandError("active_tenant_superadmin_required")
        apply_rls_request_context(user_id=user.pk, org_id=repair.fixed.ORG, bypass=False)
        try:
            org = repair.model("organizations.Organization").objects.get(pk=repair.fixed.ORG, slug="qku")
            result = repair.run(
                organization=org,
                user=user,
                apply=options["apply"],
                expected_baseline=options["expected_baseline"],
                undo=options["undo"],
            )
        except repair.RepairError as exc:
            raise CommandError(str(exc)) from exc
        finally:
            reset_rls_context()
        if options["safe_summary"]:
            summary = (
                f"master_degree: status={result['status']} planned={result['planned']} "
                f"applied={int(result['applied'])} baseline={result['baseline']}"
            )
            if result["receipt"]:
                summary += f" receipt={result['receipt']}"
            self.stdout.write(summary)
        else:
            self.stdout.write(json.dumps(result, sort_keys=True))
