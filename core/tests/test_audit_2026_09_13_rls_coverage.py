"""Audit `access` (2026-09-13) F-05 — RLS əhatəsi: hər ``organization_id`` sütunlu
cədvəlin tenant siyasəti OLMALIDIR.

Niyə: ``registrar_guestrosterdocument`` (0069) ``organization_id`` ilə yaradıldı,
amma RLS siyasəti unuduldu — bunu tutan CI testi yox idi, ona görə sürüşdü.
Bu test miqrasiya olunmuş test bazasında ``pg_class``/``pg_policy``-dən oxuyur
(auditorun ``rls_query.sql`` sorğusunun CI versiyası) və bilinən istisnaları
AÇIQ siyahı ilə pinləyir: yeni istisna → test qırılır → qərar şüurlu verilir.
"""

from __future__ import annotations

from django.db import connection

import pytest

pytestmark = pytest.mark.postgres

# ``organization_id`` daşıyıb QƏSDƏN RLS-siz saxlanılan cədvəllər. Hər sətir
# üçün səbəb yazılmalıdır; siyahı boşalana qədər burada qalır.
RLS_EXEMPT_TABLES = {
    # 2026-09-02-dən bilinən, qəsdən: login-öncəsi (auth backend, ilk-giriş
    # middleware) oxunur — tenant konteksti hələ yoxdur. Açıq qərar olaraq
    # qalır (`organizations/migrations/0018` şərhi, `test_rls_platform_logs.py`).
    "accounts_userprofile",
}

# RLS AÇIQ, siyasəti VAR, amma ``FORCE`` yoxdur — yalnız cədvəl sahibi üçün
# bypass; audit `access` §5 P3 qeydi (ayrıca qərar, bu düzəlişin əhatəsi deyil).
FORCE_EXEMPT_TABLES = {
    "accounts_accountactivationevidence",
    "accounts_accountrestoreevidence",
}

_INVENTORY_SQL = """
SELECT c.relname,
       c.relrowsecurity,
       c.relforcerowsecurity,
       (SELECT count(*) FROM pg_policy p WHERE p.polrelid = c.oid) AS policy_count
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relkind = 'r'
  AND EXISTS (
        SELECT 1 FROM pg_attribute a
        WHERE a.attrelid = c.oid AND a.attname = 'organization_id' AND NOT a.attisdropped
  )
ORDER BY c.relname
"""


def _org_tables():
    if connection.vendor != "postgresql":
        pytest.skip("RLS əhatə testi PostgreSQL tələb edir")
    with connection.cursor() as cursor:
        cursor.execute(_INVENTORY_SQL)
        return [
            {"table": name, "rls": bool(rls), "forced": bool(forced), "policies": int(policies)}
            for name, rls, forced, policies in cursor.fetchall()
        ]


@pytest.mark.django_db
def test_every_org_scoped_table_has_rls_policy():
    rows = _org_tables()
    assert rows, "organization_id sütunlu cədvəl tapılmadı — inventar sorğusu səhvdir"

    missing = [r["table"] for r in rows if (not r["rls"] or r["policies"] == 0) and r["table"] not in RLS_EXEMPT_TABLES]
    assert missing == [], f"RLS siyasətsiz tenant cədvəlləri (F-05): {missing}"

    stale_exempt = sorted(t for t in RLS_EXEMPT_TABLES if any(r["table"] == t and r["rls"] for r in rows))
    assert stale_exempt == [], f"İstisna siyahısı köhnəlib — artıq RLS-lidir: {stale_exempt}"


@pytest.mark.django_db
def test_guest_roster_document_is_rls_protected():
    """F-05 — 0074 miqrasiyasının konkret nəticəsi."""
    rows = {r["table"]: r for r in _org_tables()}
    row = rows["registrar_guestrosterdocument"]
    assert row["rls"] and row["forced"] and row["policies"] >= 1, row


@pytest.mark.django_db
def test_rls_tables_are_forced_except_known_pair():
    rows = _org_tables()
    not_forced = sorted(
        r["table"] for r in rows if r["rls"] and not r["forced"] and r["table"] not in FORCE_EXEMPT_TABLES
    )
    assert not_forced == [], f"FORCE ROW LEVEL SECURITY yoxdur: {not_forced}"
    stale = sorted(t for t in FORCE_EXEMPT_TABLES if any(r["table"] == t and r["forced"] for r in rows))
    assert stale == [], f"FORCE istisna siyahısı köhnəlib: {stale}"
