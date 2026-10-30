"""Exact MR116/117 teacher-confirmed lesson label correction."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from core.rls import apply_rls_request_context
from core.rls_pooling import rls_worker_atomic

from ...request_schedule_labels import RepairError, run


class Command(BaseCommand):
    help = "MR116/117 iki dərsin cədvəldən kənar nişanını düzəlt (default dry-run)."

    def add_arguments(self, parser):
        parser.add_argument("--actor", required=True)
        parser.add_argument("--expected-baseline", default="")
        parser.add_argument("--apply", action="store_true")

    @rls_worker_atomic()
    def handle(self, *args, **options):
        # This exact dossier is WCU-scoped; never enable a tenant bypass.
        from django.apps import apps

        org_id = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
        apply_rls_request_context(user_id=None, org_id=org_id, bypass=False, local=True)
        org = apps.get_model("organizations.Organization").objects.get(pk=org_id)
        user = get_user_model().objects.get(username=options["actor"], is_active=True, is_superuser=True)
        apply_rls_request_context(user_id=user.pk, org_id=org.pk, bypass=False, local=True)
        try:
            result = run(
                organization=org, user=user, apply=options["apply"], expected_baseline=options["expected_baseline"]
            )
        except RepairError as exc:
            raise CommandError(str(exc)) from exc
        mode = "apply" if options["apply"] else "dry_run"
        fields = [f"mode={mode}"]
        for key in ("baseline", "pending", "already_present", "applied"):
            if key in result:
                fields.append(f"{key}={result[key]}")
        self.stdout.write("request_schedule_labels: " + " ".join(fields))
