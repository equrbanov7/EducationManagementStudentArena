"""Offline private source + authenticated full capture -> hash-pinned executable plan."""

import hashlib
import json
import os
import stat
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.core.serializers.json import DjangoJSONEncoder

from ...reaudit_cells.builder import Builder
from ...reaudit_cells.manifest import MAX_BYTES, SHA, RepairError, require


def private_json(path, checksum, *, max_bytes=MAX_BYTES):
    require(SHA.fullmatch(str(checksum)), "input_hash_required")
    file = Path(path)
    mode = file.lstat().st_mode
    require(stat.S_ISREG(mode) and not mode & 0o077, "private_regular_input_required")
    require(file.stat().st_size <= max_bytes, "input_byte_budget")
    raw = file.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == checksum, "input_hash_changed")
    return json.loads(raw)


class Command(BaseCommand):
    help = "Təzə tam ixrac və mənbə sətirlərindən yalnız lokal məxfi plan hazırlayır."
    requires_system_checks = []

    def add_arguments(self, parser):
        for key in (
            "source-file",
            "source-sha256",
            "current-file",
            "current-sha256",
            "organization-id",
            "period-id",
            "source-system",
            "out",
        ):
            parser.add_argument("--" + key, required=True)

    def handle(self, *args, **options):
        try:
            source = private_json(options["source_file"], options["source_sha256"])
            # The authenticated full-capture producer permits 512 MiB; executable
            # repair plans retain their smaller native 256 MiB contract.
            current = private_json(options["current_file"], options["current_sha256"], max_bytes=512 * 1024 * 1024)
            plan = Builder(
                source=source,
                current=current,
                **{
                    key: options[key]
                    for key in ("organization_id", "period_id", "source_system", "source_sha256", "current_sha256")
                },
            ).build()
            raw = (
                json.dumps(plan, cls=DjangoJSONEncoder, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                + "\n"
            ).encode()
            require(len(raw) <= MAX_BYTES, "executable_manifest_byte_budget")
            path = Path(options["out"])
            require(
                path.parent.is_dir() and not path.parent.stat().st_mode & 0o077, "private_output_directory_required"
            )
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(raw)
            summary = {
                "sha256": hashlib.sha256(raw).hexdigest(),
                "source_rows": len(plan["sources"]),
                "offering_count": len(plan["offering_ids"]),
                "route_count": len(plan["routes"]),
                "inventory_counts": plan["inventory_counts"],
            }
        except RepairError as exc:
            raise CommandError("reaudit_cells_plan_refused:" + str(exc)) from None
        except Exception:
            raise CommandError("reaudit_cells_plan_refused:invalid_private_input") from None
        self.stdout.write(json.dumps(summary, sort_keys=True))
