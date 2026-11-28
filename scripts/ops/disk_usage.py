"""Read-only production disk inventory. Output contains aggregate counts and sizes only."""

import json
import os
import re
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import PurePosixPath

VOLUMES = {
    "postgres_data",
    "redis_data",
    "media_data",
    "static_data",
    "prometheus_data",
    "grafana_data",
    "alertmanager_data",
    "loki_data",
    "promtail_positions",
    "piston_packages",
}
CACHE_TYPES = {"regular", "exec.cachemount", "source.local", "source.git.checkout", "frontend", "internal"}
DRIVERS = {"json-file", "local", "journald", "syslog", "fluentd", "none", "gelf", "awslogs", "splunk"}
MISSING = "ölçülmədi"
PROJECT = "EducationManagementStudentArena"


def run(args, timeout):
    """Discard raw stderr, which can contain private filenames. Keep partial du results."""
    try:
        result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=timeout)
        return result.returncode, result.stdout.decode("utf-8", "replace")
    except subprocess.TimeoutExpired as exc:
        return 124, (exc.stdout or b"").decode("utf-8", "replace")
    except OSError:
        return 1, ""


def size(value):
    return f"{value / 2 ** 30:.3f} GiB ({value:,} B)" if value is not None else MISSING


def amount(label, value):
    print(f"- {label} — {size(value)}")


def bytes_sum(rows, field):
    values = [r.get(field, -1) for r in rows]
    return sum(values) if all(isinstance(v, int) and v >= 0 for v in values) else None


def docker_usage(df):
    images = {r["Id"]: r for r in df.get("Images") or []}.values()
    layers = df.get("LayersSize")
    if not isinstance(layers, int) or layers < 0:
        layers = None
    amount("Image layları, paylaşılan lay bir dəfə", layers)
    unique = None
    if all(
        isinstance(r.get("Size"), int) and isinstance(r.get("SharedSize"), int) and r["Size"] >= r["SharedSize"] >= 0
        for r in images
    ):
        unique = sum(r["Size"] - r["SharedSize"] for r in images)
    amount("Yalnız bir image-ə məxsus laylar", unique)
    amount(
        "Bir neçə image-in paylaşdığı laylar",
        layers - unique if layers is not None and unique is not None and layers >= unique else None,
    )
    amount("Konteynerlərin yazılan layları", bytes_sum(df.get("Containers") or [], "SizeRw"))
    by_volume = {}
    for r in df.get("Volumes") or []:
        name = r.get("Name", "")
        key = next((v for v in VOLUMES if name == v or name.endswith("_" + v)), "digər")
        by_volume.setdefault(key, []).append(r.get("UsageData") or {})
    usage = [row for rows in by_volume.values() for row in rows]
    amount(f"Docker volume-ləri ümumi ({len(usage)})", bytes_sum(usage, "Size"))
    unused = [row for row in usage if row.get("RefCount") == 0]
    amount(
        "Konteyner istinadı olmayan volume-lər",
        (
            bytes_sum(unused, "Size")
            if all(isinstance(r.get("RefCount"), int) and r["RefCount"] >= 0 for r in usage)
            else None
        ),
    )
    for key, rows in sorted(by_volume.items()):
        amount(f"Volume · {key} ({len(rows)})", bytes_sum(rows, "Size"))
    cache = df.get("BuildCache") or []
    amount(f"Build keşi ({len(cache)} qeyd)", bytes_sum(cache, "Size"))
    amount("Keşdə paylaşılan kimi işarələnən hissə", bytes_sum([r for r in cache if r.get("Shared")], "Size"))
    amount(
        "Hazırda istifadədə olmayan, paylaşılmayan keş",
        bytes_sum([r for r in cache if not r.get("InUse") and not r.get("Shared")], "Size"),
    )
    grouped = {}
    for r in cache:
        key = r.get("Type")
        grouped.setdefault(key if key in CACHE_TYPES else "digər", []).append(r)
    for key, rows in sorted(grouped.items()):
        amount(f"Keş növü · {key}", bytes_sum(rows, "Size"))
    print("Image, keş və host qovluqlarında eyni məlumat hesablana bilər. Bölmələri bir-birinə toplamayın.")


def rotation():
    rc, raw = run(["docker", "ps", "-aq", "--no-trunc"], 8)
    ids = [s for s in raw.splitlines() if re.fullmatch(r"[a-f0-9]{64}", s)]
    if rc or not ids:
        print("Docker log rotasiyası — " + MISSING)
        return
    fmt = '{{.HostConfig.LogConfig.Type}}|{{index .HostConfig.LogConfig.Config "max-size"}}|{{index .HostConfig.LogConfig.Config "max-file"}}'
    rc, out = run(["docker", "inspect", "--format", fmt, *ids], 12)
    counts = Counter()
    for line in out.splitlines():
        fields = line.split("|")
        if len(fields) == 3:
            driver, cap, files = fields
            cap = cap if re.fullmatch(r"[0-9]{1,12}[kmgt]?[bB]?", cap, re.I) else "açıq göstərilməyib"
            files = files if re.fullmatch(r"[0-9]{1,6}", files) else "açıq göstərilməyib"
            counts[(driver if driver in DRIVERS else "digər", cap, files)] += 1
    for (driver, cap, files), n in sorted(counts.items()):
        print(f"- {driver}, max-size {cap}, max-file {files} — {n} konteyner")
    if rc or sum(counts.values()) != len(ids):
        print("- Bəzi konteynerlər ölçü zamanı dəyişdi.")


def host_reader():
    if os.geteuid() == 0:
        return [], ""
    if run(["sudo", "-n", "true"], 2)[0] == 0:
        return ["sudo", "-n"], ""
    # The existing exporter mounts / read-only. No helper container or writable mount.
    fmt = (
        '{{.State.Running}} {{range .Mounts}}{{if and (eq .Destination "/host") (eq .Source "/")}}{{.RW}}{{end}}{{end}}'
    )
    rc, out = run(["docker", "inspect", "--format", fmt, "emsarena-node-exporter"], 4)
    if not rc and out.strip() == "true false":
        return ["docker", "exec", "-u", "0", "emsarena-node-exporter"], "/host"
    return [], ""


def low_io(prefix, args, budget):
    # An internal timeout also stops an exec inside the exporter if its client disconnects.
    wrapper = 'if command -v ionice >/dev/null; then exec ionice -c3 nice -n 19 "$@"; else exec nice -n 19 "$@"; fi'
    return run([*prefix, "timeout", "-s", "KILL", str(budget), "sh", "-c", wrapper, "disk-usage", *args], budget + 5)


def directory_groups(output, mount, tree):
    result = Counter()
    var = {"lib", "backups", "cache", "log", "tmp", "spool", "www", "snap"}
    lib = {"docker", "containerd", "apt", "snapd", "systemd"}
    home = {
        PROJECT: "tətbiq qovluğu",
        ".cache": "istifadəçi keşləri",
        ".local": "lokal proqramlar",
        ".docker": "Docker istifadəçi faylları",
        "actions-runner": "Actions runner",
    }
    app = {"backups": "tətbiq ehtiyat nüsxələri", ".git": "tətbiqin Git deposu", "media": "tətbiq media qovluğu"}
    for line in output.splitlines():
        count, sep, source = line.partition("\t")
        if not sep or not count.isdecimal():
            continue
        path = PurePosixPath(source)
        try:
            parts = path.relative_to((mount or "") + "/" + tree).parts
        except ValueError:
            continue
        label = None
        if not parts:
            label = "/" + tree
        elif tree == "var" and len(parts) == 1:
            label = "/var/" + parts[0] if parts[0] in var else "/var · digər alt qovluqlar"
        elif tree == "var" and len(parts) == 2 and parts[0] == "lib" and parts[1] in lib:
            label = "/var/lib/" + parts[1]
        elif tree == "var" and parts == ("log", "journal"):
            label = "Host jurnalının qovluğu"
        elif tree == "home" and len(parts) == 2:
            label = home.get(parts[1], "Digər istifadəçi alt qovluqları")
        elif tree == "home" and len(parts) == 3 and parts[1] == PROJECT:
            label = app.get(parts[2])
        if label:
            result[label] += int(count) * 1024
    return result


def backup_usage():
    worker = "educationmanagementstudentarena-celery_worker-1"
    fmt = '{{.State.Running}} {{range .Mounts}}{{if eq .Destination "/backups"}}{{.Type}} {{.RW}} {{.Source}}{{end}}{{end}}'
    rc, info = run(["docker", "inspect", "--format", fmt, worker], 4)
    fields = info.strip().split(" ", 3)
    if (
        rc
        or len(fields) != 4
        or fields[:3] != ["true", "bind", "false"]
        or PurePosixPath(fields[3]).parts[-3:] != (PROJECT, "backups", "postgres")
    ):
        amount("PostgreSQL ehtiyat nüsxələri (bind mount)", None)
        return
    rc, out = low_io(["docker", "exec", worker], ["du", "-sk", "/backups"], 10)
    match = re.fullmatch(r"(\d+)\s+/backups\s*", out)
    amount("PostgreSQL ehtiyat nüsxələri (bind mount)", int(match[1]) * 1024 if not rc and match else None)


def journal_rotation():
    rc, journal = run(["journalctl", "--disk-usage"], 4)
    match = re.search(r"take up ([0-9.]+[BKMGT]?) ", journal)
    print("- systemd journalctl --disk-usage — " + (match[1] if not rc and match else MISSING))
    rc, config = run(["systemd-analyze", "cat-config", "systemd/journald.conf"], 3)
    if rc:
        print("- journald rotasiya konfiqurasiyası — " + MISSING)
        return
    keys = ("SystemMaxUse", "RuntimeMaxUse", "SystemMaxFileSize", "RuntimeMaxFileSize", "MaxFileSec", "MaxRetentionSec")
    options = {}
    for line in config.splitlines():
        key, _, val = line.strip().partition("=")
        if key.strip() in keys:
            options[key.strip()] = val.strip()
    for key in keys:
        val = options.get(key, "")
        if not val:
            val = "systemd standartı"
        elif not re.fullmatch(r"(?:[0-9]+(?:[.][0-9]+)?(?:[KMGTPE]|us|ms|s|min|h|d|w|y|month|year)?\s*){1,4}", val):
            val = MISSING
        print(f"- journald {key} — {val}")


def directory_usage(prefix, mount, tree):
    rc, out = low_io(prefix, ["du", "-kx", "-d", "3" if tree == "home" else "2", mount + "/" + tree], 50)
    totals = directory_groups(out, mount, tree)
    if rc or "/" + tree not in totals:
        print(f"- /{tree} — natamam ölçü (icazə və ya vaxt həddi). Görünən rəqəmlər aşağı sərhəddir.")
    for label, value in totals.most_common():
        amount(label, value)


def docker_logs(prefix, mount):
    rc, directory = run(["docker", "info", "--format", "{{.DockerRootDir}}"], 6)
    root = PurePosixPath(directory.strip())
    if rc or not root.is_absolute() or ".." in root.parts:
        print("Docker JSON log faylları — " + MISSING)
        return
    # BusyBox and GNU find/du both support this form. Names never leave the pipe.
    script = r"""set -eu
result=$(find "$1" -maxdepth 2 -type f -name '*-json.log*' -exec du -k {} +) || exit 1
printf '%s\n' "$result" | awk 'NF>=2 {if ($NF ~ /-json[.]log$/) {a+=$1; n++} else {b+=$1; m++}} END {printf "%.0f %d %.0f %d\n", a*1024,n,b*1024,m}'
"""
    rc, out = low_io(prefix, ["sh", "-c", script, "disk-usage", mount + str(root / "containers")], 15)
    m = re.fullmatch(r"(\d+) (\d+) (\d+) (\d+)\s*", out)
    if rc or not m:
        print("Docker JSON log faylları — " + MISSING)
        return
    for label, value, count in (("Aktiv JSON logları", m[1], m[2]), ("Rotasiya edilmiş JSON logları", m[3], m[4])):
        amount(f"{label} ({count} fayl)", int(value))


def main():
    print("## Disk istifadəsi · " + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    fs = os.statvfs("/")
    total, free, avail = (blocks * fs.f_frsize for blocks in (fs.f_blocks, fs.f_bfree, fs.f_bavail))
    amount("Kök fayl sistemi · ümumi", total)
    amount("Tutulan bloklar", total - free)
    amount("Adi istifadəçiyə ayrılan boş yer", avail)
    amount("Sistem üçün ayrılmış boş bloklar", free - avail)
    print(f"- Monitorinqdə doluluq — {100 * (1 - avail / total):.1f}%")
    print("\n### Docker")
    # A single GET to the API behind 'docker system df -v'. Never emit raw image or container metadata.
    rc, raw = run(
        [
            "curl",
            "-fsS",
            "--max-time",
            "65",
            "--unix-socket",
            "/var/run/docker.sock",
            "http://localhost/v1.42/system/df",
        ],
        68,
    )
    if rc:
        print("Docker layları, cildlər və keş — " + MISSING)
    else:
        try:
            usage = json.loads(raw)
        except ValueError:
            usage = None
        if isinstance(usage, dict) and "LayersSize" in usage:
            docker_usage(usage)
        else:
            print("Docker layları, cildlər və keş — " + MISSING)
    print("\n### Log rotasiyası")
    rotation()
    journal_rotation()
    prefix, mount = host_reader()
    docker_logs(prefix, mount)
    print("\n### Diskə ayrılan yer · qovluqlar")
    print("Alt qovluqlar yuxarıdakı cəmlərə daxildir. Fərdi adlar göstərilmir.")
    backup_usage()
    directory_usage(prefix, mount, "var")
    # The self-hosted runner owns the deployment and runner trees. Its native view may be wider than an exporter without DAC capabilities.
    directory_usage(prefix if not mount else [], "", "home")


if __name__ == "__main__":
    os.environ["LC_ALL"] = "C"
    main()
