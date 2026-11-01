"""Default dry-run for one sealed58-QB source and its fixed host/workflow."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, transaction

from apps.workload.public import fixed_source58_source_scope
from core.rls import apply_rls_request_context, reset_rls_context
from core.rls_pooling import rls_worker_atomic

from ...services.reviewed_content_contract import ContentError
from ...services.reviewed_content_state import model
from ...services.reviewed_source58 import execute
from ...services.reviewed_source58_source import load_source
from ...services.reviewed_source58_undo import undo


class Command(BaseCommand):
    help = "Sabit58 q/b mənbəsinin cari tam sübutla yoxlanması; defolt yalnız dry-run."

    def add_arguments(self, parser):
        parser.add_argument("--actor", required=True)
        parser.add_argument("--manifest", required=True)
        parser.add_argument("--manifest-sha256", required=True)
        parser.add_argument("--baseline", default="")
        parser.add_argument("--undo", default="")
        parser.add_argument("--receipt-sha256", default="")
        parser.add_argument("--apply", action="store_true")

    @rls_worker_atomic()
    @transaction.atomic
    def handle(self, *args, **options):
        scope = fixed_source58_source_scope()
        user = get_user_model().objects.filter(username=options["actor"], is_active=True, is_superuser=True).first()
        if user is None:
            raise CommandError("reviewed_source58_active_superadmin_required")
        apply_rls_request_context(user_id=user.pk, org_id=scope["organization_id"], bypass=False)
        try:
            organization = model("organizations.Organization").objects.get(pk=scope["organization_id"], is_active=True)
            data = load_source(options["manifest"], options["manifest_sha256"])
            kwargs = dict(
                data=data,
                source_sha256=options["manifest_sha256"],
                user=user,
                organization=organization,
                apply=options["apply"],
                expected_baseline=options["baseline"],
            )
            if options["undo"]:
                result = undo(**kwargs, batch=options["undo"], receipt_sha256=options["receipt_sha256"])
            else:
                if options["receipt_sha256"]:
                    raise ContentError("reviewed_source58_unused_receipt_sha")
                result = execute(**kwargs)
        except ContentError as exc:
            raise CommandError(str(exc)) from exc
        except (ValueError, KeyError, TypeError, OSError, DatabaseError) as exc:
            raise CommandError("reviewed_source58_current_evidence_or_operation_unavailable") from exc
        finally:
            reset_rls_context()
        mode = "apply" if options["apply"] else "dry_run"
        self.stdout.write(
            "source58: mode=" + mode + " " + " ".join(f"{key}={value}" for key, value in sorted(result.items()))
        )
