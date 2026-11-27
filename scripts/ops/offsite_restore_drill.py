"""Restore an encrypted synthetic PostgreSQL + media snapshot from a dedicated drill repository."""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]


@contextmanager
def scratch_database():
    name = "ems_drill_" + uuid.uuid4().hex
    # Only databases successfully created by this invocation are eligible for cleanup.
    subprocess.run(["createdb", "--maintenance-db=postgres", "--template=template0", name], check=True)
    try:
        yield name
    finally:
        subprocess.run(["dropdb", "--maintenance-db=postgres", name], check=True)


def fixture(action, database, media, marker):
    user = quote(os.environ["PGUSER"], safe="")
    password = quote(os.environ.get("PGPASSWORD", ""), safe="")
    port = int(os.environ.get("PGPORT", 5432))
    env = dict(
        os.environ,
        DATABASE_URL=f"postgresql://{user}:{password}@127.0.0.1:{port}/{database}",
        DJANGO_SETTINGS_MODULE="config.settings.test",
        PYTHON_DOTENV_DISABLED="1",
    )
    if action == "seed":
        subprocess.run(
            [sys.executable, "manage.py", "migrate", "--noinput", "--verbosity=0"], cwd=ROOT, env=env, check=True
        )
    subprocess.run(
        [sys.executable, "-m", "scripts.ops.restore_drill_fixture", action, str(media), marker],
        cwd=ROOT,
        env=env,
        check=True,
    )


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run():
    if os.environ.get("PGHOST") != "127.0.0.1":
        raise ValueError("Use the runner's disposable PostgreSQL service on 127.0.0.1")
    if not os.environ.get("RESTIC_REPOSITORY", "").startswith(("s3:", "rest:")):
        raise ValueError("Configure a dedicated remote S3 or REST drill repository")
    marker = uuid.uuid4().hex
    with tempfile.TemporaryDirectory(prefix="ems-drill-backup-") as source:
        source = Path(source)
        with scratch_database() as database:
            fixture("seed", database, source / "media", marker)
            dump = source / "database.dump"
            subprocess.run(["pg_dump", "--format=custom", "--no-owner", "--no-acl", "-f", dump, database], check=True)
        dump_hash = digest(dump)
        (media_path,) = (source / "media").rglob(f"{marker}.txt")
        media_relative = media_path.relative_to(source)
        media_hash = digest(media_path)
        result = subprocess.run(
            ["restic", "backup", "--json", "--tag", "emsarena-restore-drill", "database.dump", "media"],
            cwd=source,
            text=True,
            stdout=subprocess.PIPE,
            check=True,
        )
        (summary,) = (
            item for item in map(json.loads, result.stdout.splitlines()) if item.get("message_type") == "summary"
        )
        snapshot = summary["snapshot_id"]

    # At this point the original database and both input files have been removed.
    with tempfile.TemporaryDirectory(prefix="ems-drill-restore-") as target:
        target = Path(target)
        subprocess.run(["restic", "restore", snapshot, "--target", target, "--verify"], check=True)
        dump = target / "database.dump"
        if digest(dump) != dump_hash or digest(target / media_relative) != media_hash:
            raise ValueError("Restored dump or attachment checksum differs from the original")
        with scratch_database() as restored:
            subprocess.run(
                ["pg_restore", "--single-transaction", "--no-owner", "--no-acl", "--dbname", restored, dump], check=True
            )
            fixture("verify", restored, target / "media", marker)
    print(f"Verified snapshot {snapshot}, dump SHA-256 {dump_hash}, attachment SHA-256 {media_hash}", flush=True)


if __name__ == "__main__":
    run()
