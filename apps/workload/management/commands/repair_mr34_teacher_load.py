"""Five fixed MR34 assignments only; dry-run by default, no role/journal changes."""

import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.rls import apply_rls_request_context, reset_rls_context
from core.rls_pooling import rls_worker_atomic

from ...services import mr34_teacher_spec as spec
from ...services.mr34_teacher_repair import run
from ...services.sbio235_state import RepairError, model


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument("--actor", required=True)
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--expected-baseline", default="")
        parser.add_argument("--undo", default="")

    @rls_worker_atomic()
    @transaction.atomic
    def handle(self, *args, **options):
        user = get_user_model().objects.filter(username=options["actor"], is_active=True, is_superuser=True).first()
        if user is None:
            raise CommandError("mr34_active_postgresql_superadmin_required")
        apply_rls_request_context(user_id=user.pk, org_id=spec.ORG, bypass=False)
        try:
            result = run(
                organization=model("organizations.Organization").objects.get(pk=spec.ORG),
                user=user,
                apply=options["apply"],
                expected_baseline=options["expected_baseline"],
                undo=options["undo"],
            )
        except RepairError as exc:
            raise CommandError(str(exc)) from exc
        finally:
            reset_rls_context()
        self.stdout.write(json.dumps(result, sort_keys=True))
