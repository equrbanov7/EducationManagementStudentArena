"""Default dry-run; reviewed private manifest, source authority and fresh locked baseline."""

import json

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from core.rls import apply_rls_request_context, reset_rls_context
from core.rls_pooling import rls_worker_atomic

from ... import reaudit_journal_structure as repair
from ... import reaudit_journal_structure_spec as spec
from ... import reaudit_structure_diagnostics as diagnostics


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
        trace = diagnostics.QueryTrace()
        try:
            with connection.execute_wrapper(trace):
                manifest = spec.validate(json.loads(spec.private_bytes(options["file"], options["file_sha256"])))
                trace.operation = manifest["operation"]
                trace.phase = "authority"
                authority = (
                    spec.private_bytes(options["authority_file"], manifest["authority_sha256"])
                    if options["apply"]
                    else None
                )
                trace.phase = "actor"
                actor = (
                    get_user_model()
                    .objects.filter(username=options["actor"], is_active=True, is_superuser=True)
                    .first()
                )
                if actor is None:
                    raise ValueError("structure_active_superuser")
                trace.phase = "rls"
                apply_rls_request_context(user_id=actor.pk, org_id=spec.ORG, bypass=False, local=True)
                try:
                    trace.phase = "organization"
                    organization = apps.get_model("organizations.Organization").objects.get(pk=spec.ORG)
                    trace.phase = "repair"
                    result = repair.run(
                        organization=organization,
                        actor=actor,
                        manifest=manifest,
                        authority_bytes=authority,
                        **{key: options[key] for key in ("apply", "expected_baseline", "undo")},
                    )
                except Exception as exc:
                    trace.capture(exc)
                    raise
                finally:
                    trace.phase = "reset_rls"
                    reset_rls_context(local=True)
        except Exception as exc:
            self.stderr.write(diagnostics.PREFIX + json.dumps(trace.capture(exc), sort_keys=True))
            code = exc.args[0] if len(exc.args) == 1 and isinstance(exc.args[0], str) else None
            raise CommandError(
                code if code in diagnostics.CODES and code.startswith("structure_") else "structure_refused"
            ) from None
        self.stdout.write("reaudit_journal_structure: " + json.dumps(result, sort_keys=True))
