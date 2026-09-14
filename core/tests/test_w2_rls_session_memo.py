"""2026-09-14 — RLS sessiya-səviyyəli GUC yaddaşı (perf auditi F-07).

Hər kabinet səhifəsi ~10 `set_config` + 5 `current_setting` round-trip edirdi
(əsasən `bypass_rls()`-in oxu→on→bərpa üçlüyü). Yaddaş eyni DB sessiyasında
eyni dəyərin təkrar yazılmasını/oxunmasını atlayır; atomic blok içində (SET
LOCAL) və `RLS_TRANSACTION_SCOPED` rejimində söndürülür.

`TransactionTestCase` — test gövdəsi atomic blokda deyil, yəni yaddaş yolu
həqiqətən işləyir (adi `TestCase` hər şeyi tranzaksiyaya alır).
"""

from django.db import connection, transaction
from django.test import TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext

import pytest

from core import rls


def _db_value(name):
    with connection.cursor() as cur:
        cur.execute("SELECT current_setting(%s, true)", [name])
        return cur.fetchone()[0] or ""


@pytest.mark.postgres
class RlsSessionMemoTest(TransactionTestCase):
    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL GUC")
        rls.reset_rls_context()

    def test_repeated_tenant_set_hits_the_database_once(self):
        rls.set_rls_tenant("11111111-1111-1111-1111-111111111111")
        with CaptureQueriesContext(connection) as ctx:
            rls.set_rls_tenant("11111111-1111-1111-1111-111111111111")
            rls.set_rls_tenant("11111111-1111-1111-1111-111111111111")
        self.assertEqual(len(ctx.captured_queries), 0)
        self.assertEqual(_db_value("app.current_org_id"), "11111111-1111-1111-1111-111111111111")

        with CaptureQueriesContext(connection) as ctx:
            rls.set_rls_tenant("22222222-2222-2222-2222-222222222222")
        self.assertEqual(len(ctx.captured_queries), 1)
        self.assertEqual(_db_value("app.current_org_id"), "22222222-2222-2222-2222-222222222222")

    def test_nested_bypass_costs_nothing_and_restores_previous_value(self):
        rls.set_rls_bypass(False)
        with CaptureQueriesContext(connection) as ctx:
            with rls.bypass_rls():
                self.assertEqual(_db_value("app.bypass_rls"), "on")
                with CaptureQueriesContext(connection) as inner:
                    with rls.bypass_rls():
                        pass
                self.assertEqual(len(inner.captured_queries), 0, "daxili bypass heç bir sorğu etmir")
        # xarici: «on» + «off» — əvvəlki dəyər üçün current_setting oxunmur (yaddaşdadır)
        set_configs = [q for q in ctx.captured_queries if "set_config" in q["sql"]]
        reads = [q for q in ctx.captured_queries if "current_setting" in q["sql"] and "set_config" not in q["sql"]]
        self.assertEqual(len(set_configs), 2)
        # tək oxu bu testin öz `_db_value` çağırışıdır — kod özü current_setting oxumur
        self.assertEqual(len(reads), 1)
        self.assertEqual(_db_value("app.bypass_rls"), "off")

    def test_set_local_inside_atomic_never_poisons_the_session_memo(self):
        rls.set_rls_tenant("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        with transaction.atomic():
            rls.set_rls_tenant("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")  # SET LOCAL
            self.assertEqual(rls._get_rls_setting("app.current_org_id"), "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
        # blokdan sonra sessiya dəyəri qayıdır — yaddaş və DB razılaşır
        self.assertEqual(rls._get_rls_setting("app.current_org_id"), "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        self.assertEqual(_db_value("app.current_org_id"), "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    def test_session_level_write_inside_rolled_back_transaction_is_forgotten(self):
        rls.set_rls_tenant("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        try:
            with transaction.atomic():
                rls.set_rls_tenant("cccccccc-cccc-cccc-cccc-cccccccccccc", local=False)
                raise RuntimeError("rollback")
        except RuntimeError:
            pass
        # PostgreSQL rollback sessiya SET-ini də geri alır; yaddaş bunu bilmir → açar
        # unudulur, növbəti oxu DB-yə gedir və həqiqi dəyəri (aaaa…) qaytarır.
        with CaptureQueriesContext(connection) as ctx:
            value = rls._get_rls_setting("app.current_org_id")
        self.assertEqual(len(ctx.captured_queries), 1, "unudulmuş açar DB-dən oxunur")
        self.assertEqual(value, "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        self.assertEqual(value, _db_value("app.current_org_id"))

    def test_reopened_connection_starts_with_an_empty_memo(self):
        rls.set_rls_tenant("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        connection.close()
        with CaptureQueriesContext(connection) as ctx:
            rls.set_rls_tenant("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        self.assertEqual(len(ctx.captured_queries), 1)
        self.assertEqual(_db_value("app.current_org_id"), "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    @override_settings(RLS_TRANSACTION_SCOPED=True)
    def test_transaction_scoped_mode_disables_the_memo(self):
        rls.set_rls_tenant("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        with CaptureQueriesContext(connection) as ctx:
            rls.set_rls_tenant("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        self.assertEqual(len(ctx.captured_queries), 1)
