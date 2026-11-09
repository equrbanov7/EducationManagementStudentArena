"""Read-only legacy timetable metadata profile; no persons, credentials or links exported."""

import datetime
import hashlib
import json
from pathlib import Path

from read_sources import legacy, select

QUERIES = {
    "transaction": "SELECT @@tx_read_only AS readonly, @@tx_isolation AS isolation_level",
    "columns": "SELECT COLUMN_NAME, DATA_TYPE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='ders_cedveli' ORDER BY ORDINAL_POSITION",
    "summary": "SELECT COUNT(*) AS n, MIN(added_date) AS first_added, MAX(added_date) AS last_added, SUM(from_date IS NULL OR TRIM(from_date)='') AS empty_from, SUM(to_date IS NULL OR TRIM(to_date)='') AS empty_to FROM ders_cedveli",
    "applicability_ranges": "SELECT from_date, to_date, COUNT(*) AS n FROM ders_cedveli GROUP BY from_date,to_date ORDER BY n DESC",
    "lesson_kinds": "SELECT sem_muh, COUNT(*) AS n FROM ders_cedveli GROUP BY sem_muh ORDER BY sem_muh",
    "weeks": "SELECT alt_or_ust_hefte, COUNT(*) AS n FROM ders_cedveli GROUP BY alt_or_ust_hefte ORDER BY alt_or_ust_hefte",
    "clock_ranges": "SELECT start_datetime,end_datetime,COUNT(*) AS n FROM ders_cedveli GROUP BY start_datetime,end_datetime ORDER BY n DESC",
}


def run():
    with legacy() as connection:
        rows = {key: select(connection, sql) for key, sql in QUERIES.items()}
    result = {
        "format": "legacy-timetable-profile/1",
        "captured_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source": "ems-legacy-delta-src/myedu_new.ders_cedveli",
        "source_authority": "legacy source only; current applicability not established",
        "queries": QUERIES,
        "results": rows,
        "limitations": [
            "added_date is insertion time, not timetable applicability",
            "empty from_date/to_date cannot establish 2026/2027 validity",
            "no production ScheduleSlot rows or current official schedule in this profile",
        ],
    }
    output = Path(__file__).with_suffix(".json")
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n")
    print(
        json.dumps(
            {
                "output": output.name,
                "rows": rows["summary"][0]["n"],
                "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            }
        )
    )


if __name__ == "__main__":
    run()
