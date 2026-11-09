"""Read-only, fixed qku evidence; encrypted before disk, no credential logging."""

import json

from django.core.management.base import BaseCommand, CommandError

from ...services.reaudit_snapshot import capture


class Command(BaseCommand):
    help = "QKU təkrar auditinin tam cari məlumatlarını şifrəli hissələrə çıxarır (yalnız oxu)."

    def add_arguments(self, parser):
        parser.add_argument("--actor", required=True)
        parser.add_argument("--public-key", required=True)
        parser.add_argument("--output-dir", required=True)

    def handle(self, *args, **options):
        try:
            result = capture(options["actor"], options["public_key"], options["output_dir"])
        except Exception as exc:
            raise CommandError("reaudit_snapshot_failed:" + type(exc).__name__) from None
        self.stdout.write(json.dumps(result, sort_keys=True))
