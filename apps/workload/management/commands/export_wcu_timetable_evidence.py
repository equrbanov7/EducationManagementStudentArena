"""Fixed reviewed timetable roots only; encrypted metadata, no student cells or writes."""

from django.core.management.base import BaseCommand, CommandError

from ...services.timetable_evidence.capture import capture, save_encrypted
from ...services.timetable_evidence.spec import BATCHES


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--actor", required=True)
        parser.add_argument("--batch", required=True, choices=BATCHES)
        parser.add_argument("--public-key", required=True)
        parser.add_argument("--output", required=True)

    def handle(self, *args, **options):
        try:
            payload = capture(options["actor"], options["batch"])
            sha = save_encrypted(payload, options["public_key"], options["output"])
        except Exception:
            raise CommandError("fixed_timetable_evidence_export_refused") from None
        self.stdout.write(f"encrypted_sha256={sha} roots={len(payload['selection'])}")
