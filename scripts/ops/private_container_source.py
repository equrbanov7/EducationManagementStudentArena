"""Transfer a bounded private source as the container's default non-root user."""

import hashlib
import json
import os
import re
import stat
import subprocess
from pathlib import Path

MAX_BYTES = 8 * 1024 * 1024
PATH_PATTERN = (
    r"/tmp/wcu-(?:blank-draft-syllabus|half-pair-hours|farida-slot|source58-qb)-[1-9][0-9]*-[1-9][0-9]*/source\.json"
)

# Code and non-secret identity/digest arguments only; source bytes travel on stdin.
WRITER = r"""
import hashlib,json,os,pathlib,re,stat,sys
created=None
path=pathlib.Path(sys.argv[1])
try:
    expected,size,limit=sys.argv[2],int(sys.argv[3]),int(sys.argv[4])
    uid=os.geteuid()
    if uid==0 or not 0<size<=limit<=8388608:
        raise ValueError()
    if not re.fullmatch(r"/tmp/wcu-(?:blank-draft-syllabus|half-pair-hours|farida-slot|source58-qb)-[1-9][0-9]*-[1-9][0-9]*/source\.json",str(path)):
        raise ValueError()
    parent=path.parent.lstat()
    if not stat.S_ISDIR(parent.st_mode) or parent.st_uid!=uid or stat.S_IMODE(parent.st_mode)!=0o700:
        raise ValueError()
    data=sys.stdin.buffer.read(size+1)
    if len(data)!=size or hashlib.sha256(data).hexdigest()!=expected:
        raise ValueError()
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:
        current=os.fstat(stream.fileno());created=(current.st_dev,current.st_ino)
        if current.st_uid!=uid or stat.S_IMODE(current.st_mode)!=0o600 or current.st_nlink!=1:
            raise ValueError()
        stream.write(data);stream.flush();os.fsync(stream.fileno())
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as stream:
        current=os.fstat(stream.fileno());readback=stream.read(limit+1)
        if (current.st_dev,current.st_ino)!=created or current.st_uid!=uid or stat.S_IMODE(current.st_mode)!=0o600 or current.st_size!=size or hashlib.sha256(readback).hexdigest()!=expected:
            raise ValueError()
    parent_fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(parent_fd)
    finally:os.close(parent_fd)
    print(json.dumps(dict(uid=uid,size=size,mode=384,sha256=expected),sort_keys=True))
except BaseException:
    if created is not None:
        try:
            current=path.lstat()
            if (current.st_dev,current.st_ino)==created:path.unlink()
        except OSError:pass
    print('private_source_write_refused',file=sys.stderr)
    raise SystemExit(2)
"""


def _payload(path, expected_sha):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600 or not 0 < info.st_size <= MAX_BYTES:
            raise ValueError("private_source_file_required")
        payload = source.read(MAX_BYTES + 1)
    if len(payload) != info.st_size or hashlib.sha256(payload).hexdigest() != expected_sha:
        raise ValueError("private_source_sha_or_size_changed")
    return payload


def write_private_source(path, remote_path, expected_sha, *, container):
    """Never use docker cp for0600 payloads: its ownership may differ from APPUID."""
    if (
        not isinstance(remote_path, str)
        or not re.fullmatch(PATH_PATTERN, remote_path)
        or not isinstance(expected_sha, str)
        or not re.fullmatch(r"[a-f0-9]{64}", expected_sha)
        or not isinstance(container, str)
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", container)
    ):
        raise ValueError("fixed_private_source_target_required")
    try:
        payload = _payload(Path(path), expected_sha)
        result = subprocess.run(
            [
                "docker",
                "exec",
                "-i",
                container,
                "python",
                "-c",
                WRITER,
                remote_path,
                expected_sha,
                str(len(payload)),
                str(MAX_BYTES),
            ],
            input=payload,
            capture_output=True,
            timeout=180,
        )
    except FileNotFoundError:
        raise ValueError("private_source_transport_unavailable") from None
    except (OSError, subprocess.SubprocessError):
        raise ValueError("private_source_transport_failed") from None
    if result.returncode or len(result.stdout) > 1024 or len(result.stderr) > 1024:
        raise ValueError("private_source_write_failed")
    try:
        receipt = json.loads(result.stdout)
    except (ValueError, TypeError):
        raise ValueError("private_source_receipt_invalid") from None
    if (
        type(receipt) is not dict
        or set(receipt) != {"uid", "size", "mode", "sha256"}
        or type(receipt["uid"]) is not int
        or receipt["uid"] <= 0
        or type(receipt["size"]) is not int
        or receipt["size"] != len(payload)
        or type(receipt["mode"]) is not int
        or receipt["mode"] != 0o600
        or receipt["sha256"] != expected_sha
    ):
        raise ValueError("private_source_receipt_invalid")
    return receipt
