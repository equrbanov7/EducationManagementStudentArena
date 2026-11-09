"""Source J-V4 winner order and cutoff semantics; zero is never treated as blank."""

import datetime as dt
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from .manifest import CUTOFF, digest


def minute(value):
    if isinstance(value, dt.timedelta):
        seconds = int(value.total_seconds())
        return f"{seconds // 3600:02}:{seconds % 3600 // 60:02}" if 0 <= seconds < 86400 else ""
    text = str(value or "")
    try:
        return dt.time.fromisoformat(text).strftime("%H:%M")
    except ValueError:
        return ""


def kind(row):
    if row.get("lab") == 1:
        return "lab"
    if row.get("lab") not in (None, 0):
        return "unknown"
    return {1: "lecture", 2: "lab", 0: "seminar", 3: "seminar"}.get(row.get("sem_muh"), "unknown")


def calendar_date(row):
    try:
        month = int(row["month_id"])
        if str(row["month_id"]) != f"{month:02}" or not 1 <= month <= 12:
            return None
        return dt.date(2026 if month >= 8 else 2027, month, int(row["day_number"]))
    except (TypeError, ValueError):
        return None


def numeric(value):
    if value is None or isinstance(value, bool) or not str(value).strip():
        return None
    try:
        parsed = Decimal(str(value).strip())
        return parsed if parsed.is_finite() and parsed >= 0 else None
    except InvalidOperation:
        return None


def rows(source):
    best, windows = {}, defaultdict(list)
    for row in source.get("excuse_windows", []):
        start, end = str(row["allowed_date_start"])[:10], str(row["allowed_date_end"])[:10]
        if start <= end:
            windows[str(row["student_id"])].append((start, end))
    for raw in source["points"]:
        row = {**raw, "time": minute(raw["time"])}
        key = row["journal_uniqid"], row["month_id"], str(row["day_number"]), str(row["student_id"]), row["time"]
        rank = int(row["update_counter"] or 0), str(row["updated_at"] or ""), int(row["id"])
        if key not in best or rank > best[key][0]:
            best[key] = rank, row
    for _, raw in sorted(best.values(), key=lambda pair: int(pair[1]["id"])):
        date, score = calendar_date(raw), numeric(raw["point"])
        token = str(raw["point"] if raw["point"] is not None else "").strip().lower()
        added = str(raw.get("added_date") or "")[:10]
        if date is None and score is None:
            continue
        if date is not None and date > CUTOFF or date is None and added and added > CUTOFF.isoformat():
            continue
        row = {
            "id": str(raw["id"]),
            "legacy_student_id": str(raw["student_id"]),
            "legacy_journal_uniqid": raw["journal_uniqid"],
            "source_row_sha256": digest(raw),
            "route_keys": [],
            "candidate_offering_ids": [],
        }
        if date is None:
            row.update(kind="component", component_code=str(raw["month_id"]), added_date=added, score=str(score))
            if not added:
                row["hold_reason"] = "component_source_recorded_date_unknown"
        elif score is not None:
            row.update(
                kind="grade",
                score=str(score),
                source_date=date.isoformat(),
                source_time=raw["time"],
                source_kind=kind(raw),
            )
            if score > 10 or score != score.quantize(Decimal("0.01")):
                row["hold_reason"] = "source_numeric_scale_requires_review"
        else:
            excused = raw.get("excusable") == 1 or any(
                a <= date.isoformat() <= b for a, b in windows[str(raw["student_id"])]
            )
            status = {"ie": "present", "qb": "excused" if excused else "absent"}.get(token, "unknown")
            row.update(
                kind="attendance",
                score=None,
                status=status,
                certain=status != "unknown",
                source_date=date.isoformat(),
                source_time=raw["time"],
                source_kind=kind(raw),
            )
            row["source_blank"] = not token
        yield row
