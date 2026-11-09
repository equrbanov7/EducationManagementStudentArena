"""Fixed current-period final/appeal audit. No mutation arguments or write path."""

import json

from django.core.management.base import BaseCommand, CommandError

from apps.exams.services.reaudit_final_results import audit

REFUSALS = frozenset(
    {
        "final_audit_fixed_organization",
        "final_audit_active_tenant_superuser",
        "final_audit_current_period_changed",
        "final_audit_fresh_postgresql_transaction",
        "final_audit_readonly_lost",
        "final_audit_execution_budget",
        "final_audit_attempt_budget",
        "final_audit_row_budget",
    }
)


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--actor", required=True)

    def handle(self, *args, **options):
        try:
            result = audit(options["actor"])
        except Exception as exc:
            code = str(exc)
            raise CommandError(code if code in REFUSALS else "final_audit_refused") from None
        self.stdout.write("reaudit_finals: " + json.dumps(result, sort_keys=True))
