"""Exercise cache maintenance with a local lock inode and a simulated Docker Engine."""

import fcntl
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/ops/build_cache_budget.sh"
BUDGET = 12 * 1024**3
CURRENT_TAG = "a" * 40
ROLLBACK_TAG = "b" * 40
CURRENT_IMAGE = "sha256:" + "1" * 64
ROLLBACK_IMAGE = "sha256:" + "2" * 64
FIRST_REPLICA = "3" * 64
SECOND_REPLICA = "4" * 64


def executable(path, content):
    path.write_text(content)
    path.chmod(0o755)


MOCK_DOCKER = """#!/bin/sh
set -eu
printf '%s\\n' "$*" >>"$MOCK_DIR/calls"
[ "$1 $2" = '--context default' ] || exit 98
shift 2
case "$1 $2" in
  'context inspect') echo "${ENDPOINT:-unix:///var/run/docker.sock}" ;;
  'builder prune')
    if [ "$3" = '--help' ]; then
      if [ "${CLI:-modern}" = legacy ]; then
        echo 'docker builder prune --force --keep-storage bytes'
      else
        echo 'docker buildx prune --force --builder name --max-used-space bytes'
      fi
    else
      printf '%s\\n' "$*" >>"$MOCK_DIR/prune"
      touch "$MOCK_DIR/after"
      exit "${PRUNE_EXIT:-0}"
    fi ;;
  'buildx inspect') printf 'Driver: %s\\nEndpoint: default\\n' "${DRIVER:-docker}" ;;
  'info --format') echo '/var/lib/docker' ;;
  'image ls')
    phase=before
    if [ -e "$MOCK_DIR/after" ]; then phase=after; fi
    cat "$MOCK_DIR/images-$phase" ;;
  'container ls') cat "$MOCK_DIR/ids" ;;
  'container inspect')
    phase=before
    if [ -e "$MOCK_DIR/after" ]; then phase=after; fi
    cat "$MOCK_DIR/replicas-$phase" ;;
  *) echo "unexpected Docker command: $*" >&2; exit 99 ;;
esac
"""


@pytest.fixture
def engine(tmp_path):
    lock = tmp_path / "deploy.lock"
    lock.write_text("existing production lock inode\n")
    script = tmp_path / "maintenance.sh"
    source = SCRIPT.read_text()
    assert source.count("readonly lock=/run/emsarena/deploy.lock") == 1
    script.write_text(source.replace("readonly lock=/run/emsarena/deploy.lock", f'readonly lock="{lock}"'))
    executable(tmp_path / "docker", MOCK_DOCKER)
    executable(
        tmp_path / "curl",
        """#!/bin/sh
set -eu
case "$*" in
  *'--unix-socket /var/run/docker.sock http://localhost/v1.42/system/df?type=build-cache') ;;
  *) exit 98 ;;
esac
if [ -e "$MOCK_DIR/after" ]; then size="$CACHE_AFTER"; else size="$CACHE_BEFORE"; fi
printf '{"BuildCache":[{"Size":%s}]}\\n' "$size"
""",
    )
    executable(
        tmp_path / "df",
        """#!/bin/sh
set -eu
case "$*" in
  '-B1 --output=size -- /var/lib/docker') header=Size; size="${FS_TOTAL:-4000000}" ;;
  '-B1 --output=avail -- /var/lib/docker')
    header=Avail
    if [ -e "$MOCK_DIR/after" ]; then size="${FREE_AFTER:-1007000}"; else size="${FREE_BEFORE:-1000000}"; fi ;;
  *) exit 98 ;;
esac
printf '%s\\n%s\\n' "$header" "$size"
""",
    )
    if not shutil.which("flock"):
        # macOS has flock(2) but does not bundle the util-linux CLI.
        executable(
            tmp_path / "flock",
            f"#!{sys.executable}\n"
            "import fcntl, sys\n"
            "assert sys.argv[1:] == ['-n', '9']\n"
            "try:\n"
            "    fcntl.flock(9, fcntl.LOCK_EX | fcntl.LOCK_NB)\n"
            "except BlockingIOError:\n"
            "    sys.exit(1)\n",
        )
    tags = f"{CURRENT_TAG} {CURRENT_IMAGE}\nlatest {CURRENT_IMAGE}\n{ROLLBACK_TAG} {ROLLBACK_IMAGE}\n"
    replicas = f"{FIRST_REPLICA} {CURRENT_IMAGE} true healthy\n{SECOND_REPLICA} {CURRENT_IMAGE} true healthy\n"
    for phase in ("before", "after"):
        (tmp_path / f"images-{phase}").write_text(tags)
        (tmp_path / f"replicas-{phase}").write_text(replicas)
    (tmp_path / "ids").write_text(f"{FIRST_REPLICA}\n{SECOND_REPLICA}\n")
    (tmp_path / "calls").touch()

    def run(mode="budget", **environment):
        env = {
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "MOCK_DIR": str(tmp_path),
            "CACHE_BEFORE": str(BUDGET + 10000),
            "CACHE_AFTER": str(BUDGET),
            **environment,
        }
        return subprocess.run(
            ["bash", str(script), mode], env=env, capture_output=True, text=True, timeout=15, check=False
        )

    return run


@pytest.mark.parametrize("cli", ["modern", "legacy"])
@pytest.mark.parametrize("mode", ["budget", "clear-unused"])
def test_uses_only_selected_cache_prune_and_preserves_objects(engine, tmp_path, cli, mode):
    # A full clear also runs with less cache present than the regular budget.
    before = BUDGET + 10000 if mode == "budget" else 5000
    after = BUDGET if mode == "budget" else 1200
    result = engine(mode, CLI=cli, CACHE_BEFORE=str(before), CACHE_AFTER=str(after))
    assert result.returncode == 0, result.stderr
    expected = ["builder", "prune", "--force"]
    if cli == "modern":
        expected += ["--builder", "default"]
    if mode == "budget":
        expected += ["--max-used-space" if cli == "modern" else "--keep-storage", str(BUDGET)]
    assert (tmp_path / "prune").read_text().splitlines() == [" ".join(expected)]
    report = dict(row.split("=", 1) for row in result.stdout.splitlines())
    assert report["mode"] == mode
    assert report["current_release_sha"] == CURRENT_TAG
    assert report["protected_release_tags"] == "3"
    assert report["rollback_release_tags"] == "1"
    assert report["healthy_app_replicas"] == "2"
    assert set(report["retained_release_shas"].split(",")) == {CURRENT_TAG, ROLLBACK_TAG}
    assert report["protected_release_tags_verified"] == report["app_replicas_verified"] == "true"
    assert report["cache_reported_delta_bytes"] == str(before - after)
    assert report["filesystem_available_delta_bytes"] == "7000"
    assert ("budget_target_met" in report) == (mode == "budget")
    calls = (tmp_path / "calls").read_text().splitlines()
    selections = [call for call in calls if "container ls" in call]
    assert len(selections) == 2
    for selection in selections:
        assert "container ls -q --no-trunc" in selection
        assert "com.docker.compose.project=educationmanagementstudentarena" in selection
        assert "com.docker.compose.service=app" in selection
        assert "com.docker.compose.oneoff=False" in selection
    inspections = [call for call in calls if "container inspect" in call]
    assert len(inspections) == 2
    assert all(call.endswith(f"{FIRST_REPLICA} {SECOND_REPLICA}") for call in inspections)


@pytest.mark.parametrize("free", [800000, 799999])
def test_disk_at_or_above_eighty_percent_clears_unused_even_below_budget(engine, tmp_path, free):
    result = engine(CACHE_BEFORE="5000", CACHE_AFTER="1200", FS_TOTAL="4000000", FREE_BEFORE=str(free))
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "prune").read_text().splitlines() == ["builder prune --force --builder default"]
    assert "pressure_cleanup=true" in result.stdout
    assert "prune_skipped" not in result.stdout
    assert "protected_release_tags_verified=true" in result.stdout
    assert "app_replicas_verified=true" in result.stdout
    assert "cache_reported_delta_bytes=3800" in result.stdout


def test_disk_just_below_eighty_percent_uses_normal_budget(engine, tmp_path):
    result = engine(FS_TOTAL="4000000", FREE_BEFORE="800001")
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "prune").read_text().splitlines() == [
        f"builder prune --force --builder default --max-used-space {BUDGET}"
    ]
    assert "pressure_cleanup=true" not in result.stdout
    assert "protected_release_tags_verified=true" in result.stdout


def test_skips_under_budget_and_still_verifies(engine, tmp_path):
    result = engine(CACHE_BEFORE=str(BUDGET))
    assert result.returncode == 0, result.stderr
    assert "prune_skipped=within_budget" in result.stdout
    assert "app_replicas_verified=true" in result.stdout
    assert not (tmp_path / "prune").exists()


@pytest.mark.parametrize("mode", ["budget", "clear-unused"])
def test_busy_existing_inode_prevents_any_engine_call(engine, tmp_path, mode):
    lock = tmp_path / "deploy.lock"
    inode = lock.stat().st_ino
    with lock.open("r") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = engine(mode)
    assert result.returncode != 0
    assert "lock is held" in result.stderr
    assert (tmp_path / "calls").read_text() == ""
    assert lock.stat().st_ino == inode
    assert lock.read_text() == "existing production lock inode\n"


@pytest.mark.parametrize(
    "filename,old,new,message",
    [
        ("images-after", ROLLBACK_IMAGE, "sha256:" + "5" * 64, "tag-to-image mapping changed"),
        ("replicas-after", FIRST_REPLICA, "6" * 64, "replica, image or health changed"),
        ("replicas-after", CURRENT_IMAGE, ROLLBACK_IMAGE, "replica, image or health changed"),
        ("replicas-after", "true healthy", "true unhealthy", "replica, image or health changed"),
    ],
)
def test_detects_changed_protected_snapshot(engine, tmp_path, filename, old, new, message):
    path = tmp_path / filename
    path.write_text(path.read_text().replace(old, new, 1))
    result = engine()
    assert result.returncode != 0
    assert message in result.stderr
    assert (tmp_path / "prune").is_file()
    assert "app_replicas_verified=true" not in result.stdout


@pytest.mark.parametrize(
    "filename,old,new,message",
    [
        ("images-before", ROLLBACK_IMAGE, CURRENT_IMAGE, "distinct rollback release unavailable"),
        ("replicas-before", "true healthy", "true starting", "replica is unhealthy"),
    ],
)
def test_invalid_protected_objects_prevent_prune(engine, tmp_path, filename, old, new, message):
    path = tmp_path / filename
    path.write_text(path.read_text().replace(old, new))
    result = engine()
    assert result.returncode != 0
    assert message in result.stderr
    assert not (tmp_path / "prune").exists()


def test_retained_active_cache_can_keep_total_above_budget(engine):
    result = engine(CACHE_AFTER=str(BUDGET + 2500))
    assert result.returncode == 0, result.stderr
    assert "budget_target_met=false" in result.stdout
    assert "cache_reported_delta_bytes=7500" in result.stdout


def test_failed_prune_reports_failure_after_rechecking(engine, tmp_path):
    result = engine(PRUNE_EXIT="7")
    assert result.returncode == 7
    assert "prune_exit_status=7" in result.stdout
    assert "app_replicas_verified=true" in result.stdout
    assert "filesystem_available_delta_bytes=7000" in result.stdout


@pytest.mark.parametrize("overrides", [{"ENDPOINT": "tcp://elsewhere:2376"}, {"DRIVER": "docker-container"}])
def test_fails_closed_for_nonlocal_daemon_or_builder(engine, tmp_path, overrides):
    result = engine(**overrides)
    assert result.returncode != 0
    assert not (tmp_path / "prune").exists()
