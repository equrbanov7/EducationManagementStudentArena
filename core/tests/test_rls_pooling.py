"""RLSTransactionGuard üçün control-flow testləri (Faza 2 / Mərhələ 3B).

DB tələb etmir: guard məntiqini mock connection/execute ilə yoxlayır. Tam
inteqrasiya (PostgreSQL + transaction pooling) ayrıca staging testləri tələb edir
(bax: docs/FAZA2_3B_TRANSACTION_POOLING.md).
"""

from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import override_settings

import core.rls_pooling as rls_pooling
from core.rls_pooling import RLSTransactionGuard, reset_txn_flags, rls_worker_atomic


def _ctx(conn):
    return {"connection": conn}


def test_guard_noop_on_non_postgres():
    conn = SimpleNamespace(vendor="sqlite", in_atomic_block=True)
    execute = Mock(return_value="RESULT")
    guard = RLSTransactionGuard(user_id=1, org_id=2, bypass=False)

    out = guard(execute, "SELECT 1", [], False, _ctx(conn))

    assert out == "RESULT"
    # Yalnız əsl sorğu icra olunur, set_config YOX.
    execute.assert_called_once_with("SELECT 1", [], False, _ctx(conn))


def test_guard_noop_when_not_in_atomic_block():
    conn = SimpleNamespace(vendor="postgresql", in_atomic_block=False)
    execute = Mock(return_value="R")
    guard = RLSTransactionGuard(user_id=1, org_id=2, bypass=False)

    guard(execute, "SELECT 1", [], False, _ctx(conn))

    execute.assert_called_once()


def test_guard_applies_set_local_first_for_tenant():
    conn = SimpleNamespace(vendor="postgresql", in_atomic_block=True)
    execute = Mock(return_value="R")
    guard = RLSTransactionGuard(user_id=5, org_id=7, bypass=False)

    guard(execute, "SELECT 42", ["p"], False, _ctx(conn))

    # İki çağırış: əvvəl set_config SELECT, sonra əsl sorğu.
    assert execute.call_count == 2
    first_sql, first_params = execute.call_args_list[0].args[0], execute.call_args_list[0].args[1]
    assert first_sql.startswith("SELECT set_config(")
    # SET LOCAL → set_config-in 3-cü arqumenti birbaşa SQL-də `true`.
    assert "set_config(%s, %s, true)" in first_sql
    assert first_params == [
        "app.current_user_id",
        "5",
        "app.bypass_rls",
        "off",
        "app.current_org_id",
        "7",
    ]
    # İkinci çağırış əsl sorğudur.
    assert execute.call_args_list[1].args[0] == "SELECT 42"
    assert conn._rls_txn_applied is True


def test_guard_bypass_sets_user_and_bypass_only():
    conn = SimpleNamespace(vendor="postgresql", in_atomic_block=True)
    execute = Mock(return_value="R")
    guard = RLSTransactionGuard(user_id=9, org_id=None, bypass=True)

    guard(execute, "SELECT 1", [], False, _ctx(conn))

    first_params = execute.call_args_list[0].args[1]
    # bypass yolunda tenant qoyulmur; yalnız user + bypass=on.
    assert first_params == ["app.current_user_id", "9", "app.bypass_rls", "on"]


def test_guard_applies_once_per_transaction():
    conn = SimpleNamespace(vendor="postgresql", in_atomic_block=True)
    execute = Mock(return_value="R")
    guard = RLSTransactionGuard(user_id=1, org_id=2, bypass=False)

    guard(execute, "SELECT a", [], False, _ctx(conn))
    guard(execute, "SELECT b", [], False, _ctx(conn))

    # Birinci sorğuda set_config + əsl; ikincidə yalnız əsl (artıq tətbiq olunub).
    assert execute.call_count == 3


def test_guard_reentrancy_guard_blocks_recursion():
    conn = SimpleNamespace(vendor="postgresql", in_atomic_block=True, _rls_applying=True)
    execute = Mock(return_value="R")
    guard = RLSTransactionGuard(user_id=1, org_id=2, bypass=False)

    guard(execute, "SELECT 1", [], False, _ctx(conn))

    # _rls_applying True olduğu üçün set_config tətbiq olunmur.
    execute.assert_called_once_with("SELECT 1", [], False, _ctx(conn))


def test_reset_txn_flags_clears_state():
    conn = SimpleNamespace(_rls_txn_applied=True, _rls_applying=True)
    reset_txn_flags(conn)
    assert conn._rls_txn_applied is False
    assert conn._rls_applying is False


def test_settings_items_anonymous_user_uses_empty_sentinels():
    guard = RLSTransactionGuard(user_id=None, org_id=None, bypass=False)
    items = dict(guard._settings_items())
    assert items["app.current_user_id"] == ""
    assert items["app.current_org_id"] == ""
    assert items["app.bypass_rls"] == "off"


@override_settings(RLS_TRANSACTION_SCOPED=True)
def test_worker_atomic_wraps_in_transaction_when_flag_on():
    with patch.object(rls_pooling.transaction, "atomic") as m_atomic:
        with rls_worker_atomic():
            pass
    m_atomic.assert_called_once()


@override_settings(RLS_TRANSACTION_SCOPED=False)
def test_worker_atomic_is_noop_when_flag_off():
    with patch.object(rls_pooling.transaction, "atomic") as m_atomic:
        with rls_worker_atomic():
            pass
    m_atomic.assert_not_called()
