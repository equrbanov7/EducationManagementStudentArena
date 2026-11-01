"""Fixed English-level metadata/identity evidence, read-only and ciphertext-only."""

import re

from django.core.management.base import BaseCommand, CommandError

from apps.workload.services.english_level_evidence import capture, save_encrypted
from apps.workload.services.scoped_snapshot import SnapshotError


class Command(BaseCommand):
    def add_arguments(self, parser):
        for key in ("actor", "file", "sha256", "public-key", "output"):
            parser.add_argument("--" + key, required=True)

    def handle(self, *args, **options):
        try:
            snapshot = capture(options["actor"], options["file"], options["sha256"])
            sha = save_encrypted(snapshot, options["public_key"], options["output"])
        except SnapshotError as exc:
            code = str(exc)
            raise CommandError(code if re.fullmatch(r"[a-z_]+", code) else "english_level_evidence_refused") from None
        except Exception:
            raise CommandError("english_level_evidence_refused") from None
        self.stdout.write(
            f"encrypted_sha256={sha} identities={snapshot['counts']['identity']} offerings={snapshot['counts']['offerings']} placements={snapshot['counts']['placements']}"
        )
