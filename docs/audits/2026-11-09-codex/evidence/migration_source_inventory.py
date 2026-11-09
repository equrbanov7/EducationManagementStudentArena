"""Exact source table counts in one read-only snapshot; no record content."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from read_sources import legacy, select

HERE = Path(__file__).resolve().parent


def main():
    inventory = []
    with legacy() as connection:
        tables = select(
            connection,
            "SELECT TABLE_NAME,ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME",
        )
        for row in tables:
            table = row["TABLE_NAME"]
            if not re.fullmatch(r"[A-Za-z0-9_]+", table):
                raise ValueError("unexpected_table_identifier")
            query = f"SELECT COUNT(*) AS row_count FROM `{table}`"
            count = select(connection, query)[0]["row_count"]
            inventory.append(
                {
                    "table": table,
                    "engine": row["ENGINE"],
                    "physical_row_count_all_source_scopes": count,
                    "query": query,
                    "current_ems_migrated_count": None,
                    "coverage_status": "Full target-ledger reconciliation required; source count is not missing count.",
                }
            )
    result = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "source_schema": "myedu_new",
        "role": "root@%",
        "readonly": True,
        "tables": inventory,
    }
    (HERE / "migration_source_tables.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {
                "tables": len(inventory),
                "total_physical_rows": sum(r["physical_row_count_all_source_scopes"] for r in inventory),
            }
        )
    )


if __name__ == "__main__":
    main()
