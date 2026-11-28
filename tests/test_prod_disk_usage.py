import subprocess
from pathlib import Path

import yaml

from scripts.ops import disk_usage

ROOT = Path(__file__).resolve().parents[1]


def test_directory_groups_only_emit_allowlisted_categories():
    home = "\n".join(
        (
            "2000\t/home",
            "1000\t/home/private-user",
            "600\t/home/private-user/EducationManagementStudentArena",
            "400\t/home/private-user/EducationManagementStudentArena/backups",
            "41\t/home/private-user/private-directory",
            "25\t/home/another-private-user/private-directory",
            "120\t/not/home/private-user/EducationManagementStudentArena/backups",
        )
    )
    counts = disk_usage.directory_groups(home, "", "home")
    assert counts["/home"] == 2000 * 1024
    assert counts["tətbiq ehtiyat nüsxələri"] == 400 * 1024
    assert counts["Digər istifadəçi alt qovluqları"] == 66 * 1024
    assert "private" not in str(counts)
    assert disk_usage.directory_groups("59\t/host/var/lib/docker\n11\t/host/var/hidden", "/host", "var") == {
        "/var/lib/docker": 59 * 1024,
        "/var · digər alt qovluqlar": 11 * 1024,
    }


def test_docker_layers_de_duplicate_images_and_hide_metadata(capsys):
    one = {"Id": "private-repo-a", "Size": 70, "SharedSize": 20}
    two = {"Id": "private-repo-b", "Size": 30, "SharedSize": 20}
    disk_usage.docker_usage(
        {
            "LayersSize": 80,
            "Images": [one, one, two],
            "Volumes": [{"Name": "sensitive-project_postgres_data", "UsageData": {"Size": 35, "RefCount": 0}}],
            "BuildCache": [{"Type": "sensitive", "Size": 10, "InUse": False, "Shared": False}],
            "Containers": [{"SizeRw": 8, "Names": ["sensitive"]}],
        }
    )
    text = capsys.readouterr().out
    assert "bir dəfə — 0.000 GiB (80 B)" in text
    assert "məxsus laylar — 0.000 GiB (60 B)" in text
    assert "paylaşdığı laylar — 0.000 GiB (20 B)" in text
    assert "istinadı olmayan volume-lər — 0.000 GiB (35 B)" in text
    assert "postgres_data (1) — 0.000 GiB (35 B)" in text
    assert "paylaşılmayan keş — 0.000 GiB (10 B)" in text
    assert "private" not in text and "sensitive" not in text
    disk_usage.docker_usage({"Images": [{"Id": "x", "Size": None, "SharedSize": -1}], "LayersSize": -1})
    assert "məxsus laylar — ölçülmədi" in capsys.readouterr().out


def test_rotation_only_renders_counters_and_safe_config(monkeypatch, capsys):
    responses = iter(
        [
            (0, ("a" * 64 + "\n") * 2),
            (0, "json-file|10m|3\nprivate-driver|secret-cap|untrusted-file\n"),
            (0, "Archived and active journals take up 15.0M in the file system."),
            (0, "# comment with secret\nSystemMaxUse=100M\nSystemMaxUse=250M\nRuntimeMaxUse=1-private\n"),
        ]
    )
    monkeypatch.setattr(disk_usage, "run", lambda args, timeout: next(responses))
    disk_usage.rotation()
    disk_usage.journal_rotation()
    out = capsys.readouterr().out
    assert "json-file, max-size 10m, max-file 3 — 1" in out
    assert "journald SystemMaxUse — 250M" in out
    assert "15.0M" in out and "private" not in out and "secret" not in out and "untrusted" not in out


def test_physical_logs_only_emit_aggregates(tmp_path, monkeypatch, capsys):
    container = tmp_path / "containers" / "private-id"
    container.mkdir(parents=True)
    for name in ("private-id-json.log", "private-id-json.log.1", "private-id-json.log.2.gz"):
        (container / name).write_bytes(b"private log content" * 500)
    monkeypatch.setattr(disk_usage, "run", lambda args, timeout: (0, str(tmp_path)))

    def synthetic_scan(prefix, args, budget):
        scan = subprocess.run(args, capture_output=True, text=True, timeout=budget)
        return scan.returncode, scan.stdout

    monkeypatch.setattr(disk_usage, "low_io", synthetic_scan)
    disk_usage.docker_logs([], "")
    out = capsys.readouterr().out
    assert "Aktiv JSON logları (1 fayl)" in out
    assert "Rotasiya edilmiş JSON logları (2 fayl)" in out
    assert "private" not in out


def test_disk_job_is_separate_and_sha_pinned():
    config = yaml.safe_load((ROOT / ".github/workflows/prod-host-maint.yml").read_text())
    job = config["jobs"]["disk-usage"]
    assert config["permissions"] == {"contents": "read"}
    assert "github.ref == 'refs/heads/main'" in job["if"]
    assert "action != 'disk-usage'" in config["jobs"]["host"]["if"]
    script = job["steps"][0]["run"]
    assert "ref=${GITHUB_SHA}" in script and "${RUNNER_TEMP}" in script
    assert "ionice -c3" in script and "--privileged" not in script and "nsenter" not in script
    assert job["timeout-minutes"] == 5


def test_stock_compose_logs_and_tsdb_have_budgets():
    compose = yaml.safe_load((ROOT / "docker-compose.prod.yml").read_text())
    services = compose["services"]
    for section in services.values():
        assert section["logging"]["driver"] == "json-file"
        assert section["logging"]["options"] == {"max-size": "10m", "max-file": "3"}
    assert "--storage.tsdb.retention.size=${PROMETHEUS_RETENTION_SIZE:-6GB}" in services["prometheus"]["command"]
    assert "--storage.tsdb.retention.time=${PROMETHEUS_RETENTION_TIME:-15d}" in services["prometheus"]["command"]
    loki = yaml.safe_load((ROOT / "docker/loki/loki-config.yml").read_text())["limits_config"]
    assert loki["retention_period"] == "336h"
    assert loki["ingestion_rate_mb"] == "${LOKI_INGESTION_RATE_MB:-0.025}"
    assert "-config.expand-env=true" in services["loki"]["command"]
    assert "-config.expand-env=true" in " ".join(services["promtail"]["command"])
    scrape = yaml.safe_load((ROOT / "docker/promtail/promtail-config.yml").read_text())["scrape_configs"][0]
    assert scrape["docker_sd_configs"][0]["filters"] == [
        {"name": "label", "values": ["com.docker.compose.project=${LOG_COMPOSE_PROJECT}"]}
    ]
