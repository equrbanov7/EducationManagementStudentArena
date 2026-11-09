"""Default dry-run; reviewed private manifest, source authority and fresh locked baseline."""

import json
import re

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.rls import apply_rls_request_context, reset_rls_context
from core.rls_pooling import rls_worker_atomic

from ... import reaudit_journal_structure as repair
from ... import reaudit_journal_structure_spec as spec


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--actor", required=True)
        parser.add_argument("--file", required=True)
        parser.add_argument("--file-sha256", required=True)
        parser.add_argument("--authority-file", default="")
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--expected-baseline", default="")
        parser.add_argument("--undo", default="")

    @rls_worker_atomic()
    @transaction.atomic
    def handle(self, *args, **options):
        try:
            manifest = spec.validate(json.loads(spec.private_bytes(options["file"], options["file_sha256"])))
            authority = (
                spec.private_bytes(options["authority_file"], manifest["authority_sha256"])
                if options["apply"]
                else None
            )
            actor = (
                get_user_model().objects.filter(username=options["actor"], is_active=True, is_superuser=True).first()
            )
            if actor is None:
                raise ValueError("structure_active_superuser")
            apply_rls_request_context(user_id=actor.pk, org_id=spec.ORG, bypass=False, local=True)
            try:
                result = repair.run(
                    organization=apps.get_model("organizations.Organization").objects.get(pk=spec.ORG),
                    actor=actor,
                    manifest=manifest,
                    authority_bytes=authority,
                    **{key: options[key] for key in ("apply", "expected_baseline", "undo")},
                )
            finally:
                reset_rls_context(local=True)
        except Exception as exc:
            code = str(exc)
            raise CommandError(code if re.fullmatch(r"structure_[a-z_]+", code) else "structure_refused") from None
        self.stdout.write("reaudit_journal_structure: " + json.dumps(result, sort_keys=True))
