"""Bounded row84 contact consolidation; no journal, grade, syllabus or timetable writes."""

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, transaction

from core.rls_pooling import rls_worker_atomic

from ...services import it8179_state as state
from ...services.it8179_repair import repair_it8179_load


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--org", default="qku")
        parser.add_argument("--actor", required=True)
        parser.add_argument("--file", required=True)
        parser.add_argument("--sha256", required=True)
        parser.add_argument("--baseline", default="")
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--undo", action="store_true")

    @rls_worker_atomic()
    @transaction.atomic
    def handle(self, *args, **options):
        from core.rls import apply_rls_request_context

        user = get_user_model().objects.filter(username=options["actor"], is_active=True, is_superuser=True).first()
        if not user:
            raise CommandError("active_superadmin_required")
        # Set user before resolving tenant; both settings live in this transaction
        # under either RLS_TRANSACTION_SCOPED deployment mode.
        apply_rls_request_context(user_id=user.pk, org_id=state.ORG)
        org = state.model("organizations.Organization").objects.filter(pk=state.ORG, slug=options["org"]).first()
        if org is None and options["org"] == state.ORG:
            org = state.model("organizations.Organization").objects.filter(pk=state.ORG).first()
        if org is None:
            raise CommandError("fixed_tenant_missing")
        try:
            sha = state.load_source(options["file"], options["sha256"])
            result = repair_it8179_load(
                organization=org,
                user=user,
                source_sha256=sha,
                apply=options["apply"],
                expected_baseline=options["baseline"],
                undo=options["undo"],
            )
        except state.RepairError as exc:
            raise CommandError(str(exc)) from None
        except (ObjectDoesNotExist, ValidationError, DatabaseError):
            raise CommandError("it8179_current_scope_conflict") from None
        except OSError:
            raise CommandError("official_docx_unavailable") from None
        if not options["apply"]:
            transaction.set_rollback(True)
        mode = "apply" if options["apply"] else "dry_run"
        self.stdout.write("it8179_load: mode=" + mode + " " + " ".join(f"{k}={v}" for k, v in sorted(result.items())))
