"""Independent reconciliation CLI Django settings qaldırmadan import olunmalıdır."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_reconcile_collect_import_is_django_settings_free():
    root = Path(__file__).resolve().parents[3]
    clean_env = os.environ.copy()
    clean_env.pop("DJANGO_SETTINGS_MODULE", None)
    command = (
        "from django.conf import settings; "
        "assert not settings.configured; "
        "from scripts.legacy_reconcile.collect import CellElection; "
        "assert not settings.configured; "
        "assert CellElection(expected_rows=1).candidate_buckets == 0"
    )
    result = subprocess.run(
        [sys.executable, "-c", command],
        cwd=root,
        env=clean_env,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
