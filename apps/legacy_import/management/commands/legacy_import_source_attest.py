"""Emit a sanitized read-only attestation of the audited legacy source."""

import argparse
import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.legacy_import.services.mariadb_gateway import (
    MariaDBSourceGatewayError,
    build_configured_mariadb_source_factory,
    load_mariadb_source_config,
)
from apps.legacy_import.services.source_attestation import (
    MAX_ATTESTATION_ROWS,
    LegacySourceAttestationError,
    attest_legacy_identity_source,
)


def _max_rows(value: str) -> int:
    if not value.isascii() or not value.isdecimal():
        raise argparse.ArgumentTypeError("legacy_source_attestation_max_rows_invalid")
    parsed = int(value, 10)
    if not 1 <= parsed <= MAX_ATTESTATION_ROWS:
        raise argparse.ArgumentTypeError("legacy_source_attestation_max_rows_invalid")
    return parsed


class Command(BaseCommand):
    help = "Attest the fixed students/workers legacy source contracts without emitting source data."
    requires_system_checks = []
    requires_migrations_checks = False

    def add_arguments(self, parser):
        parser.add_argument(
            "--max-rows",
            type=_max_rows,
            help="Fail if either audited projection exceeds this complete-count limit.",
        )

    def handle(self, *args, **options):
        try:
            config = load_mariadb_source_config(settings)
            connection_factory = build_configured_mariadb_source_factory(config)
            report = attest_legacy_identity_source(
                connection_factory=connection_factory,
                max_rows=options.get("max_rows"),
            )
        except (MariaDBSourceGatewayError, LegacySourceAttestationError) as exc:
            raise CommandError(exc.code) from None
        except Exception:
            raise CommandError("legacy_source_attestation_failed") from None

        self.stdout.write(json.dumps(report, ensure_ascii=True, separators=(",", ":"), sort_keys=True))
