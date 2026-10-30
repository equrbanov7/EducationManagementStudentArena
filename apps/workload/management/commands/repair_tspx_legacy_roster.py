"""Fixed-source TSPX roster correction; safe output contains no student identities."""

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError

from core.rls import apply_rls_request_context, reset_rls_context
from core.rls_pooling import rls_worker_atomic

from ...services import tspx_roster_repair
from ...services.sbio235_state import RepairError, model
from ...services.tspx_roster_plan import ORG, read_plan


class Command(BaseCommand):
    help = "MyEdu üzrə 135 TSPX reyestrini dəqiq 23/26+1 bölgüsü ilə bərpa edir; defolt atomik dry-run."

    output_prefix = "tspx_roster"

    def load_plan(self, options):
        return read_plan(options["manifest"], options["manifest_sha256"])

    def add_arguments(self, parser):
        parser.add_argument("--org", default="qku")
        parser.add_argument("--actor", required=True)
        parser.add_argument("--manifest", required=True)
        parser.add_argument("--manifest-sha256", required=True)
        parser.add_argument("--expected-baseline", default="")
        parser.add_argument("--undo", default="")
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
            plan = self.load_plan(options)
            organization = model("organizations.Organization").objects.get(pk=ORG, slug="qku", is_active=True)
            result = tspx_roster_repair.run(
                plan=plan,
                organization=organization,
                user=user,
                expected_baseline=options["expected_baseline"],
                undo=options["undo"],
                apply=options["apply"],
            )
        except RepairError as exc:
            raise CommandError(str(exc)) from exc
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise CommandError("tspx_private_manifest_invalid") from exc
        except (ObjectDoesNotExist, PermissionDenied, ValidationError, IntegrityError) as exc:
            raise CommandError("tspx_canonical_roster_rejected") from exc
        finally:
            reset_rls_context()
        mode = "undo" if options["undo"] and options["apply"] else "apply" if options["apply"] else "dry_run"
        self.stdout.write(
            self.output_prefix
            + ": mode="
            + mode
            + " "
            + " ".join(f"{key}={value}" for key, value in sorted(result.items()))
        )
