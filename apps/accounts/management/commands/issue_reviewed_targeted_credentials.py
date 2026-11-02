"""Issue only exact reviewed pending usernames; no plaintext credentials leave memory."""

import json
from pathlib import Path

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.rls import apply_rls_request_context, reset_rls_context
from core.rls_pooling import rls_worker_atomic

from ...services.reviewed_targeted_credentials import BATCHES, ORG, issue


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--actor", required=True)
        parser.add_argument("--batch", choices=sorted(BATCHES), required=True)
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--baseline", default="")
        parser.add_argument("--public-key", default="")
        parser.add_argument("--output", default="")

    @rls_worker_atomic()
    @transaction.atomic
    def handle(self, *args, **options):
        actor = get_user_model().objects.filter(username=options["actor"], is_active=True, is_superuser=True).first()
        if actor is None:
            raise CommandError("targeted_credentials_refused")
        apply_rls_request_context(user_id=actor.pk, org_id=ORG, bypass=False, local=True)
        existed = bool(options["output"] and (Path(options["output"]).exists() or Path(options["output"]).is_symlink()))
        try:
            organization = apps.get_model("organizations.Organization").objects.get(pk=ORG)
            result = issue(
                organization=organization,
                actor=actor,
                **{k: options[k] for k in ("batch", "apply", "baseline", "public_key", "output")},
            )
        except Exception:
            if options["apply"] and options["output"] and not existed:
                # Never leave an encrypted result for an issuance that rolled back.
                Path(options["output"]).unlink(missing_ok=True)
            raise CommandError("targeted_credentials_refused") from None
        finally:
            reset_rls_context(local=True)
        self.stdout.write("reviewed_targeted_credentials: " + json.dumps(result, sort_keys=True))
