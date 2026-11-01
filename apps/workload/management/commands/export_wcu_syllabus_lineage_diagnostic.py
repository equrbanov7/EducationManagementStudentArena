"""Fixed 027 encrypted metadata-only lineage-cycle evidence; no pointer changes."""

from django.core.management.base import BaseCommand, CommandError

from apps.workload.services.four_cell_diagnostics import describe, render
from apps.workload.services.syllabus_content_export import save_encrypted
from apps.workload.services.syllabus_lineage_diagnostic import capture


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument("--actor", required=True)
        parser.add_argument("--public-key", required=True)
        parser.add_argument("--output", required=True)

    def handle(self, *args, **options):
        stage = "capture"
        try:
            snapshot = capture(options["actor"])
            stage = "encrypt"
            sha = save_encrypted(snapshot, options["public_key"], options["output"])
        except Exception as exc:
            self.stderr.write("syllabus_lineage_diagnostic: " + render(describe(exc, stage)))
            raise CommandError("fixed_syllabus_lineage_diagnostic_refused") from None
        self.stdout.write(
            f"encrypted_sha256={sha} roots={snapshot['counts']['roots']} cycles={snapshot['counts']['cycles']}"
        )
