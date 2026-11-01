"""Encrypted read-only syllabus fingerprints for one existing pinned journal-root batch."""

import re

from django.core.management.base import BaseCommand, CommandError

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
        try:
            snapshot = capture(options["actor"], options["batch"])
            sha = save_encrypted(snapshot, options["public_key"], options["output"])
        except SnapshotError as exc:
            code = str(exc)
            raise CommandError(code if re.fullmatch(r"[a-z_]+", code) else "syllabus_content_export_refused") from None
        except Exception:
            raise CommandError("syllabus_content_export_refused") from None
        self.stdout.write(
            f"encrypted_sha256={sha} roots={snapshot['counts']['roots']} versions={snapshot['counts']['versions']}"
        )
