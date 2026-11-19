"""«Cari yükə bərpa et» (``/ders-yuku/tarixce/<id>/berpa/``) yavaşlığı — YALNIZ-OXU diaqnostika (2026-11-19).

Heç nə YAZMIR, şəxs məlumatı çap etmir: (1) hazırda kilid gözləyən / 20 s-dən uzun gedən sorğular
(yalnız müddət + sorğunun ilk 140 simvolu, parametrlər ``$n``), (2) ``core.reviewed_graph.graph`` —
bərpanın iki dəfə hesabladığı jurnal qrafının müddəti və cədvəl üzrə sətir sayları.
"""

import time

from django.db import connection

from core.reviewed_graph import graph
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

OFFERING = "bad814fd-a7a5-4e24-8722-6e0d33e9ee13"

with connection.cursor() as cur:
    cur.execute(
        "SELECT pid, state, wait_event_type, wait_event, extract(epoch FROM now() - query_start)::int, "
        "left(regexp_replace(query, '\\s+', ' ', 'g'), 140) FROM pg_stat_activity "
        "WHERE datname = current_database() AND pid <> pg_backend_pid() AND state <> 'idle' "
        "AND (wait_event_type = 'Lock' OR now() - query_start > interval '20 seconds') ORDER BY 5 DESC LIMIT 15"
    )
    rows = cur.fetchall()
print(f"slow_or_waiting_queries: {len(rows)}")
for pid, state, wtype, wevent, secs, query in rows:
    print(f"  pid={pid} state={state} wait={wtype}/{wevent} secs={secs} q={query}")

with connection.cursor() as cur:
    cur.execute(
        "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() AND state = 'idle in transaction' "
        "AND now() - state_change > interval '30 seconds'"
    )
    print(f"idle_in_transaction_over_30s: {cur.fetchone()[0]}")

with rls_worker_atomic(), bypass_rls():
    from apps.registrar.models import CourseOffering

    org_id = CourseOffering.objects.filter(pk=OFFERING).values_list("organization_id", flat=True).first()
    t0 = time.monotonic()
    try:
        result = graph({"registrar.CourseOffering": [OFFERING]}, organization_id=org_id)
        status = "ok"
    except Exception as exc:  # noqa: BLE001 — diaqnostika
        result, status = {}, type(exc).__name__ + ":" + str(exc)[:80]
    elapsed = time.monotonic() - t0
    print(f"graph_status: {status}")
    print(f"graph_seconds: {elapsed:.2f}")
    print(f"graph_total_rows: {sum(map(len, result.values()))}")
    for label, values in sorted(result.items(), key=lambda item: -len(item[1]))[:15]:
        print(f"  {label}: {len(values)}")
