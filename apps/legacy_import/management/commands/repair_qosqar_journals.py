"""One atomic source6591 correction for exactly two reviewed Qoşqar journal pairs."""

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, transaction

from apps.workload.public import JournalsError, repair_qosqar_journals
from core.rls_pooling import rls_worker_atomic

from ...services import qosqar_modelling_evidence
from ...services.repair_support import RepairContext, establish_rls_scope, resolve_organization


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--org", default="qku")
        parser.add_argument("--actor", required=True)
        parser.add_argument("--file", required=True)
        parser.add_argument("--sha256", required=True)
        parser.add_argument("--baseline", default="")
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--undo", action="store_true")

    @rls_worker_atomic()
    @transaction.atomic
    def handle(self, *args, **options):
        user = get_user_model().objects.filter(username=options["actor"], is_active=True, is_superuser=True).first()
        if user is None:
            raise CommandError("active_superadmin_required")
        org = resolve_organization(options["org"])
        establish_rls_scope(RepairContext(org, user, options["apply"], 0))
        try:
            if options["sha256"] != qosqar_modelling_evidence.SOURCE_SHA:
                raise JournalsError("pinned_source_package_changed")
            sections, sha = qosqar_modelling_evidence.load(options["file"])
            result = repair_qosqar_journals(
                organization=org,
                user=user,
                sections=sections,
                source_sha256=sha,
                expected_baseline=options["baseline"],
                apply=options["apply"],
                undo=options["undo"],
            )
        except JournalsError as exc:
            raise CommandError(str(exc)) from None
        except (ObjectDoesNotExist, ValidationError, DatabaseError):
            raise CommandError("qosqar_journals_current_scope_conflict") from None
        except OSError:
            raise CommandError("source_file_unavailable") from None
        if not options["apply"]:
            transaction.set_rollback(True)
        mode = "apply" if options["apply"] else "dry_run"
        self.stdout.write(
            "qosqar_journals: mode=" + mode + " " + " ".join(f"{k}={v}" for k, v in sorted(result.items()))
        )
