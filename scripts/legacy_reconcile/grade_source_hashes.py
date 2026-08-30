"""Legacy grade source-row hash-lərini MariaDB-dən müstəqil yenidən qur."""

from __future__ import annotations

import datetime
import re

from apps.legacy_import.services.field_contracts import (
    JOURNAL_POINT_ARCHIVE_FIELDS,
    JOURNAL_POINT_FIELDS,
)
from apps.legacy_import.services.legacy_grade_field_contracts import (
    EXAM_ENTRY_EXIT_FIELDS,
    YEKUN_EVIDENCE_FIELDS,
)
from apps.legacy_import.services.rehearsal_contracts import source_row_hash

_NON_GRADE_MONTHS = tuple(f"{month:02d}" for month in range(1, 13)) + ("k1", "k2", "k3", "si")
_NON_GRADE_SQL = ", ".join(f"'{value}'" for value in _NON_GRADE_MONTHS)
_TIME_RE = re.compile(r"(?P<sign>-?)(?P<hours>\d+):(?P<minutes>\d{2}):(?P<seconds>\d{2}(?:\.\d+)?)\Z")

_RAW_QUERIES = {
    YEKUN_EVIDENCE_FIELDS.source_table: """
        SELECT id, student_id, lesson_id, journal_id, girish, imtahanda, yekun,
               group_id, kesr, guzest_girish, level, guzest_artim
          FROM yekun ORDER BY id;
    """,
    JOURNAL_POINT_FIELDS.source_table: f"""
        SELECT id, journal_uniqid, month_id, day_number, student_id, point,
               added_date, time, excusable, why, j_id, lab, sem_muh,
               description, update_counter, updated_at
          FROM journals_dates_points
         WHERE COALESCE(month_id, '') NOT IN ({_NON_GRADE_SQL})
         ORDER BY id;
    """,
    JOURNAL_POINT_ARCHIVE_FIELDS.source_table: f"""
        SELECT id, journal_uniqid, month_id, day_number, student_id, point,
               added_date, time, excusable, why, j_id, lab, sem_muh,
               description, update_counter, updated_at
          FROM journals_dates_points_archive
         WHERE COALESCE(month_id, '') NOT IN ({_NON_GRADE_SQL})
         ORDER BY id;
    """,
    EXAM_ENTRY_EXIT_FIELDS.source_table: """
        SELECT id, student_id, lesson_id, giris_point, cixis_point, type, added_date
          FROM imthngrscxsblr ORDER BY id;
    """,
}


def _nullable(value):
    return None if value in (None, "NULL") else value


def _integer(value):
    value = _nullable(value)
    return None if value is None else int(value)


def _float(value):
    value = _nullable(value)
    return None if value is None else float(value)


def _text(value):
    value = _nullable(value)
    return None if value is None else str(value)


def _datetime(value):
    value = _nullable(value)
    return None if value is None else datetime.datetime.fromisoformat(str(value))


def _timedelta(value):
    value = _nullable(value)
    if value is None:
        return None
    match = _TIME_RE.fullmatch(str(value))
    if match is None:
        raise ValueError("legacy_grade_source_time_invalid")
    seconds = int(match.group("hours")) * 3600 + int(match.group("minutes")) * 60 + float(match.group("seconds"))
    return datetime.timedelta(seconds=-seconds if match.group("sign") else seconds)


def _yekun_row(values):
    converters = (
        _integer,
        _integer,
        _integer,
        _integer,
        _float,
        _float,
        _float,
        _integer,
        _integer,
        _integer,
        _integer,
        _integer,
    )
    return tuple(convert(value) for convert, value in zip(converters, values))


def _point_row(values):
    converters = (
        _integer,
        _text,
        _text,
        _text,
        _integer,
        _text,
        _datetime,
        _timedelta,
        _integer,
        _text,
        _integer,
        _integer,
        _integer,
        _text,
        _integer,
        _datetime,
    )
    return tuple(convert(value) for convert, value in zip(converters, values))


def _attempt_row(values):
    converters = (_integer, _integer, _integer, _integer, _integer, _integer, _datetime)
    return tuple(convert(value) for convert, value in zip(converters, values))


_CONTRACTS = {
    YEKUN_EVIDENCE_FIELDS.source_table: (YEKUN_EVIDENCE_FIELDS, _yekun_row),
    JOURNAL_POINT_FIELDS.source_table: (JOURNAL_POINT_FIELDS, _point_row),
    JOURNAL_POINT_ARCHIVE_FIELDS.source_table: (JOURNAL_POINT_ARCHIVE_FIELDS, _point_row),
    EXAM_ENTRY_EXIT_FIELDS.source_table: (EXAM_ENTRY_EXIT_FIELDS, _attempt_row),
}


def collect_source_grade_hashes(source) -> dict[tuple[str, int], str]:
    """Importer kontraktını təkrar istifadə edib hər source hash-i yenidən hesabla."""

    hashes: dict[tuple[str, int], str] = {}
    for source_table, sql in _RAW_QUERIES.items():
        contract, convert = _CONTRACTS[source_table]
        for raw in source.query(f"{source_table} xam source hash", sql):
            values = convert(raw)
            if len(values) != len(contract.allowed_fields):
                raise ValueError("legacy_grade_source_hash_row_shape_invalid")
            row = dict(zip(contract.allowed_fields, values))
            legacy_pk = int(row["id"])
            key = (source_table, legacy_pk)
            if key in hashes:
                raise ValueError("legacy_grade_source_hash_duplicate")
            hashes[key] = source_row_hash(
                contract=contract,
                legacy_pk=legacy_pk,
                projected_row=row,
            )
    return hashes


__all__ = ["collect_source_grade_hashes"]
