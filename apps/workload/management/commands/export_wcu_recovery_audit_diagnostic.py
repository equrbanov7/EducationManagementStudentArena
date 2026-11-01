"""Encrypted fixed recovery audit metadata, including oversized rows without raw bodies."""

from django.core.management.base import BaseCommand, CommandError

from apps.workload.services.four_cell_diagnostics import describe, render
from apps.workload.services.recovery_audit_diagnostic import capture
from apps.workload.services.syllabus_content_export import save_encrypted


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--actor", required=True)
        parser.add_argument("--public-key", required=True)
        parser.add_argument("--output", required=True)

    def handle(self, *args, **options):
        try:
            payload = capture(options["actor"])
            sha = save_encrypted(payload, options["public_key"], options["output"])
        except Exception as exc:
            self.stderr.write("four_cell_history_diagnostic: " + render(describe(exc, "capture")))
            raise CommandError("fixed_recovery_audit_diagnostic_refused") from None
        self.stdout.write(f"encrypted_sha256={sha}")
