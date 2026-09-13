"""
/health/ `build` açarı — image drift görünürlüyü (Codex audit 2026-09-13, P1-07).

docker/build-info.sh image-ə /app/build-info.json yazır; core/health_build_info
onu bir dəfə oxuyub /health/ cavabına əlavə edir. Burada: fayl var → sha
görünür; fayl yoxdur/zədəlidir → «unknown», endpoint sınmır; yalnız icazəli
açarlar sızır; keş sıfırlanmadan fayl dəyişikliyi görünmür (prosesin ömründə
sabitdir).
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from unittest import mock

from django.test import Client, override_settings

import pytest

from core import health_build_info, views
from core.health_build_info import get_build_info, reset_build_info_cache

ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _fresh_caches():
    reset_build_info_cache()
    views._HEALTH_CACHE.update({"expires_at": 0.0, "payload": None, "status_code": 503})
    yield
    reset_build_info_cache()
    views._HEALTH_CACHE.update({"expires_at": 0.0, "payload": None, "status_code": 503})


def _write(tmp_path: Path, payload) -> Path:
    path = tmp_path / "build-info.json"
    path.write_text(payload if isinstance(payload, str) else json.dumps(payload), encoding="utf-8")
    return path


@override_settings(HEALTH_CHECK_CACHE_SECONDS=0)
def test_health_exposes_build_sha_from_build_info_file(tmp_path):
    path = _write(
        tmp_path, {"sha": "abc1234def", "django": "5.2.17", "python": "3.12.8", "built_at": "2026-09-13T08:00:00+00:00"}
    )
    with mock.patch.dict(os.environ, {"EMS_BUILD_INFO_PATH": str(path)}):
        response = Client().get("/health/")

    assert response.status_code in (200, 207)
    build = response.json()["build"]
    assert build == {
        "sha": "abc1234def",
        "django": "5.2.17",
        "python": "3.12.8",
        "built_at": "2026-09-13T08:00:00+00:00",
    }


@override_settings(HEALTH_CHECK_CACHE_SECONDS=0)
def test_health_reports_unknown_build_when_file_is_missing(tmp_path):
    with mock.patch.dict(os.environ, {"EMS_BUILD_INFO_PATH": str(tmp_path / "nope.json")}):
        response = Client().get("/health/")

    assert response.status_code in (200, 207)
    assert response.json()["build"] == {"sha": "unknown"}


@pytest.mark.parametrize("payload", ["{not json", "[1, 2, 3]", '{"django": ""}'])
def test_corrupt_or_shapeless_build_info_degrades_to_unknown(tmp_path, payload):
    path = _write(tmp_path, payload)
    with mock.patch.dict(os.environ, {"EMS_BUILD_INFO_PATH": str(path)}):
        assert get_build_info() == {"sha": "unknown"}


def test_only_allowlisted_keys_are_exposed(tmp_path):
    path = _write(tmp_path, {"sha": "abc", "django": "5.2", "database_url": "postgres://secret", "extra": 1})
    with mock.patch.dict(os.environ, {"EMS_BUILD_INFO_PATH": str(path)}):
        info = get_build_info()
    assert info == {"sha": "abc", "django": "5.2"}
    assert "database_url" not in json.dumps(info)


def test_build_info_is_read_once_per_process_and_reset_rereads(tmp_path):
    path = _write(tmp_path, {"sha": "first"})
    with mock.patch.dict(os.environ, {"EMS_BUILD_INFO_PATH": str(path)}):
        assert get_build_info()["sha"] == "first"
        _write(tmp_path, {"sha": "second"})
        assert get_build_info()["sha"] == "first", "fayl prosesin ömründə bir dəfə oxunur"
        reset_build_info_cache()
        assert get_build_info()["sha"] == "second"
        # Qaytarılan dict surətdir — çağıran keşi korlaya bilməz.
        get_build_info()["sha"] = "tampered"
        assert get_build_info()["sha"] == "second"


def test_default_path_is_project_root_build_info(settings):
    with mock.patch.dict(os.environ, {"EMS_BUILD_INFO_PATH": ""}):
        assert health_build_info.build_info_path() == Path(settings.BASE_DIR) / "build-info.json"


def test_build_info_script_writes_expected_shape(tmp_path):
    """docker/build-info.sh lokal python ilə də eyni sxemi yazır (image-də eynidir)."""
    out = tmp_path / "bi.json"
    env = {**os.environ, "BUILD_GIT_SHA": "feedface", "DJANGO_SETTINGS_MODULE": ""}
    # Image-də `python` = /usr/local/bin/python; burada venv-in interpretatorunu önə qoyuruq.
    import sys

    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    result = subprocess.run(
        ["sh", str(ROOT / "docker/build-info.sh"), str(out)], capture_output=True, text=True, env=env
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["sha"] == "feedface"
    assert set(data) == {"sha", "django", "python", "built_at"}
    assert data["django"] and data["built_at"].endswith("+00:00")
