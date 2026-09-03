"""Validate legacy source custody and integrity without writing to the database."""

import json

from django.core.management.base import BaseCommand, CommandError

from apps.legacy_import.services.preflight import (
    LegacySourcePreflightError,
    inspect_legacy_source,
)


class Command(BaseCommand):
    help = "Run a strictly read-only custody and integrity preflight on a SQL snapshot."
    requires_system_checks = []
    requires_migrations_checks = False

    def add_arguments(self, parser):
        parser.add_argument("--source", required=True)
        parser.add_argument("--expected-sha256", required=True)
        parser.add_argument("--expected-size-bytes", required=True, type=int)
        parser.add_argument("--expected-table-count", required=True, type=int)

    def handle(self, *args, **options):
        try:
            result = inspect_legacy_source(
                source=options["source"],
                expected_sha256=options["expected_sha256"],
                expected_size_bytes=options["expected_size_bytes"],
                expected_table_count=options["expected_table_count"],
            )
        except LegacySourcePreflightError as exc:
            raise CommandError(f"Legacy source preflight failed ({exc.code}).") from None

        self.stdout.write(json.dumps(result.to_safe_dict(), sort_keys=True))
