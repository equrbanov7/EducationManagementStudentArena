"""Run-specific Linux process supervision; no database access or arbitrary commands."""

import contextlib
import fcntl
import json
import os
import re
import secrets
import shutil
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path

DEADLINE = 780
GRACE = 5
TOKEN = "EMS_REAUDIT_PROCESS_TOKEN"
START_GATE = (
    "import os,sys;fd=int(sys.argv[1]);ready=os.read(fd,1);os.close(fd);"
    "sys.exit(125) if ready!=b'1' else os.execv(sys.argv[2],sys.argv[2:])"
)
COMMANDS = {
    "repair_audit_cells_20261109": {"--actor", "--org", "--file", "--sha256", "--expected-baseline", "--undo"},
    "repair_audit_syllabi_20261109": {
        "--actor",
        "--org",
        "--offering",
        "--source-file",
        "--source-sha256",
        "--baseline",
        "--undo",
    },
    "repair_reaudit_journal_structure": {
        "--actor",
        "--file",
        "--file-sha256",
        "--authority-file",
        "--expected-baseline",
        "--undo",
    },
    "audit_reaudit_final_results_20261109": {"--actor"},
    "inspect_reaudit_duplicate_qb": {"--actor"},
}


def require(condition, code):
    if not condition:
        raise ValueError(code)


def directory(value):
    path = Path(value)
    require(bool(re.fullmatch(r"/tmp/ems-reaudit-op-[1-9][0-9]*-[1-9][0-9]*", str(path))), "runner_path")
    return path


@contextlib.contextmanager
def locked(path):
    info = path.lstat()
    require(
        stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o700,
        "runner_directory_owner",
    )
    fd = os.open(path / "process.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "a+b") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def store(path, value):
    temporary = path / ("process-" + secrets.token_hex(8) + ".next")
    with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), "w") as stream:
        json.dump(value, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path / "process.json")


def read(path):
    target = path / "process.json"
    if not target.exists():
        return {"status": "prepared", "child": None, "supervisor": None, "token": None}
    with os.fdopen(os.open(target, os.O_RDONLY | os.O_NOFOLLOW), "rb") as stream:
        info = os.fstat(stream.fileno())
        require(
            info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o600 and info.st_size <= 4096,
            "runner_state_owner",
        )
        value = json.load(stream)
    require(
        set(value) == {"status", "child", "supervisor", "token"}
        and value["status"] in {"prepared", "running", "finished", "cancelled"},
        "runner_state",
    )
    return value


def identity(pid):
    try:
        root = Path("/proc") / str(pid)
        fields = root.joinpath("stat").read_text().rsplit(") ", 1)[1].split()
        return {
            "pid": pid,
            "uid": root.stat().st_uid,
            "pgid": int(fields[2]),
            "session": int(fields[3]),
            "start": int(fields[19]),
            "state": fields[0],
            "boot": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        }
    except (FileNotFoundError, ProcessLookupError):
        return None


def same(current, expected):
    return current is not None and all(
        current[key] == expected[key] for key in ("pid", "uid", "pgid", "session", "start", "boot")
    )


def members(record):
    child = record["child"]
    if child is None:
        return []
    result = []
    for path in Path("/proc").iterdir():
        if not path.name.isdigit():
            continue
        current = identity(int(path.name))
        if current is None or current["pgid"] != child["pgid"] or current["state"] == "Z":
            continue
        require(
            current["uid"] == child["uid"]
            and current["boot"] == child["boot"]
            and current["session"] == child["session"]
            and current["start"] >= child["start"],
            "runner_process_identity",
        )
        environment = None
        for _ in range(5):
            try:
                environment = path.joinpath("environ").read_bytes().split(b"\0")
                break
            except (FileNotFoundError, ProcessLookupError):
                break
            except PermissionError:
                # Linux makes environ unreadable briefly during exit, before Z.
                time.sleep(0.02)
                current_exit = identity(current["pid"])
                if current_exit is None or current_exit["state"] == "Z":
                    break
        if environment is None:
            current_exit = identity(current["pid"])
            require(current_exit is None or current_exit["state"] == "Z", "runner_environment_unreadable")
            continue
        latest = identity(current["pid"])
        if latest is None or latest["state"] == "Z":
            continue
        require(same(latest, current), "runner_process_identity")
        require((TOKEN + "=" + record["token"]).encode() in environment, "runner_process_token")
        result.append(current)
    return result


def signal_exact(expected, number):
    current = identity(expected["pid"])
    if current is None or current["state"] == "Z":
        return
    require(same(current, expected), "runner_process_identity")
    # pidfd pins the exact Linux process across PID reuse between check and signal.
    try:
        fd = os.pidfd_open(expected["pid"])
    except ProcessLookupError:
        return
    try:
        current = identity(expected["pid"])
        if current is None or current["state"] == "Z":
            return
        require(same(current, expected), "runner_process_identity")
        try:
            signal.pidfd_send_signal(fd, number)
        except ProcessLookupError:
            pass  # Exited after the pinned identity check; no process was signalled.
    finally:
        os.close(fd)


def stop(record, *, supervisor=False):
    for number in (signal.SIGTERM, signal.SIGKILL):
        for current in reversed(members(record)):
            signal_exact(current, number)
        if supervisor and record["supervisor"]:
            signal_exact(record["supervisor"], number)
        until = time.monotonic() + GRACE
        while time.monotonic() < until:
            if number == signal.SIGKILL:
                # Catch a descendant forked during the first signal traversal.
                for current in reversed(members(record)):
                    signal_exact(current, number)
            parent = identity(record["supervisor"]["pid"]) if supervisor and record["supervisor"] else None
            if not members(record) and (parent is None or parent["state"] == "Z"):
                return
            time.sleep(0.05)
    require(not members(record), "runner_stop_unconfirmed")
    if supervisor and record["supervisor"]:
        parent = identity(record["supervisor"]["pid"])
        require(parent is None or parent["state"] == "Z", "runner_stop_unconfirmed")


def prepare(path):
    path.mkdir(mode=0o700, exist_ok=True)
    with locked(path):
        require(not (path / "process.json").exists(), "runner_already_prepared")
        store(path, read(path))


def cleanup(path):
    if not path.exists():
        return
    with locked(path):
        record = read(path)
        store(path, {**record, "status": "cancelled"})
    stop(record, supervisor=True)
    # Never remove source files if identity/termination could not be proved.
    with locked(path):
        require(read(path)["status"] == "cancelled", "runner_cancel_state")
        require(not members(record), "runner_stop_unconfirmed")
        shutil.rmtree(path)


def native_args(name, args):
    require(name in COMMANDS, "runner_fixed_command")
    index = 0
    while index < len(args):
        flag = args[index]
        if flag == "--apply" and name.startswith("repair_"):
            index += 1
            continue
        require(flag in COMMANDS[name] and index + 1 < len(args), "runner_fixed_arguments")
        require(0 < len(args[index + 1]) <= 4096 and not args[index + 1].startswith("--"), "runner_argument_value")
        index += 2
    return [sys.executable, "manage.py", name, *args]


def execute(path, argv, *, deadline=DEADLINE):
    child, record, gate_read, gate_write = None, None, None, None
    try:
        with locked(path):
            require(read(path)["status"] == "prepared", "runner_not_prepared")
            token = secrets.token_hex(32)
            gate_read, gate_write = os.pipe()
            child = subprocess.Popen(
                [sys.executable, "-c", START_GATE, str(gate_read), *argv],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
                env={**os.environ, TOKEN: token},
                pass_fds=(gate_read,),
            )
            os.close(gate_read)
            gate_read = None
            record = {
                "status": "running",
                "child": identity(child.pid),
                "supervisor": identity(os.getpid()),
                "token": token,
            }
            require(record["child"] is not None, "runner_child_identity")
            store(path, record)
            # EOF on supervisor death prevents native execution before durable identity.
            os.write(gate_write, b"1")
            os.close(gate_write)
            gate_write = None
        try:
            stdout, stderr = child.communicate(timeout=deadline)
        except subprocess.TimeoutExpired:
            stop(record)
            child.wait(timeout=GRACE)
            raise ValueError("reaudit_native_deadline_expired_receipt_unknown") from None
        stop(record)  # Also remove descendants surviving a successful parent.
        return child.returncode, stdout, stderr
    finally:
        for descriptor in (gate_read, gate_write):
            if descriptor is not None:
                os.close(descriptor)
        if record is not None:
            stop(record)
            if child is not None:
                child.wait(timeout=GRACE)
            with locked(path):
                current = read(path)
                if current["status"] != "cancelled":
                    store(path, {**record, "status": "finished"})


def main(argv):
    require(len(argv) >= 2, "runner_arguments")
    mode, path = argv[0], directory(argv[1])
    if mode == "prepare" and len(argv) == 2:
        prepare(path)
    elif mode == "cleanup" and len(argv) == 2:
        cleanup(path)
    elif mode == "run" and len(argv) >= 3:
        code, stdout, stderr = execute(path, native_args(argv[2], argv[3:]))
        sys.stdout.buffer.write(stdout)
        sys.stderr.buffer.write(stderr)
        return code
    else:
        raise ValueError("runner_fixed_mode")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception:
        print("reaudit_native_outcome_unknown_inspect_receipt_before_retry", file=sys.stderr)
        sys.exit(2)
