"""Sabit233KE aliası; tenant, exact baseline, dry-run və auditli undo."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from core.rls import apply_rls_request_context, reset_rls_context
from core.rls_pooling import rls_worker_atomic

from ...services import ke233_alias_repair as repair
from ...services import ke233_alias_spec as spec
from ...services import ke233_alias_state as state
from ...services.scoping import WorkloadDenied


class Command(BaseCommand):
    help = "Yalnız233KE→233KEaz exact planı; dry-run defoltdur."

    def add_arguments(self, parser):
        parser.add_argument("--org", default="qku")
        parser.add_argument("--actor", required=True)
        parser.add_argument("--source-sha256", required=True)
        parser.add_argument("--expected-baseline", default="")
        parser.add_argument("--undo", default="")
        parser.add_argument("--apply", action="store_true")

    @rls_worker_atomic()
    def handle(self, *args, **options):
        if options["org"] != "qku":
            raise CommandError("tenant_slug_mismatch")
        user = get_user_model().objects.filter(username=options["actor"], is_active=True, is_superuser=True).first()
        if user is None:
            raise CommandError("active_superadmin_required")
        apply_rls_request_context(user_id=user.pk, org_id=spec.ORG, bypass=False)
        try:
            org = state.model("organizations.Organization").objects.get(pk=spec.ORG, slug=options["org"])
            result = repair.run(
                organization=org,
                user=user,
                source_sha256=options["source_sha256"],
                expected_baseline=options["expected_baseline"],
                undo=options["undo"],
                apply=options["apply"],
            )
        except (state.RepairError, WorkloadDenied) as exc:
            raise CommandError(getattr(exc, "code", str(exc))) from exc
        finally:
            reset_rls_context()
        mode = "undo" if options["undo"] and options["apply"] else "apply" if options["apply"] else "dry_run"
        self.stdout.write("ke233_alias: mode=" + mode + " " + " ".join(f"{k}={v}" for k, v in sorted(result.items())))
