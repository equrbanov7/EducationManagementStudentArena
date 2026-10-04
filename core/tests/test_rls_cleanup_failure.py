"""Failed request cleanup discards tenant-bearing connections without masking errors."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.db import InterfaceError

import pytest

from core import rls


def test_cleanup_does_not_reopen_an_unused_connection():
    conn = SimpleNamespace(vendor="postgresql", connection=None, close=Mock())
    with patch.object(rls, "connection", conn), patch.object(rls, "_set_rls_settings") as reset:
        rls.reset_rls_context(only_if_connection_open=True)
    reset.assert_not_called()
    conn.close.assert_not_called()


def test_cleanup_discards_a_connection_already_closed_by_driver():
    conn = SimpleNamespace(vendor="postgresql", connection=SimpleNamespace(closed=1), close=Mock())
    with patch.object(rls, "connection", conn), patch.object(rls, "_set_rls_settings") as reset:
        rls.reset_rls_context(only_if_connection_open=True)
    reset.assert_not_called()
    conn.close.assert_called_once()


@pytest.mark.parametrize("cleanup", [True, False])
def test_reset_failure_always_discards_connection_and_explicit_reset_still_raises(cleanup):
    conn = SimpleNamespace(vendor="postgresql", connection=SimpleNamespace(closed=0), close=Mock())
    with (
        patch.object(rls, "connection", conn),
        patch.object(rls, "_set_rls_settings", side_effect=InterfaceError("connection lost")),
    ):
        if cleanup:
            rls.reset_rls_context(only_if_connection_open=True)
        else:
            with pytest.raises(InterfaceError, match="connection lost"):
                rls.reset_rls_context()
    conn.close.assert_called_once()
