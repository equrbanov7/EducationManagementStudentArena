"""Emit a complete PII-free PK inventory for the fixed 81-table source plan."""

import argparse
import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.legacy_import.services.mariadb_gateway import (
    MariaDBSourceGatewayError,
    build_configured_mariadb_source_factory,
    load_mariadb_source_config,
)
from apps.legacy_import.services.pk_inventory import (
    MAX_PK_INVENTORY_ROWS,
    LegacyPKInventoryError,
    inventory_legacy_primary_keys,
    validate_source_snapshot_sha256,
)
from apps.legacy_import.services.pk_inventory_contracts import (
    DEFAULT_PK_BATCH_SIZE,
    MAX_PK_BATCH_SIZE,
)
from apps.legacy_import.services.table_plan import LegacyTablePlanError


def _bounded_integer(*, code: str, minimum: int, maximum: int):
    def parse(value: str) -> int:
        if not value.isascii() or not value.isdecimal():
            raise argparse.ArgumentTypeError(code)
        parsed = int(value, 10)
        if not minimum <= parsed <= maximum:
            raise argparse.ArgumentTypeError(code)
        return parsed

    return parse


class Command(BaseCommand):
    help = "Inventory integer PK aggregates for the fixed legacy source plan without target writes."
    requires_system_checks = []
    requires_migrations_checks = False

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            default=DEFAULT_PK_BATCH_SIZE,
            type=_bounded_integer(
                code="legacy_pk_inventory_batch_size_invalid",
                minimum=1,
                maximum=MAX_PK_BATCH_SIZE,
            ),
        )
        parser.add_argument(
            "--max-rows",
            type=_bounded_integer(
                code="legacy_pk_inventory_max_rows_invalid",
                minimum=1,
                maximum=MAX_PK_INVENTORY_ROWS,
            ),
            help="Fail before connecting when this cap is below the fixed plan total.",
        )

    def handle(self, *args, **options):
        try:
            if getattr(settings, "LEGACY_MARIADB_SOURCE_ATTEST_ENABLED", False) is not True:
                load_mariadb_source_config(settings)
            source_snapshot_sha256 = validate_source_snapshot_sha256(
                getattr(settings, "LEGACY_MARIADB_SOURCE_SNAPSHOT_SHA256", None)
            )
            config = load_mariadb_source_config(settings)
            connection_factory = build_configured_mariadb_source_factory(config)
            report = inventory_legacy_primary_keys(
                connection_factory=connection_factory,
                source_snapshot_sha256=source_snapshot_sha256,
                batch_size=options["batch_size"],
                max_rows=options.get("max_rows"),
            )
        except (MariaDBSourceGatewayError, LegacyPKInventoryError, LegacyTablePlanError) as exc:
            raise CommandError(exc.code) from None
        except Exception:
            raise CommandError("legacy_pk_inventory_failed") from None

        self.stdout.write(json.dumps(report, ensure_ascii=True, separators=(",", ":"), sort_keys=True))
