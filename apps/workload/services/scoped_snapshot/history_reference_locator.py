"""One field serialization and UUID-token scan, retaining literal substring semantics."""

import re

from django.db import connection
from django.db.models import BooleanField, Q
from django.db.models.expressions import RawSQL

UUID = r"[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}"
MAX_REFERENCE_BYTES = 1024 * 1024


def reference_locator(table, *, insensitive_ids, literal_ids=(), source_points=()):
    insensitive, literal = set(map(str, insensitive_ids)), set(map(str, literal_ids))
    points = sorted(set(map(str, source_points)))
    if any(not point.isdigit() for point in points):
        raise ValueError("history_numeric_source_points_required")
    if sum(len(value.encode()) for value in insensitive | literal | set(points)) > MAX_REFERENCE_BYTES:
        raise ValueError("history_reference_byte_budget")
    uuid_insensitive = sorted(value.lower() for value in insensitive if re.fullmatch(UUID, value))
    uuid_literal = sorted(value for value in literal if re.fullmatch(UUID, value))
    other_insensitive = sorted(value for value in insensitive if not re.fullmatch(UUID, value))
    other_literal = sorted(value for value in literal if not re.fullmatch(UUID, value))
    table = connection.ops.quote_name(table)
    point_pattern = "(^|[^0-9])(" + "|".join(points) + ")([^0-9]|$)" if points else "(?!)"
    # The materialized, correlated projection detoasts/casts each JSON field
    # once. Keep fields separate: no match can cross JSON-field boundaries.
    sql = f"""EXISTS (
        WITH body AS MATERIALIZED (
            SELECT ARRAY[{table}.changes::text, {table}.old_values::text,
                         {table}.new_values::text] AS fields
        )
        SELECT 1 FROM body CROSS JOIN LATERAL unnest(body.fields) AS field(value)
        WHERE field.value ~ %s
           OR EXISTS (SELECT 1 FROM regexp_matches(field.value, %s, 'g') AS token
                      WHERE lower(token[1]) IN (SELECT unnest(%s::text[]))
                         OR token[1] IN (SELECT unnest(%s::text[])))
           OR EXISTS (SELECT 1 FROM unnest(%s::text[]) AS needle
                      WHERE strpos(upper(field.value), upper(needle)) > 0)
           OR EXISTS (SELECT 1 FROM unnest(%s::text[]) AS needle
                      WHERE strpos(field.value, needle) > 0)
    )"""
    params = [point_pattern, "(" + UUID + ")", uuid_insensitive, uuid_literal, other_insensitive, other_literal]
    return Q(resource_id__in=insensitive | literal) | Q(RawSQL(sql, params, output_field=BooleanField()))
