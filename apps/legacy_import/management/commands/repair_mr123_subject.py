"""MR123 exact current journal correction: dry-run first, baseline-pinned apply."""

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError

from apps.registrar.public import MR123Error, repair_mr123_subject
from core.rls_pooling import rls_worker_atomic

from ...services.repair_support import RepairContext, establish_rls_scope, resolve_organization


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--org", default="qku")
        parser.add_argument("--actor", required=True)
        parser.add_argument("--expected-baseline", default="")
        parser.add_argument("--apply", action="store_true")

    @rls_worker_atomic()
    def handle(self, *args, **options):
        user = get_user_model().objects.filter(username=options["actor"], is_active=True, is_superuser=True).first()
        if not user:
            raise CommandError("active_superadmin_required")
        org = resolve_organization(options["org"])
        establish_rls_scope(RepairContext(org, user, options["apply"], 0))
        try:
            result = repair_mr123_subject(
                organization=org, user=user, apply=options["apply"], expected_baseline=options["expected_baseline"]
            )
        except MR123Error as exc:
            raise CommandError(str(exc)) from None
        except (ObjectDoesNotExist, ValidationError, DatabaseError):
            raise CommandError("mr123_current_scope_conflict") from None
        self.stdout.write("mr123_subject: " + " ".join(f"{key}={value}" for key, value in sorted(result.items())))
