"""Encrypted-only reviewed fixed partition audit; no arbitrary IDs or changed limits."""

import re

from django.core.management.base import BaseCommand, CommandError

from apps.workload.services.chair_cells_fixed_parts import capture, save_encrypted
from apps.workload.services.scoped_snapshot import SnapshotError


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument("--actor", required=True)
        parser.add_argument("--part", required=True)
        parser.add_argument("--public-key", required=True)
        parser.add_argument("--output", required=True)

    def handle(self, *args, **options):
        try:
            payload = capture(options["actor"], options["part"])
            digest = save_encrypted(payload, options["public_key"], options["output"])
        except SnapshotError as exc:
            code = str(exc)
            raise CommandError(code if re.fullmatch(r"[a-z_]+", code) else "journal_part_export_refused") from None
        except Exception:
            raise CommandError("journal_part_export_refused") from None
        self.stdout.write(
            f"encrypted_sha256={digest} roots=10 offerings={payload['counts']['offerings']} marks={payload['counts']['marks']}"
        )
