"""Rəy 2026-10-21 (R05): ``config.settings.test`` SQLite ilə AYDIN xəta verir (fail-fast).

Testlər RLS, triggerlər, CHECK-lər və xam SQL miqrasiyalarına söykənir — SQLite-da onlar çaşdırıcı xətalar verirdi.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULES = ("config.settings.base", "config.settings.test")


def _fresh_test_settings(database_url):
    with patch.dict(os.environ, {"DATABASE_URL": database_url, "EMS_TEST_DB_TEMPLATE": ""}, clear=False):
        saved = {name: sys.modules.pop(name, None) for name in MODULES}
        try:
            return importlib.import_module("config.settings.test")
        finally:
            for name, module in saved.items():
                sys.modules.pop(name, None)
                if module is not None:
                    sys.modules[name] = module


@pytest.mark.parametrize("url", ["sqlite:////tmp/emsarena-guard.sqlite3", "sqlite://:memory:"])
def test_sqlite_database_url_fails_fast_with_a_clear_message(url):
    with pytest.raises(ImproperlyConfigured) as excinfo:
        _fresh_test_settings(url)
    message = str(excinfo.value)
    assert "PostgreSQL" in message and "Tests require PostgreSQL" in message
    assert "sqlite" in message


def test_postgres_database_url_is_accepted():
    module = _fresh_test_settings("postgres://user:pw@127.0.0.1:5432/emsarena_guard")
    assert "postgresql" in module.DATABASES["default"]["ENGINE"]


def test_ci_test_jobs_run_on_postgres():
    for name in ("_unit-tests.yml", "_rls-txn-pool.yml", "_js-tests.yml"):
        workflow = (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")
        assert "config.settings.test" in workflow
        assert "DATABASE_URL: postgres://" in workflow
        assert "sqlite" not in workflow.lower()
