"""Encrypted-only fixed-tenant journal audit; pinned batch selection, no arbitrary IDs."""

import re

from django.core.management.base import BaseCommand, CommandError

from apps.workload.services.chair_cells_export import capture, save_encrypted
from apps.workload.services.scoped_snapshot import SnapshotError


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
            safe_code = code if re.fullmatch(r"[a-z_]+", code) else "journal_cells_export_refused"
            raise CommandError(safe_code) from None
        except Exception:
            # Privacy boundary: SQL/crypto/filesystem failures must not print values
            # or paths, even if the management command is run with --traceback.
            raise CommandError("journal_cells_export_refused") from None
        self.stdout.write(
            f"encrypted_sha256={sha} offerings={snapshot['counts']['offerings']} marks={snapshot['counts']['marks']}"
        )
