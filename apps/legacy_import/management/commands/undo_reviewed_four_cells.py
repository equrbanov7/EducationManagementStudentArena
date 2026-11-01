"""Default-dry strict undo of only the unchanged reviewed four-cell receipt."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from core.rls import apply_rls_request_context, reset_rls_context
from core.rls_pooling import rls_worker_atomic

from ...services.reviewed_content_contract import ContentError, load_payload
from ...services.reviewed_content_four_spec import SOURCE_SHA, TARGETS
from ...services.reviewed_content_four_undo import undo
from ...services.reviewed_content_spec import ORG
from ...services.reviewed_content_state import model


class Command(BaseCommand):
    help = "Dəqiq dörd xana bərpasının yalnız dəyişməz qəbz üzrə geri qaytarılması; defolt audit."

    def add_arguments(self, parser):
        parser.add_argument("--org", default="qku")
        parser.add_argument("--actor", required=True)
        parser.add_argument("--manifest", required=True)
        parser.add_argument("--batch", required=True)
        parser.add_argument("--expected-baseline", default="")
        parser.add_argument("--apply", action="store_true")

    @rls_worker_atomic()
    def handle(self, *args, **options):
        if options["org"] != "qku":
            raise CommandError("fixed_tenant_slug_required")
        user = get_user_model().objects.filter(username=options["actor"], is_active=True, is_superuser=True).first()
        if user is None:
            raise CommandError("active_superadmin_required")
        apply_rls_request_context(user_id=user.pk, org_id=ORG, bypass=False)
        try:
            organization = model("organizations.Organization").objects.get(pk=ORG, slug="qku", is_active=True)
            result = undo(
                data=load_payload(options["manifest"], SOURCE_SHA, sorted(TARGETS)),
                source_sha256=SOURCE_SHA,
                user=user,
                organization=organization,
                batch=options["batch"],
                apply=options["apply"],
                expected_baseline=options["expected_baseline"],
            )
        except ContentError as exc:
            raise CommandError(str(exc)) from exc
        except Exception as exc:
            raise CommandError("reviewed_four_undo_guard_rejected") from exc
        finally:
            reset_rls_context()
        mode = "undo" if options["apply"] else "dry_run"
        self.stdout.write(
            "reviewed_four_undo: mode=" + mode + " " + " ".join(f"{k}={v}" for k, v in sorted(result.items()))
        )
