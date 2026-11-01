"""Fixed append-only approved own source beside an unchanged empty human draft."""

import json
import re
from uuid import UUID

from django.contrib.auth import get_user_model
from django.core.exceptions import MultipleObjectsReturned, ObjectDoesNotExist
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, connection, transaction

from apps.legacy_import.services import blank_draft_syllabus_recovery as recovery
from apps.legacy_import.services import blank_draft_syllabus_spec as spec
from apps.legacy_import.services.repair_support import RepairContext, establish_rls_scope
from apps.workload.public import describe_read_only_export_error, render_read_only_export_error
from core.rls import apply_rls_request_context
from core.rls_pooling import rls_worker_atomic


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--org", default="qku")
        parser.add_argument("--actor", required=True)
        parser.add_argument("--file", default="")
        parser.add_argument("--sha256", default="")
        parser.add_argument("--baseline", default="")
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--undo", default="")

    @rls_worker_atomic()
    @transaction.atomic
    def handle(self, *args, **options):
        if options["baseline"] and not re.fullmatch("[a-f0-9]{64}", options["baseline"]):
            raise CommandError("baseline_shape")
        if options["apply"] and not options["baseline"]:
            raise CommandError("fresh_baseline_required")
        if options["undo"]:
            try:
                if str(UUID(options["undo"])) != options["undo"] or options["file"] or options["sha256"]:
                    raise ValueError
            except ValueError:
                raise CommandError("undo_arguments") from None
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL lock_timeout = '5s'")
                cursor.execute("SET LOCAL statement_timeout = '120s'")
            apply_rls_request_context(user_id=None, org_id=spec.ORG, bypass=False, local=True)
            org = recovery.core.model("organizations.Organization").objects.get(pk=spec.ORG, slug=options["org"])
            actor = get_user_model().objects.get(username=options["actor"], is_active=True, is_superuser=True)
            establish_rls_scope(RepairContext(org, actor, options["apply"], 0))
            recovery.state.actor_scope(org, actor)
            loaded = None if options["undo"] else recovery.load(options["file"], options["sha256"])
            result = recovery.run(
                org, actor, loaded, expected_baseline=options["baseline"], apply=options["apply"], undo=options["undo"]
            )
        except Exception as exc:
            diagnostic = describe_read_only_export_error(exc, "prepare")
            if isinstance(exc, (ObjectDoesNotExist, MultipleObjectsReturned)):
                diagnostic["guard"] = "fixed_scope_changed"
            elif isinstance(exc, DatabaseError):
                diagnostic["guard"] = "restore_database_conflict"
            elif isinstance(exc, OSError):
                diagnostic["guard"] = "source_file_unavailable"
            self.stderr.write("blank_draft_syllabus_diagnostic: " + render_read_only_export_error(diagnostic))
            raise CommandError(
                diagnostic["guard"] if diagnostic["guard"] != "unclassified" else "blank_draft_restore_refused"
            ) from None
        self.stdout.write(json.dumps(result, sort_keys=True))
