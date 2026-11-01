"""Default read-only receipt-bound undo for the one fixed source28 case."""

import re

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, transaction

from apps.workload.public import describe_read_only_export_error, render_read_only_export_error
from core.rls import apply_rls_request_context, reset_rls_context
from core.rls_pooling import rls_worker_atomic

from ...services.reviewed_content_28_spec import TARGET
from ...services.reviewed_content_28_undo import undo
from ...services.reviewed_content_contract import ContentError, load_payload
from ...services.reviewed_content_spec import ORG
from ...services.reviewed_content_state import model


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--actor", required=True)
        parser.add_argument("--manifest", required=True)
        parser.add_argument("--manifest-sha256", required=True)
        parser.add_argument("--batch", required=True)
        parser.add_argument("--expected-baseline", default="")
        parser.add_argument("--apply", action="store_true")

    @rls_worker_atomic()
    @transaction.atomic
    def handle(self, *args, **options):
        actor = get_user_model().objects.filter(username=options["actor"], is_active=True, is_superuser=True).first()
        if actor is None:
            raise CommandError("active_superadmin_required")
        apply_rls_request_context(user_id=actor.pk, org_id=ORG, bypass=False)
        try:
            data = load_payload(options["manifest"], options["manifest_sha256"], [TARGET])
            result = undo(
                data=data,
                source_sha256=options["manifest_sha256"],
                user=actor,
                organization=model("organizations.Organization").objects.get(pk=ORG, slug="qku", is_active=True),
                batch=options["batch"],
                apply=options["apply"],
                expected_baseline=options["expected_baseline"],
            )
        except ContentError as exc:
            fields = self._diagnostic(exc)
            code = fields["guard"] if fields["guard"] != "unclassified" else "source28_undo_guard_failed"
            raise CommandError(code) from exc
        except (ValueError, OSError, DatabaseError) as exc:
            self._diagnostic(exc)
            raise CommandError("source28_undo_input_or_database_guard_failed") from exc
        finally:
            reset_rls_context()
        if not re.fullmatch(r"[a-f0-9]{64}", result.get("baseline", "")):
            raise CommandError("source28_undo_summary_invalid")
        counts = [result.get(key, 0) for key in ("deleted_lessons", "deleted_marks", "already_undone")]
        if any(type(value) is not int or value < 0 or value > 28 for value in counts):
            raise CommandError("source28_undo_summary_invalid")
        mode = "undo" if options["apply"] else "dry_run"
        self.stdout.write(
            f"reviewed_source28_undo: mode={mode} baseline={result['baseline']} "
            f"deleted_lessons={counts[0]} deleted_marks={counts[1]} already_undone={counts[2]}"
        )

    def _diagnostic(self, exc):
        fields = describe_read_only_export_error(exc, "source28_undo")
        self.stderr.write("reviewed_source28_diagnostic: " + render_read_only_export_error(fields))
        return fields
