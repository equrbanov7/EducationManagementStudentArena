"""Fixed six candidates: mask, credit and canonical effects, with no mutation mode."""

import json
import re

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.rls import apply_rls_request_context, reset_rls_context
from core.rls_pooling import rls_worker_atomic

from ... import reaudit_journal_structure_spec as spec
from ...reaudit_journal_structure_diagnostics import inspect


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--actor", required=True)

    @rls_worker_atomic()
    @transaction.atomic
    def handle(self, *args, **options):
        actor = get_user_model().objects.filter(username=options["actor"], is_active=True, is_superuser=True).first()
        if actor is None:
            raise CommandError("structure_active_superuser")
        apply_rls_request_context(user_id=actor.pk, org_id=spec.ORG, bypass=False, local=True)
        try:
            result = inspect(
                organization=apps.get_model("organizations.Organization").objects.get(pk=spec.ORG), actor=actor
            )
        except Exception as exc:
            raise CommandError(
                str(exc) if re.fullmatch(r"structure_[a-z_]+", str(exc)) else "structure_refused"
            ) from None
        finally:
            reset_rls_context(local=True)
        self.stdout.write("reaudit_duplicate_qb: " + json.dumps(result, sort_keys=True))
