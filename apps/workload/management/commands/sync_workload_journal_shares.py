"""Mövcud jurnallarda cari yük təyinatlarının dar növ paylarını bərpa et; dry-run defolt."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from core.rls import apply_rls_request_context, reset_rls_context
from core.rls_pooling import rls_worker_atomic

from ...services.journal_share_sync import run
from ...services.sbio235_state import RepairError, model
from ...services.tasks import normalize_academic_year


class Command(BaseCommand):
    help = "Bütün kafedralarda yalnız mövcud jurnalın yükə uyğun növ payları; baseline ilə apply."

    def add_arguments(self, parser):
        parser.add_argument("--org", default="qku")
        parser.add_argument("--year", required=True)
        parser.add_argument("--actor", required=True)
        parser.add_argument("--expected-baseline", default="")
        parser.add_argument("--apply", action="store_true")

    @rls_worker_atomic()
    def handle(self, *args, **options):
        user = get_user_model().objects.filter(username=options["actor"], is_active=True, is_superuser=True).first()
        organization = model("organizations.Organization").objects.filter(slug=options["org"], is_active=True).first()
        year = normalize_academic_year(options["year"])
        if not user or not organization or not year:
            raise CommandError("active_superadmin_org_and_year_required")
        apply_rls_request_context(user_id=user.pk, org_id=organization.pk, bypass=False)
        try:
            result = run(
                organization=organization,
                year=year,
                user=user,
                apply=options["apply"],
                expected_baseline=options["expected_baseline"],
            )
        except RepairError as exc:
            raise CommandError(str(exc)) from exc
        finally:
            reset_rls_context()
        mode = "apply" if options["apply"] else "dry_run"
        self.stdout.write(
            "workload_shares: mode=" + mode + " " + " ".join(f"{key}={value}" for key, value in sorted(result.items()))
        )
