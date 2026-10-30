"""41 fixed, reviewed active identities; stdout carries counts and opaque hashes."""

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError

from core.rls import apply_rls_request_context, reset_rls_context
from core.rls_pooling import rls_worker_atomic

from ...services import bi_mu536_roster_repair
from ...services.bi_mu536_roster_plan import ORG, read_plan
from ...services.sbio235_state import RepairError, model


class Command(BaseCommand):
    help = "536 Bİ/MU üçün 41 mənbə+canlı şəxsiyyət üzrə alt qrup bərpası; defolt atomik dry-run."

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
            plan = read_plan(options["manifest"], options["manifest_sha256"])
            organization = model("organizations.Organization").objects.get(pk=ORG, slug="qku", is_active=True)
            result = bi_mu536_roster_repair.run(
                plan=plan,
                organization=organization,
                user=user,
                apply=options["apply"],
                expected_baseline=options["expected_baseline"],
                undo=options["undo"],
            )
        except RepairError as exc:
            raise CommandError(str(exc)) from exc
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise CommandError("bi_mu_private_manifest_invalid") from exc
        except (ObjectDoesNotExist, PermissionDenied, ValidationError, DatabaseError) as exc:
            raise CommandError("bi_mu_canonical_roster_rejected") from exc
        finally:
            reset_rls_context()
        mode = "undo" if options["undo"] and options["apply"] else "apply" if options["apply"] else "dry_run"
        self.stdout.write(
            "bi_mu536_roster: mode=" + mode + " " + " ".join(f"{key}={value}" for key, value in sorted(result.items()))
        )
