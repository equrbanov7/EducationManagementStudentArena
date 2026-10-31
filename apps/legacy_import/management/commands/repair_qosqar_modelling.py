"""Qoşqar exact source modelling journal and own syllabus correction: dry-run first, baseline-pinned apply."""

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError

from apps.workload.public import ModellingError, repair_qosqar_modelling
from core.rls_pooling import rls_worker_atomic

from ...services.qosqar_modelling_evidence import load
from ...services.repair_support import RepairContext, establish_rls_scope, resolve_organization


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--org", default="qku")
        parser.add_argument("--source-evidence", required=True)
        parser.add_argument("--actor", required=True)
        parser.add_argument("--expected-baseline", default="")
        parser.add_argument("--undo", action="store_true")
        parser.add_argument("--apply", action="store_true")

    @rls_worker_atomic()
    def handle(self, *args, **options):
        user = get_user_model().objects.filter(username=options["actor"], is_active=True, is_superuser=True).first()
        if not user:
            raise CommandError("active_superadmin_required")
        org = resolve_organization(options["org"])
        establish_rls_scope(RepairContext(org, user, options["apply"], 0))
        try:
            sections, source_sha = load(options["source_evidence"])
            result = repair_qosqar_modelling(
                sections=sections,
                source_sha256=source_sha,
                organization=org,
                user=user,
                apply=options["apply"],
                expected_baseline=options["expected_baseline"],
                undo=options["undo"],
            )
        except ModellingError as exc:
            raise CommandError(str(exc)) from None
        except (ObjectDoesNotExist, ValidationError, DatabaseError):
            raise CommandError("qosqar_modelling_current_scope_conflict") from None
        self.stdout.write("qosqar_modelling: " + " ".join(f"{key}={value}" for key, value in sorted(result.items())))
