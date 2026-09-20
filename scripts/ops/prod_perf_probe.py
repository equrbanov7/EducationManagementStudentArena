"""Prod tətbiq daxili performans + DB zondu (OXU-YALNIZ; sahib 2026-09-21).

`prod_audit.sh` bunu app konteynerində `manage.py shell <` ilə işlədir.
* Verilənlər bazası: ölçü, bağlantı sayı, cache hit ratio, uzun sorğular,
  seq_scan ağır cədvəllər, `pg_stat_statements` varsa ən yavaş 8 sorğu.
* Tətbiq: real superadmin sessiyası ilə (force_login — parol yoxdur) 12 səhifəyə
  GET; sorğu sayı + müddət (DEBUG yalnız bu prosesdə açılır, cavablar atılır).
Heç bir yazı yoxdur; POST edilmir.
"""

import os
import time

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection, reset_queries
from django.test import Client
from django.urls import reverse

HOST = os.environ.get("PROBE_HOST") or "127.0.0.1"


def q(sql, params=None):
    with connection.cursor() as cur:
        cur.execute(sql, params or [])
        return cur.fetchall()


print("== DB")
try:
    print("size:", q("SELECT pg_size_pretty(pg_database_size(current_database()))")[0][0])
    print(
        "connections:",
        q("SELECT count(*), sum((state='active')::int) FROM pg_stat_activity WHERE datname=current_database()")[0],
    )
    hit = q(
        "SELECT round(100*sum(blks_hit)/nullif(sum(blks_hit)+sum(blks_read),0),2) FROM pg_stat_database WHERE datname=current_database()"
    )[0][0]
    print("cache hit ratio %:", hit, "(<95 → shared_buffers/index problemi)")
    long_q = q(
        "SELECT pid, now()-query_start AS age, left(query,90) FROM pg_stat_activity "
        "WHERE state='active' AND now()-query_start > interval '5 seconds' AND datname=current_database() ORDER BY age DESC LIMIT 5"
    )
    print("long-running (>5s):", long_q or "yoxdur")
    seq = q(
        "SELECT relname, seq_scan, idx_scan, n_live_tup FROM pg_stat_user_tables "
        "WHERE n_live_tup > 20000 AND seq_scan > idx_scan ORDER BY seq_scan DESC LIMIT 8"
    )
    print("seq_scan > idx_scan (böyük cədvəllər):")
    for row in seq:
        print("   ", row)
    if not seq:
        print("    yoxdur")
    dead = q(
        "SELECT relname, n_dead_tup, n_live_tup, last_autovacuum FROM pg_stat_user_tables "
        "WHERE n_dead_tup > 50000 ORDER BY n_dead_tup DESC LIMIT 5"
    )
    print("dead tuples > 50k:", dead or "yoxdur")
    try:
        top = q(
            "SELECT round(mean_exec_time::numeric,1), calls, left(query,110) FROM pg_stat_statements "
            "ORDER BY mean_exec_time DESC LIMIT 8"
        )
        print("pg_stat_statements — ən yavaş (orta ms, çağırış, sorğu):")
        for row in top:
            print("   ", row)
    except Exception as exc:  # noqa: BLE001
        print("pg_stat_statements yoxdur:", str(exc).splitlines()[0][:80])
except Exception as exc:  # noqa: BLE001
    print("DB zondu xətası:", exc)

print()
print("== Tətbiq (superadmin sessiyası, GET, sorğu sayı / ms)")
User = get_user_model()
user = User.objects.filter(is_superuser=True, is_active=True).order_by("id").first()
if user is None:
    print("aktiv superadmin yoxdur — tətbiq zondu ötürüldü")
else:
    settings.DEBUG = True
    settings.ALLOWED_HOSTS = ["*"]
    client = Client()
    client.force_login(user)
    pages = [
        reverse("accounts:profile"),
        reverse("accounts:profile") + "?section=my-exams",
        reverse("accounts:profile") + "?section=groups-registry",
        reverse("accounts:profile") + "?section=people-teachers",
        reverse("accounts:profile") + "?section=student-registry",
        reverse("accounts:profile") + "?section=workload-overview",
        reverse("accounts:profile") + "?section=my-subjects",
        reverse("registrar:journal_list"),
    ]
    try:
        from apps.registrar.models import CourseOffering

        off = CourseOffering.objects.filter(is_active=True, period__is_current=True).order_by("-created_at").first()
        if off:
            pages.append(reverse("registrar:journal_detail", args=[off.pk]))
    except Exception as exc:  # noqa: BLE001
        print("journal_detail seçilmədi:", exc)
    try:
        from apps.exams.models import Exam

        exam = Exam.objects.filter(is_deleted=False, author=user).order_by("-created_at").first()
        if exam:
            pages.append(reverse("exams:teacher_exam_detail", args=[exam.slug]))
            pages.append(reverse("exams:teacher_exam_results", args=[exam.slug]))
    except Exception as exc:  # noqa: BLE001
        print("exam seçilmədi:", exc)
    print(f"{'status':>6} {'q':>4} {'ms':>6}  url")
    slow = []
    for url in pages:
        reset_queries()
        t0 = time.time()
        try:
            resp = client.get(url, HTTP_HOST=HOST, follow=False)
            status = resp.status_code
        except Exception as exc:  # noqa: BLE001
            status = f"ERR {type(exc).__name__}"
        ms = int((time.time() - t0) * 1000)
        n = len(connection.queries)
        print(f"{str(status):>6} {n:>4} {ms:>6}  {url}")
        if n > 80 or ms > 1500:
            slow.append((url, n, ms))
    print()
    print("⚠️ yavaş/sorğu-ağır (q>80 və ya >1500ms):", slow or "yoxdur")
