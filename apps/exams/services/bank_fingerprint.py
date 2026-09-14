"""SQLite content digest without PostgreSQL StringAgg or nested Concat trees."""

from django.db import connections
from django.db.models import F, Func, TextField


def sqlite_exam_fingerprint(queryset):
    connection = connections[queryset.db]
    fields = (
        "id",
        "order",
        "language",
        "text",
        "options__id",
        "options__label",
        "options__is_correct",
        "options__text",
    )
    rows = (
        queryset.order_by("id", "options__id")
        .annotate(fingerprint_row=Func(*(F(name) for name in fields), function="JSON_ARRAY", output_field=TextField()))
        .values("fingerprint_row")
    )
    sql, params = rows.query.get_compiler(using=queryset.db).as_sql()
    # JSON escapes row separators and preserves field boundaries. Ordering is
    # inside the subquery; GROUP_CONCAT receives a deterministic row stream.
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT MD5(COALESCE(GROUP_CONCAT(\"fingerprint_row\", CHAR(30)), '')) FROM (" + sql + ') AS "digest_rows"',
            params,
        )
        return "sqlite:" + cursor.fetchone()[0]
