"""Tam boş legacy388→367 üçün ayrıca, məhdud dry-run/apply/undo."""

import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.rls import apply_rls_request_context, reset_rls_context

from ... import empty_group_alias as repair
from ...models import Organization


class Command(BaseCommand):
    help = "Yalnız132 F→132F; tam snapshot, dry-run default, exact baseline və auditli undo."

    def add_arguments(self, parser):
        parser.add_argument("--org", default="qku")
        parser.add_argument("--actor", required=True)
        parser.add_argument("--expected-baseline", default="")
        parser.add_argument("--undo", default="")
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--summary", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        user = get_user_model().objects.filter(username=options["actor"], is_active=True, is_superuser=True).first()
        if user is None or options["org"] != "qku":
            raise CommandError("active_tenant_superadmin_required")
        apply_rls_request_context(user_id=user.pk, org_id=repair.ORG, bypass=False)
        try:
            org = Organization.objects.get(pk=repair.ORG, slug=options["org"])
            result = repair.run(
                user=user,
                organization=org,
                apply=options["apply"],
                expected_baseline=options["expected_baseline"],
                undo=options["undo"],
            )
        except repair.RepairError as exc:
            raise CommandError(str(exc)) from exc
        finally:
            reset_rls_context()
        if options["summary"]:
            mode = "apply" if options["apply"] else "dry_run"
            receipt = result.get("batch", "none")
            self.stdout.write(
                f"empty132f: mode={mode} baseline={result['baseline']} "
                f"blocked={int(result['blocked'])} applied={int(options['apply'])} receipt={receipt}"
            )
        else:
            self.stdout.write(json.dumps(result, ensure_ascii=False, sort_keys=True))
