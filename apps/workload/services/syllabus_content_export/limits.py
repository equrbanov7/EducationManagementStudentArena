"""Bound every DB statement and the total read-only capture, without truncation."""

from contextlib import contextmanager
from time import monotonic

from django.db import connection

from ..scoped_snapshot import SnapshotError

MAX_SECONDS = 120
MAX_QUERIES = 600


@contextmanager
def query_budget():
    deadline, count = monotonic() + MAX_SECONDS, 0

    def enforce(execute, sql, params, many, context):
        nonlocal count
        count += 2
        remaining = int((deadline - monotonic()) * 1000)
        if remaining <= 0 or count > MAX_QUERIES:
            raise SnapshotError("syllabus_query_or_time_budget_exceeded")
        execute("SELECT set_config('statement_timeout', %s, true)", [f"{remaining}ms"], False, context)
        return execute(sql, params, many, context)

    with connection.execute_wrapper(enforce):
        yield
        if monotonic() > deadline:
            raise SnapshotError("syllabus_query_or_time_budget_exceeded")


def bounded(query, limit):
    result = list(query.order_by("pk")[: limit + 1])
    if len(result) > limit:
        raise SnapshotError("syllabus_row_budget_exceeded")
    return result
