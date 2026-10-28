"""Read-only WCU2026/27 allowlisted workload export, encrypted before disk."""

from django.core.management.base import BaseCommand, CommandError

from apps.workload.services.scoped_snapshot import SnapshotError, capture, save_encrypted


class Command(BaseCommand):
    help = "WCU2026/27 dərs yükü metadata ixracı; yalnız şifrəli fayl, DB yazısı yoxdur."

    def add_arguments(self, parser):
        parser.add_argument("--actor", required=True)
        parser.add_argument("--public-key", required=True)
        parser.add_argument("--output", required=True)

    def handle(self, *args, **options):
        try:
            snapshot = capture(options["actor"])
            digest = save_encrypted(snapshot, options["public_key"], options["output"])
        except (SnapshotError, OSError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            f"encrypted_sha256={digest} tasks={len(snapshot['data']['tasks'])} rows={len(snapshot['data']['rows'])}"
        )
