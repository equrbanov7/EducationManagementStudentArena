"""One data-driven chair selection; no broad workbook import or task confirm."""

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError

from core.rls import apply_rls_request_context, reset_rls_context
from core.rls_pooling import rls_worker_atomic

from ...services import reviewed_batch
from ...services.reviewed_batch_manifest import ORG, read_manifest, select_manifest
from ...services.sbio235_state import RepairError, model
from ...services.scoping import WorkloadDenied


class Command(BaseCommand):
    help = "Baxılmış kafedra mənbəsinin açıq seçilmiş sətirləri; defolt atomik dry-run."

    def add_arguments(self, parser):
        parser.add_argument("--org", default="qku")
        parser.add_argument("--actor", required=True)
        parser.add_argument("--manifest", required=True)
        parser.add_argument("--manifest-sha256", required=True)
        parser.add_argument("--lines", nargs="+", required=True, type=int)
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
            manifest = read_manifest(options["manifest"], options["manifest_sha256"])
            from ...services import civil_source_partition

            partition = manifest.get("format") == civil_source_partition.FORMAT
            plan = (
                None
                if partition
                else select_manifest(manifest, sha256=options["manifest_sha256"], lines=options["lines"])
            )
            organization = model("organizations.Organization").objects.get(pk=ORG, slug=options["org"], is_active=True)
            runner = civil_source_partition.run if partition else reviewed_batch.run
            selection = (
                {"manifest": manifest, "manifest_sha": options["manifest_sha256"], "lines": options["lines"]}
                if partition
                else {"plan": plan}
            )
            result = runner(
                **selection,
                organization=organization,
                user=user,
                expected_baseline=options["expected_baseline"],
                undo=options["undo"],
                apply=options["apply"],
            )
        except (RepairError, WorkloadDenied) as exc:
            raise CommandError(getattr(exc, "code", str(exc))) from exc
        except (KeyError, TypeError, ValueError, OSError) as exc:
            raise CommandError("reviewed_manifest_shape_or_private_file_invalid") from exc
        except (ObjectDoesNotExist, PermissionDenied, IntegrityError, ValidationError) as exc:
            raise CommandError("canonical_source_batch_rejected") from exc
        finally:
            reset_rls_context()
        mode = "undo" if options["undo"] and options["apply"] else "apply" if options["apply"] else "dry_run"
        self.stdout.write(
            "reviewed_source: mode=" + mode + " " + " ".join(f"{key}={value}" for key, value in sorted(result.items()))
        )
