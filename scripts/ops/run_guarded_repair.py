"""One repair invocation: stable reads through direct PostgreSQL or PgBouncer.

This file is piped into the existing app container by the reviewed workflow;
no deployed application setting, database default, or other worker is changed.
"""

import os
import re
import sys
import traceback

COMMANDS = {
    "repair_sbio235_workload",
    "repair_233ke_group_alias",
    "repair_cavid_source_batch",
    "repair_si135_legacy_roster",
    "repair_bi_mu536_legacy_roster",
    "repair_tspx_legacy_roster",
    "repair_reviewed_workload_batch",
    "repair_reviewed_journal_content",
    "undo_reviewed_four_cells",
}


def prepare_connection():
    import manage

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", manage.DEFAULT_SETTINGS_MODULE)
    import django
    from django.db import connections, transaction
    from django.db.backends.postgresql.psycopg_any import IsolationLevel

    # Django/psycopg emits BEGIN ISOLATION LEVEL for every transaction. Unlike
    # libpq PGOPTIONS, this is accepted by PgBouncer's startup-parameter gate.
    # Only this short-lived Python process receives this connection option.
    config = connections.databases["default"]
    config["OPTIONS"] = {**config.get("OPTIONS", {}), "isolation_level": IsolationLevel.REPEATABLE_READ}
    django.setup()
    connection = connections["default"]
    if connection.vendor != "postgresql":
        raise RuntimeError("postgresql_required")
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SHOW transaction_isolation")
            isolation = cursor.fetchone()[0]
        if isolation != "repeatable read":
            raise RuntimeError("repeatable_read_required")
    return isolation


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print("CommandError: fixed_repair_command_not_allowed", file=sys.stderr)
        return 2
    try:
        prepare_connection()
    except Exception:  # noqa: BLE001 — never expose connection errors/DSNs.
        print("CommandError: repair_repeatable_read_connection_required", file=sys.stderr)
        return 2
    print("fixed_repair: transaction_isolation=repeatable_read", flush=True)
    from django.core.management import execute_from_command_line
    from django.db import connections

    try:
        execute_from_command_line(["manage.py", *sys.argv[1:]])
    except Exception as exc:  # noqa: BLE001 — expose code locations, never exception values.
        kind = type(exc).__name__.lower()
        if not re.fullmatch(r"[a-z_]+", kind):
            kind = "exception"
        print("CommandError: fixed_repair_unexpected_" + kind, file=sys.stderr)
        # Frame filenames/functions are code metadata, not local values or SQL.
        # Prefer the deepest application frame over a database driver frame.
        frames = traceback.extract_tb(exc.__traceback__)
        local = [frame for frame in frames if "/apps/" in frame.filename or "/core/" in frame.filename]
        if local:
            frame = local[-1]
            module = os.path.basename(frame.filename).removesuffix(".py")
            if re.fullmatch(r"[a-zA-Z0-9_]+", module) and re.fullmatch(r"[a-zA-Z0-9_]+", frame.name):
                print(
                    f"fixed_repair_exception: class={kind} module={module} function={frame.name} line={frame.lineno}",
                    file=sys.stderr,
                )
        return 1
    finally:
        connections.close_all()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
