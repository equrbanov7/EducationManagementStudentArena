"""Opt-in local Docker integration; synthetic data, no running app/DB or network."""

import hashlib
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/ops"))
import private_container_source as transport  # noqa: E402

pytestmark = pytest.mark.skipif(
    os.environ.get("EMS_SOURCE_DOCKER_INTEGRATION") != "1",
    reason="Opt-in existing local image only; no pull or production-container access",
)


def docker(*args, **kwargs):
    return subprocess.run(["docker", *args], capture_output=True, check=True, **kwargs)


def test_uid1000_root_owned_0600_failure_then_default_uid_stdin_success(tmp_path):
    # The fixture derives only from an existing local image. COPY creates exactly
    # the ownership failure; all executable commands use final default UID1000.
    base = "emsarena-prod:latest"
    docker("image", "inspect", base)
    identity = uuid.uuid4().hex[:10]
    tag = "ems-private-source-fixture:" + identity
    container = "ems-private-source-fixture-" + identity
    remote = "/tmp/wcu-blank-draft-syllabus-1-1/source.json"
    payload = b'{"synthetic_private_transport_only":true}'
    digest = hashlib.sha256(payload).hexdigest()
    source = tmp_path / "source.json"
    source.write_bytes(payload)
    source.chmod(0o600)
    (tmp_path / "Dockerfile").write_text(
        "FROM " + base + "\nUSER 1000:1000\n"
        "RUN python -c \"import pathlib;pathlib.Path('/tmp/wcu-blank-draft-syllabus-1-1').mkdir(mode=0o700)\"\n"
        "COPY --chown=0:0 --chmod=0600 source.json " + remote + "\n"
    )
    try:
        docker("build", "--pull=false", "--network=none", "-t", tag, str(tmp_path))
        docker(
            "run",
            "--rm",
            "-d",
            "--network",
            "none",
            "--name",
            container,
            "--entrypoint",
            "python",
            tag,
            "-c",
            "import time;time.sleep(180)",
        )
        result = docker(
            "exec",
            container,
            "python",
            "-c",
            "import os,pathlib,sys; p=pathlib.Path(sys.argv[1]);print(os.geteuid(),p.stat().st_uid);\ntry:p.read_bytes()\nexcept PermissionError:print('expected_permission_error')",
            remote,
            text=True,
        )
        assert result.stdout.splitlines() == ["1000 0", "expected_permission_error"]
        docker("exec", container, "python", "-c", "import pathlib,sys;pathlib.Path(sys.argv[1]).unlink()", remote)
        receipt = transport.write_private_source(source, remote, digest, container=container)
        assert receipt == dict(uid=1000, size=len(payload), mode=0o600, sha256=digest)
        # Independent later process mirrors the service's Path.read_bytes call.
        result = docker(
            "exec",
            container,
            "python",
            "-c",
            "import os,stat,pathlib,json,hashlib,sys;p=pathlib.Path(sys.argv[1]);s=p.stat();print(json.dumps(dict(uid=s.st_uid,mode=stat.S_IMODE(s.st_mode),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),reader_uid=os.geteuid())))",
            remote,
            text=True,
        )
        assert json.loads(result.stdout) == dict(uid=1000, reader_uid=1000, mode=0o600, sha256=digest)
        with pytest.raises(ValueError, match="write_failed"):
            transport.write_private_source(source, remote, digest, container=container)
        # Existing data survives O_EXCL refusal; no reparenting or overwrite.
        result = docker(
            "exec",
            container,
            "python",
            "-c",
            "import pathlib,hashlib,sys;print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())",
            remote,
            text=True,
        )
        assert result.stdout.strip() == digest
        docker("exec", container, "python", "-c", "import pathlib,sys;pathlib.Path(sys.argv[1]).unlink()", remote)
        failed = subprocess.run(
            [
                "docker",
                "exec",
                "-i",
                container,
                "python",
                "-c",
                transport.WRITER,
                remote,
                "a" * 64,
                str(len(payload)),
                str(transport.MAX_BYTES),
            ],
            input=payload,
            capture_output=True,
        )
        assert failed.returncode == 2 and b"private_source_write_refused" in failed.stderr
        check = docker(
            "exec",
            container,
            "python",
            "-c",
            "import pathlib,sys;print(pathlib.Path(sys.argv[1]).exists())",
            remote,
            text=True,
        )
        assert check.stdout.strip() == "False"
        # Real post-create failure: force fsync to fail in this one isolated
        # Python process. The UID-owned incomplete source must be unlinked.
        fault = (
            "import os;os.fsync=lambda fd:(_ for _ in ()).throw(OSError('synthetic_disk_failure'))\n" + transport.WRITER
        )
        failed = subprocess.run(
            [
                "docker",
                "exec",
                "-i",
                container,
                "python",
                "-c",
                fault,
                remote,
                digest,
                str(len(payload)),
                str(transport.MAX_BYTES),
            ],
            input=payload,
            capture_output=True,
        )
        assert failed.returncode == 2 and b"private_source_write_refused" in failed.stderr
        assert b"synthetic_disk_failure" not in failed.stderr
        check = docker(
            "exec",
            container,
            "python",
            "-c",
            "import pathlib,sys;print(pathlib.Path(sys.argv[1]).exists())",
            remote,
            text=True,
        )
        assert check.stdout.strip() == "False"
    finally:
        subprocess.run(["docker", "rm", "-f", container], capture_output=True)
        subprocess.run(["docker", "image", "rm", "-f", tag], capture_output=True)
