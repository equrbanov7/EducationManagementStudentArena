"""Read-only, fixed qku evidence; encrypted before disk, no credential logging."""

import json

from django.core.management.base import BaseCommand, CommandError

from ...services.reaudit_snapshot import capture
from ...services.reaudit_snapshot.diagnostics import PREFIX, safe_failure


class Command(BaseCommand):
    help = "QKU təkrar auditinin tam cari məlumatlarını şifrəli hissələrə çıxarır (yalnız oxu)."

    def add_arguments(self, parser):
        parser.add_argument("--actor", required=True)
        parser.add_argument("--public-key", required=True)
        parser.add_argument("--output-dir", required=True)
        parser.add_argument(
            "--scope",
            choices=("full", "core"),
            default="full",
            help="full = tarixi 78 cədvəl; core = yalnız identity/map/xana/düzəliş/yük/sillabus başlıqları",
        )

    def handle(self, *args, **options):
        diagnostic = {}
        try:
            result = capture(
                options["actor"],
                options["public_key"],
                options["output_dir"],
                scope=options["scope"],
                diagnostic=diagnostic,
            )
        except Exception as exc:
            self.stderr.write(PREFIX + json.dumps(safe_failure(exc, diagnostic), sort_keys=True))
            raise CommandError("reaudit_snapshot_failed") from None
        self.stdout.write(json.dumps(result, sort_keys=True))
