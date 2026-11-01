"""Fixed English-level metadata/identity evidence, read-only and ciphertext-only."""

from django.core.management.base import BaseCommand, CommandError

from apps.workload.services.english_level_evidence import capture, save_encrypted
from apps.workload.services.four_cell_diagnostics import describe, render
from apps.workload.services.scoped_snapshot import SnapshotError


class Command(BaseCommand):
    def add_arguments(self, parser):
        for key in ("actor", "file", "sha256", "public-key", "output"):
            parser.add_argument("--" + key, required=True)

    def handle(self, *args, **options):
        stage = "capture"
        try:
            snapshot = capture(options["actor"], options["file"], options["sha256"])
            stage = "encrypt"
            sha = save_encrypted(snapshot, options["public_key"], options["output"])
        except SnapshotError as exc:
            self.stderr.write("english_level_diagnostic: " + render(describe(exc, stage)))
            raise CommandError("english_level_evidence_refused") from None
        except Exception as exc:
            self.stderr.write("english_level_diagnostic: " + render(describe(exc, stage)))
            raise CommandError("english_level_evidence_refused") from None
        self.stdout.write(
            f"encrypted_sha256={sha} identities={snapshot['counts']['identity']} offerings={snapshot['counts']['offerings']} placements={snapshot['counts']['placements']}"
        )
