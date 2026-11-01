"""Encrypted fixed-four audit/source-claim evidence; no data-write options."""

from django.core.management.base import BaseCommand, CommandError

from ...services.four_cell_diagnostics import describe, render
from ...services.four_cell_history_capture import capture, save_encrypted


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--actor", required=True)
        parser.add_argument("--public-key", required=True)
        parser.add_argument("--output", required=True)

    def handle(self, *args, **options):
        stage = "capture"
        try:
            payload = capture(options["actor"])
            stage = "encrypt"
            sha = save_encrypted(payload, options["public_key"], options["output"])
        except Exception as exc:
            self.stderr.write("four_cell_history_diagnostic: " + render(describe(exc, stage)))
            raise CommandError("four_cell_history_export_refused") from None
        counts = payload["counts"]
        self.stdout.write(
            f"encrypted_sha256={sha} cases=4 audits={counts['four_cell_history_audits']} changes={counts['four_cell_history_changes']}"
        )
