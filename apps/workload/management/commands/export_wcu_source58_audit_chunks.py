"""Fixed Source58 audit proof, ciphertext only on disk and stdout digest only."""

from django.core.management.base import BaseCommand, CommandError

from ...services.source58_audit_diagnostic import capture


class Command(BaseCommand):
    def add_arguments(self, parser):
        for name in ("actor", "public-key", "output"):
            parser.add_argument("--" + name, required=True)

    def handle(self, *args, **options):
        try:
            sha = capture(options["actor"], options["public_key"], options["output"])
        except Exception:
            raise CommandError("source58_audit_diagnostic_refused") from None
        self.stdout.write("encrypted_sha256=" + sha)
