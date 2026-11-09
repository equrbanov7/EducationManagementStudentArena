"""Real Linux process tests; run in a networkless, read-only test container on macOS."""

import importlib.util
import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path
from uuid import uuid4

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/ops/reaudit_command_runner.py"
spec = importlib.util.spec_from_file_location("reviewed_runner", SCRIPT)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

WRAPPER = """
import importlib.util,sys,time
from pathlib import Path
spec=importlib.util.spec_from_file_location('runner',sys.argv[1]);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.GRACE=.2
if len(sys.argv)>5 and sys.argv[5]=='wait-ready':
    class ReadyProcess(m.subprocess.Popen):
        def communicate(self,*args,**kwargs):
            until=time.monotonic()+20
            while not (Path(sys.argv[2])/'pids.json').exists():
                if self.poll() is not None or time.monotonic()>=until:
                    raise AssertionError('Synthetic process tree readiness failed')
                time.sleep(.02)
            return super().communicate(*args,**kwargs)
    m.subprocess.Popen=ReadyProcess
try:
    code,out,err=m.execute(Path(sys.argv[2]),[sys.executable,'-c',sys.argv[3]],deadline=float(sys.argv[4]))
    sys.stdout.buffer.write(out);sys.stderr.buffer.write(err);sys.exit(code)
except ValueError as exc:
    sys.stderr.write(str(exc))
    sys.exit(124)
"""


@unittest.skipUnless(sys.platform == "linux" and hasattr(os, "pidfd_open"), "Requires real Linux proc/pidfd")
class RunnerProcessTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path("/tmp") / f"ems-reaudit-op-{os.getpid()}-{int(uuid4().hex[:8], 16) + 1}"
        runner.prepare(self.folder)
        self.processes = []

    def tearDown(self):
        for process in self.processes:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
        if self.folder.exists():
            runner.cleanup(self.folder)

    def launch(self, code, deadline, *, wait_ready=False):
        process = subprocess.Popen(
            [sys.executable, "-c", WRAPPER, str(SCRIPT), str(self.folder), code, str(deadline)]
            + (["wait-ready"] if wait_ready else []),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.processes.append(process)
        return process

    def descendants(self, *, startup_delay=0):
        ready = self.folder / "descendant-ready"
        child = (
            "import signal,time;from pathlib import Path;"
            "signal.signal(signal.SIGTERM,signal.SIG_IGN);"
            f"Path({str(ready)!r}).touch();time.sleep(30)"
        )
        return (
            "import json,os,signal,subprocess,sys,time\n"
            "from pathlib import Path\n"
            "signal.signal(signal.SIGTERM,signal.SIG_IGN)\n"
            f"time.sleep({startup_delay!r})\n"
            f"p=subprocess.Popen([sys.executable,'-c',{child!r}])\n"
            "until=time.monotonic()+20\n"
            f"while not Path({str(ready)!r}).exists():\n"
            "    if p.poll() is not None or time.monotonic()>=until:\n"
            "        raise AssertionError('Synthetic descendant readiness failed')\n"
            "    time.sleep(.02)\n"
            f"pending=Path({str(self.folder / 'pids.next')!r})\n"
            "pending.write_text(json.dumps([os.getpid(),p.pid]))\n"
            f"pending.replace({str(self.folder / 'pids.json')!r})\n"
            "time.sleep(30)"
        )

    def await_pids(self):
        until = time.monotonic() + 20
        target = self.folder / "pids.json"
        while time.monotonic() < until:
            if target.exists():
                return json.loads(target.read_text())
            time.sleep(0.02)
        self.fail("Synthetic child did not start")

    def assert_dead(self, pids):
        for pid in pids:
            info = runner.identity(pid)
            self.assertTrue(info is None or info["state"] == "Z", f"Process still active: {pid}")

    def test_success_and_verified_cleanup(self):
        process = self.launch("print('synthetic success')", 5)
        stdout, stderr = process.communicate(timeout=10)
        self.assertEqual((process.returncode, stdout, stderr), (0, b"synthetic success\n", b""))
        self.assertEqual(runner.read(self.folder)["status"], "finished")
        runner.cleanup(self.folder)
        self.assertFalse(self.folder.exists())

    def test_timeout_kills_term_ignoring_parent_and_descendant(self):
        # Startup deliberately exceeds the real deadline. Only this test's
        # communicate wrapper waits until both SIGTERM handlers are installed.
        process = self.launch(self.descendants(startup_delay=1), 0.6, wait_ready=True)
        pids = self.await_pids()
        stdout, stderr = process.communicate(timeout=10)
        self.assertEqual(process.returncode, 124)
        self.assertEqual((stdout, stderr), (b"", b"reaudit_native_deadline_expired_receipt_unknown"))
        self.assert_dead(pids)
        runner.cleanup(self.folder)
        self.assertFalse(self.folder.exists())

    def test_cancellation_cleanup_kills_supervisor_and_child_tree(self):
        process = self.launch(self.descendants(), 25)
        pids = self.await_pids()
        runner.cleanup(self.folder)
        process.communicate(timeout=5)
        self.assertIsNotNone(process.returncode)
        self.assert_dead(pids + [process.pid])
        self.assertFalse(self.folder.exists())

    def test_cleanup_refuses_reused_or_unrelated_pid_and_preserves_source(self):
        process = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(30)"], start_new_session=True)
        self.processes.append(process)
        expected = runner.identity(process.pid)
        expected["start"] += 1
        private = self.folder / "plan.json"
        private.write_text("synthetic private input")
        with runner.locked(self.folder):
            runner.store(self.folder, {"status": "running", "child": None, "supervisor": expected, "token": None})
        with self.assertRaisesRegex(ValueError, "process_identity"):
            runner.cleanup(self.folder)
        self.assertIsNone(process.poll())
        self.assertTrue(private.exists())
        # Reset only synthetic state for test teardown after proving no signal was sent.
        with runner.locked(self.folder):
            runner.store(self.folder, {"status": "cancelled", "child": None, "supervisor": None, "token": None})

    def test_cancelled_intent_cannot_start_and_fixed_cli_rejects_shell(self):
        with runner.locked(self.folder):
            runner.store(self.folder, {"status": "cancelled", "child": None, "supervisor": None, "token": None})
        with self.assertRaisesRegex(ValueError, "not_prepared"):
            runner.execute(self.folder, [sys.executable, "-c", "raise RuntimeError('must not run')"])
        with self.assertRaisesRegex(ValueError, "fixed_command"):
            runner.native_args("shell", ["-c", "anything"])
        with self.assertRaisesRegex(ValueError, "fixed_arguments"):
            runner.native_args("repair_reaudit_journal_structure", ["--settings", "alternate"])

    def test_supervisor_death_before_identity_commit_never_starts_native_child(self):
        marker = self.folder / "must-not-exist"
        child_pid = self.folder / "gated-child.json"
        setup = (
            "original=m.store\n"
            "def crash(path,record):\n"
            "    if record['status']=='running':\n"
            f"        Path({str(child_pid)!r}).write_text(str(record['child']['pid']))\n"
            "        import os,signal;os.kill(os.getpid(),signal.SIGKILL)\n"
            "    return original(path,record)\n"
            "m.store=crash\n"
        )
        wrapper = WRAPPER.replace("m.GRACE=.2\n", "m.GRACE=.2\n" + setup)
        process = subprocess.Popen(
            [
                sys.executable,
                "-c",
                wrapper,
                str(SCRIPT),
                str(self.folder),
                f"open({str(marker)!r},'w').write('incorrect native start')",
                "5",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.processes.append(process)
        process.communicate(timeout=5)
        self.assertLess(process.returncode, 0)
        self.assertFalse(marker.exists())
        pid = int(child_pid.read_text())
        until = time.monotonic() + 2
        while time.monotonic() < until:
            info = runner.identity(pid)
            if info is None or info["state"] == "Z":
                break
            time.sleep(0.02)
        self.assert_dead([pid])
        runner.cleanup(self.folder)
        self.assertFalse(self.folder.exists())


if __name__ == "__main__":
    unittest.main()
