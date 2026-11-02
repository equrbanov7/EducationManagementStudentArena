"""Fixed current migration approvals from four genuine own active BASE sources, fixed five courses."""

import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.rls import apply_rls_request_context, reset_rls_context
from core.rls_pooling import rls_worker_atomic

from ...services import exact_syllabus_recovery as core
from ...services import own_base_syllabus_bank as repair
from ...services import own_base_syllabus_spec as spec


class Command(BaseCommand):
    help = "Five reviewed current courses from four own active BASE sources; no academic or workload changes."

    def add_arguments(self, parser):
        parser.add_argument("--actor", required=True)
        parser.add_argument("--batch", choices=("all", "ordinary", "design"), default="all")
        parser.add_argument("--file")
        parser.add_argument("--sha256")
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--baseline", default="")
        parser.add_argument("--undo", default="")

    @rls_worker_atomic()
    @transaction.atomic
    def handle(self, *args, **options):
        actor = get_user_model().objects.filter(username=options["actor"], is_active=True, is_superuser=True).first()
        if actor is None:
            raise CommandError("ownbase_tenant_superadmin_required")
        apply_rls_request_context(user_id=actor.pk, org_id=spec.ORG, bypass=False, local=True)
        try:
            if not options["undo"] and (not options["file"] or not options["sha256"]):
                raise core.RestoreError("ownbase_exact_source_packet_required")
            loaded = None if options["undo"] else repair.load(options["file"], options["sha256"])
            org = core.model("organizations.Organization").objects.get(pk=spec.ORG)
            result = repair.run(
                organization=org,
                actor=actor,
                loaded=loaded,
                apply=options["apply"],
                expected_baseline=options["baseline"],
                undo=options["undo"],
                batch=options["batch"],
            )
        except core.RestoreError as exc:
            code = str(exc)
            if not code.startswith("ownbase_") or not code.replace("_", "").isalnum():
                code = "ownbase_reviewed_guard_failed"
            raise CommandError(code) from None
        except Exception:
            raise CommandError("ownbase_snapshot_failed") from None
        finally:
            reset_rls_context(local=True)
        self.stdout.write(json.dumps(result, sort_keys=True))
