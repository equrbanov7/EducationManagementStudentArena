"""Bounded reviewed payloads, written by APPUID without docker-cp ownership drift."""

import base64
import gzip
import hashlib
import io
import json
import re
import subprocess

LIMIT = 128 * 1024 * 1024
PLAN_LIMITS = {"cells": 256 * 1024 * 1024, "syllabi": 20_000_000, "structure": 1024 * 1024}
WRITER = r"""
import hashlib,os,pathlib,re,stat,sys
path=pathlib.Path(sys.argv[1]); expected=sys.argv[2]; size=int(sys.argv[3])
if not re.fullmatch(r'/tmp/ems-reaudit-op-[1-9][0-9]*-[1-9][0-9]*/(?:plan|authority)\.json',str(path)):raise ValueError('path')
parent=path.parent.lstat()
if os.geteuid()==0 or parent.st_uid!=os.geteuid() or stat.S_IMODE(parent.st_mode)!=0o700:raise ValueError('owner')
if not 0<size<=268435456:raise ValueError('size')
data=sys.stdin.buffer.read(size+1)
if len(data)!=size or hashlib.sha256(data).hexdigest()!=expected:raise ValueError('digest')
with os.fdopen(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600),'wb') as stream:
    stream.write(data);stream.flush();os.fsync(stream.fileno())
print(expected)
"""


def unpack(path, operation):
    with gzip.open(path, "rb") as stream:
        raw = stream.read(LIMIT + 1)
    if len(raw) > LIMIT:
        raise ValueError("bundle_budget")
    value = json.loads(raw)
    keys = {"format", "operation", "plan", "plan_sha256", "authority", "authority_sha256", "offering_ids"}
    compressed = value.get("format") == "reaudit-operation-bundle/2"
    if set(value) != keys | ({"plan_encoding"} if compressed else set()):
        raise ValueError("bundle_contract")
    if (
        value["format"] not in {"reaudit-operation-bundle/1", "reaudit-operation-bundle/2"}
        or value["operation"] != operation
        or operation not in PLAN_LIMITS
        or compressed
        and value["plan_encoding"] != "gzip"
    ):
        raise ValueError("bundle_operation")
    ids = value["offering_ids"]
    if (
        not isinstance(ids, list)
        or len(ids) > 100
        or any(not isinstance(pk, str) or not re.fullmatch(r"[a-f0-9-]{36}", pk) for pk in ids)
    ):
        raise ValueError("bundle_offering_scope")
    for name in ("plan", "authority"):
        data = base64.b64decode(value[name], validate=True)
        limit = PLAN_LIMITS[operation] if name == "plan" else 1024 * 1024
        if name == "plan" and compressed:
            with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
                data = stream.read(limit + 1)
        if len(data) > limit:
            raise ValueError("bundle_native_source_budget")
        if hashlib.sha256(data).hexdigest() != value[name + "_sha256"]:
            raise ValueError("bundle_source_digest")
        value[name] = data
    if not value["plan"]:
        raise ValueError("bundle_plan_required")
    return value


def write(container, remote, data):
    sha = hashlib.sha256(data).hexdigest()
    result = subprocess.run(
        ["docker", "exec", "-i", container, "python", "-c", WRITER, remote, sha, str(len(data))],
        input=data,
        capture_output=True,
        timeout=120,
    )
    if result.returncode or result.stdout.strip() != sha.encode():
        raise ValueError("private_source_write_failed")
    return sha
