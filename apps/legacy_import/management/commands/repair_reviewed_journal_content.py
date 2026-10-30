"""Exact197-source scope, default read-only audit, optional missing-only insert."""

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError

from core.rls import apply_rls_request_context, reset_rls_context
from core.rls_pooling import rls_worker_atomic

from ...services.reviewed_content import execute
from ...services.reviewed_content_contract import ContentError, load_payload
from ...services.reviewed_content_spec import ORG
from ...services.reviewed_content_state import model


class Command(BaseCommand):
    help = "197 rəsmi yük dəstinin sübutlu jurnal xanaları: defolt yalnız oxunan audit."

    def add_arguments(self, parser):
        parser.add_argument("--org", default="qku")
        parser.add_argument("--actor", required=True)
        parser.add_argument("--manifest", required=True)
        parser.add_argument("--manifest-sha256", required=True)
        parser.add_argument("--targets", nargs="+", required=True)
        parser.add_argument("--expected-baseline", default="")
        parser.add_argument("--apply", action="store_true")

    @rls_worker_atomic()
    def handle(self, *args, **options):
        if options["org"] != "qku":
            raise CommandError("fixed_tenant_slug_required")
        user = (
            get_user_model()
            .objects.only("id", "username", "is_active", "is_superuser")
            .filter(username=options["actor"], is_active=True, is_superuser=True)
            .first()
        )
        if user is None:
            raise CommandError("active_superadmin_required")
        apply_rls_request_context(user_id=user.pk, org_id=ORG, bypass=False)
        try:
            data = load_payload(options["manifest"], options["manifest_sha256"], options["targets"])
            organization = model("organizations.Organization").objects.get(pk=ORG, slug="qku", is_active=True)
            result = execute(
                data=data,
                source_sha256=options["manifest_sha256"],
                user=user,
                organization=organization,
                apply=options["apply"],
                expected_baseline=options["expected_baseline"],
            )
        except ContentError as exc:
            raise CommandError(str(exc)) from exc
        except (
            KeyError,
            TypeError,
            ValueError,
            OSError,
            ObjectDoesNotExist,
            PermissionDenied,
            ValidationError,
            DatabaseError,
        ) as exc:
            raise CommandError("reviewed_content_canonical_guard_rejected") from exc
        finally:
            reset_rls_context()
        mode = "apply" if options["apply"] else "dry_run"
        self.stdout.write(
            "reviewed_content: mode=" + mode + " " + " ".join(f"{key}={value}" for key, value in sorted(result.items()))
        )
