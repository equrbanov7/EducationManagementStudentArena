"""MR-000234 sabit plan saatı düzəlişi: dry-run baseline verir, yazı yalnız həmin baseline ilə; undo var."""

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError

from core.rls import apply_rls_request_context
from core.rls_pooling import rls_worker_atomic

from ...services.mr234_plan_hours import ORG, MR234Error, repair_mr234_plan_hours


class Command(BaseCommand):
    help = "MR-234: Yeganə Hidayətovanın «Xarici dil-2» sillabusuna 935 BM ing yükünün plan saatı (seminar 75)."

    def add_arguments(self, parser):
        parser.add_argument("--actor", required=True)
        parser.add_argument("--expected-baseline", default="")
        parser.add_argument("--undo", action="store_true")
        parser.add_argument("--apply", action="store_true")

    @rls_worker_atomic()
    def handle(self, *args, **options):
        from django.apps import apps

        # Sabit WCU dosyesi — tenant bypass yoxdur.
        apply_rls_request_context(user_id=None, org_id=ORG, bypass=False, local=True)
        org = apps.get_model("organizations.Organization").objects.get(pk=ORG)
        user = get_user_model().objects.filter(username=options["actor"], is_active=True, is_superuser=True).first()
        if user is None:
            raise CommandError("active_superadmin_required")
        apply_rls_request_context(user_id=user.pk, org_id=org.pk, bypass=False, local=True)
        try:
            result = repair_mr234_plan_hours(
                organization=org,
                user=user,
                apply=options["apply"],
                expected_baseline=options["expected_baseline"],
                undo=options["undo"],
            )
        except MR234Error as exc:
            raise CommandError(str(exc)) from None
        except (ObjectDoesNotExist, ValidationError, DatabaseError):
            raise CommandError("mr234_scope_conflict") from None
        self.stdout.write("mr234_plan: " + " ".join(f"{key}={value}" for key, value in sorted(result.items())))
