"""Fixed 8388→7730 merge: fresh dry report first, exact baseline required for apply."""

import json
import os
from pathlib import Path

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.services import reviewed_jale_merge as service
from core.rls import apply_rls_request_context, bypass_rls
from core.rls_pooling import rls_worker_atomic


class Command(BaseCommand):
    help = "Reviewed Jalə alias consolidation; dry-run by default; unknown references block."

    def add_arguments(self, parser):
        parser.add_argument("--report", required=True)
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--baseline-sha256", default="")
        parser.add_argument("--reason", default="")
        parser.add_argument("--i-know-this-is-production", action="store_true")

    def handle(self, *args, **options):
        if options["apply"] and not options["i_know_this_is_production"]:
            raise CommandError("jale_merge_explicit_target_required")
        with rls_worker_atomic(), transaction.atomic(), bypass_rls():
            actor = apps.get_model("auth.User").objects.get(pk=service.ACTOR)
            organization = apps.get_model("organizations.Organization").objects.get(pk=service.ORG)
            apply_rls_request_context(user_id=actor.pk, org_id=organization.pk)
            try:
                if options["apply"]:
                    result = service.execute(
                        organization,
                        actor,
                        options["baseline_sha256"],
                        options["reason"],
                    )
                else:
                    result = service.snapshot(organization, actor)
            except service.MergeError as error:
                raise CommandError(str(error)) from None
            path = Path(options["report"])
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w") as stream:
                json.dump(result, stream, ensure_ascii=False, sort_keys=True, default=str)
            self.stdout.write("Jalə reviewed report saved; no credentials exported.")
