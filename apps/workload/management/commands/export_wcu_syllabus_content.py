"""Encrypted read-only syllabus fingerprints for one existing pinned journal-root batch."""

from django.core.management.base import BaseCommand, CommandError

from apps.workload.services.four_cell_diagnostics import describe, render
from apps.workload.services.scoped_snapshot import SnapshotError
from apps.workload.services.syllabus_content_export import capture, save_encrypted


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument("--actor", required=True)
        parser.add_argument("--batch", required=True)
        parser.add_argument("--public-key", required=True)
        parser.add_argument("--output", required=True)

    def handle(self, *args, **options):
        stage = "capture"
        try:
            snapshot = capture(options["actor"], options["batch"])
            stage = "encrypt"
            sha = save_encrypted(snapshot, options["public_key"], options["output"])
        except Exception as exc:
            fields = describe(exc, stage)
            self.stderr.write("syllabus_content_diagnostic: " + render(fields))
            code = fields["guard"] if isinstance(exc, SnapshotError) else "unclassified"
            raise CommandError(code if code != "unclassified" else "syllabus_content_export_refused") from None
        self.stdout.write(
            f"encrypted_sha256={sha} roots={snapshot['counts']['roots']} versions={snapshot['counts']['versions']}"
        )
