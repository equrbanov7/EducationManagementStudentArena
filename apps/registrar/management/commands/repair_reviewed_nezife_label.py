"""One exact confirmed scheduled lesson label, RLS-bound and metadata only."""

import json

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.rls import apply_rls_request_context, reset_rls_context
from core.rls_pooling import rls_worker_atomic

from ... import reviewed_nezife_label as repair


class Command(BaseCommand):
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
            raise CommandError("nezife_label_refused")
        apply_rls_request_context(user_id=user.pk, org_id=repair.ORG, bypass=False, local=True)
        try:
            result = repair.run(
                organization=apps.get_model("organizations.Organization").objects.get(pk=repair.ORG),
                user=user,
                **{k: options[k] for k in ("apply", "expected_baseline", "undo")},
            )
        except Exception:
            raise CommandError("nezife_label_refused") from None
        finally:
            reset_rls_context(local=True)
        self.stdout.write("reviewed_nezife_label: " + json.dumps(result, sort_keys=True))
