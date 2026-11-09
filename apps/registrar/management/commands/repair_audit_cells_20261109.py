"""Reviewed all-period cells: genuinely read-only default, explicit atomic apply and receipt undo."""

import json

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from core.rls import apply_rls_request_context, reset_rls_context

from ...reaudit_cells.manifest import RepairError, load, require
from ...reaudit_cells.service import run


class Command(BaseCommand):
    help = "21 oktyabr daxil mənbə balları və uyğun boş xanalar; defolt yalnız oxuyur."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True)
        parser.add_argument("--actor", required=True)
        parser.add_argument("--file", required=True)
        parser.add_argument("--sha256", required=True)
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--expected-baseline", default="")
        parser.add_argument("--undo", default="", help="Yalnız bu dəqiq apply receipt-i geri alır.")

    def handle(self, *args, **options):
        try:
            plan = load(options["file"], options["sha256"])
            require(connection.vendor == "postgresql", "postgresql_required")
            require(not connection.in_atomic_block, "fresh_transaction_required")
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, "
                        + ("READ WRITE" if options["apply"] else "READ ONLY")
                    )
                    cursor.execute("SET LOCAL lock_timeout = '5s'")
                actor = (
                    get_user_model()
                    .objects.filter(username=options["actor"], is_active=True, is_superuser=True)
                    .first()
                )
                require(actor is not None, "active_superadmin_required")
                apply_rls_request_context(user_id=actor.pk, org_id=plan["organization_id"], bypass=False, local=True)
                try:
                    organization = (
                        apps.get_model("organizations", "Organization")
                        .objects.filter(pk=plan["organization_id"], slug=options["org"], is_active=True)
                        .first()
                    )
                    require(organization is not None, "tenant_mismatch")
                    result = run(
                        organization=organization,
                        actor=actor,
                        plan=plan,
                        **{key: options[key] for key in ("apply", "expected_baseline", "undo")},
                    )
                finally:
                    reset_rls_context(local=True)
        except RepairError as exc:
            raise CommandError("reaudit_cells_refused:" + str(exc)) from None
        except Exception:
            raise CommandError("reaudit_cells_refused:unexpected_state") from None
        self.stdout.write("reaudit_cells: " + json.dumps(result, sort_keys=True))
