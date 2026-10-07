"""Təhlükəsizlik auditi 2026-10-07 — kod icrası (coding/praktiki imtahan) Docker sandbox-u sərtləşdirilib.

Əvvəl ``docker run`` root kimi, default capability-lərlə, ``no-new-privileges``-siz
və ADSIZ işləyirdi; timeout-da ``subprocess.run`` yalnız ``docker`` CLI-ni öldürürdü —
``--rm`` konteyneri (sonsuz dövr) işləməyə davam edirdi. ``subprocess`` mock-lanır.
"""

from __future__ import annotations

import stat
import subprocess
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from apps.exams.models import CodingSubmission
from apps.exams.services.coding_runtime import execute_code

FILES = [{"name": "main.py", "content": "while True: pass", "language": "python", "is_main": True}]


def _flag(argv, name):
    """``--flag value`` cütünün dəyəri (image-dən ƏVVƏLKİ seçimlər arasında)."""
    values = [argv[index + 1] for index, item in enumerate(argv[:-1]) if item == name]
    assert len(values) == 1, f"{name} tam bir dəfə olmalıdır: {values}"
    return values[0]


@override_settings(CODING_EXECUTION_BACKEND="docker")
@patch("apps.exams.services.coding_runtime.shutil.which", return_value="/usr/bin/docker")
@patch("apps.exams.services.coding_runtime._ensure_docker_image", return_value="")
@patch("apps.exams.services.coding_runtime.subprocess.run")
class DockerSandboxTests(SimpleTestCase):
    def _run(self, run_mock, *, on_run=None, memory_limit_mb=128):
        calls = []

        def fake_run(argv, *args, **kwargs):
            calls.append(list(argv))
            if argv[:2] == ["docker", "info"]:
                return subprocess.CompletedProcess(argv, 0, stdout="27.0", stderr="")
            if argv[:2] == ["docker", "run"] and on_run is not None:
                return on_run(argv, kwargs)
            return subprocess.CompletedProcess(argv, 0, stdout="ok\n", stderr="")

        run_mock.side_effect = fake_run
        result = execute_code(
            language="python", files=FILES, stdin="", time_limit_seconds=2, memory_limit_mb=memory_limit_mb
        )
        return result, calls

    @staticmethod
    def _docker_run(calls):
        runs = [argv for argv in calls if argv[:2] == ["docker", "run"]]
        assert len(runs) == 1
        return runs[0]

    def test_run_argv_is_hardened(self, run_mock, *_mocks):
        result, calls = self._run(run_mock, memory_limit_mb=256)
        argv = self._docker_run(calls)

        self.assertEqual(result.status, CodingSubmission.STATUS_SUCCESS)
        self.assertEqual(_flag(argv, "--user"), "65534:65534")
        self.assertEqual(_flag(argv, "--cap-drop"), "ALL")
        self.assertEqual(_flag(argv, "--security-opt"), "no-new-privileges")
        self.assertEqual(_flag(argv, "--network"), "none")
        self.assertEqual(_flag(argv, "--pids-limit"), "64")
        self.assertEqual(_flag(argv, "--memory"), "256m")
        self.assertEqual(_flag(argv, "--memory-swap"), "256m")
        self.assertEqual(_flag(argv, "--cpus"), "1")
        self.assertIn("--read-only", argv)
        self.assertIn("--rm", argv)
        tmpfs = _flag(argv, "--tmpfs")
        self.assertTrue(tmpfs.startswith("/tmp:"))
        self.assertIn("nosuid", tmpfs)
        self.assertIn("size=128m", tmpfs)
        self.assertTrue(_flag(argv, "-v").endswith(":/workspace:ro"))
        self.assertRegex(_flag(argv, "--name"), r"^emsarena-code-[0-9a-f]{32}$")
        self.assertEqual(_flag(argv, "--label"), "emsarena.code-runner=1")
        # Seçimlər image-dən ƏVVƏL gəlir (sonrakılar konteyner əmrinin arqumentidir).
        self.assertEqual(argv[-3:], ["python:3.12-alpine", "python", "main.py"])

    def test_root_user_override_is_refused(self, run_mock, *_mocks):
        for configured, expected in (("0:0", "65534:65534"), ("root", "65534:65534"), ("1000:1000", "1000:1000")):
            with self.subTest(configured=configured), override_settings(CODING_EXECUTION_DOCKER_USER=configured):
                _result, calls = self._run(run_mock)
                self.assertEqual(_flag(self._docker_run(calls), "--user"), expected)

    def test_workspace_is_readable_by_non_root_user(self, run_mock, *_mocks):
        seen = {}

        def on_run(argv, _kwargs):
            workspace = Path(_flag(argv, "-v").rsplit(":/workspace:ro", 1)[0])
            seen["dir"] = stat.S_IMODE(workspace.stat().st_mode)
            seen["file"] = stat.S_IMODE((workspace / "main.py").stat().st_mode)
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

        self._run(run_mock, on_run=on_run)
        self.assertEqual(seen, {"dir": 0o755, "file": 0o644})

    def test_timeout_kills_and_removes_the_container(self, run_mock, *_mocks):
        def on_run(argv, kwargs):
            raise subprocess.TimeoutExpired(argv, kwargs["timeout"], output=b"partial", stderr=b"")

        result, calls = self._run(run_mock, on_run=on_run)

        name = _flag(self._docker_run(calls), "--name")
        self.assertEqual(result.status, CodingSubmission.STATUS_TIMEOUT)
        self.assertEqual(result.output, "partial")
        self.assertIn(["docker", "rm", "-f", name], calls)

    def test_unexpected_interrupt_still_removes_the_container(self, run_mock, *_mocks):
        class SoftTimeLimit(Exception):
            pass

        def on_run(_argv, _kwargs):
            raise SoftTimeLimit()

        with self.assertRaises(SoftTimeLimit):
            self._run(run_mock, on_run=on_run)
        argvs = [call.args[0] for call in run_mock.call_args_list]
        name = _flag(self._docker_run(argvs), "--name")
        self.assertEqual([argv for argv in argvs if argv[:2] == ["docker", "rm"]], [["docker", "rm", "-f", name]])

    def test_successful_run_does_not_call_docker_rm(self, run_mock, *_mocks):
        _result, calls = self._run(run_mock)
        self.assertFalse([argv for argv in calls if argv[:2] == ["docker", "rm"]])
