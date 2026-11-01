"""Fixed four-course Solmaz source/patok correction; no arbitrary selectors."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.workload.public import reviewed_catalog_graph as evidence
from core.rls import apply_rls_request_context, reset_rls_context
from core.rls_pooling import rls_worker_atomic

from ...services import reviewed_solmaz_recovery as repair
from ...services import reviewed_solmaz_spec as spec


class Command(BaseCommand):
    help = "Solmazın165 saatlıq patokunu və öz sillabusunu qorunan dəqiq mənbə ilə yoxla; defolt dry-run."

    def add_arguments(self, parser):
        parser.add_argument("--actor", required=True)
        parser.add_argument("--manifest", required=True)
        parser.add_argument("--manifest-sha256", required=True)
        parser.add_argument("--expected-baseline", default="")
        parser.add_argument("--undo", default="")
        parser.add_argument("--apply", action="store_true")

    @rls_worker_atomic()
    @transaction.atomic
    def handle(self, *args, **options):
        actor = get_user_model().objects.filter(username=options["actor"], is_active=True, is_superuser=True).first()
        if actor is None:
            raise CommandError("solmaz_active_superadmin_required")
        apply_rls_request_context(user_id=actor.pk, org_id=spec.ORG, bypass=False, local=True)
        try:
            org = evidence.model("organizations.Organization").objects.get(pk=spec.ORG)
            result = repair.run(
                org,
                actor,
                options["manifest"],
                options["manifest_sha256"],
                apply=options["apply"],
                expected_baseline=options["expected_baseline"],
                undo=options["undo"],
            )
        except evidence.RepairError as exc:
            # All codes are fixed literals owned by this service, not user/source bodies.
            code = str(exc)
            if not code.startswith("solmaz_") or not code.replace("_", "").isalnum():
                code = "solmaz_reviewed_guard_failed"
            raise CommandError(code) from None
        except Exception:
            raise CommandError("solmaz_current_evidence_unavailable") from None
        finally:
            reset_rls_context(local=True)
        self.stdout.write(
            "reviewed_solmaz_catalog: "
            + " ".join(
                f"{k}={int(v) if isinstance(v, bool) else v if v is not None else 'none'}"
                for k, v in sorted(result.items())
            )
        )
