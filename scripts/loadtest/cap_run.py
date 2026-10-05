#!/usr/bin/env python3
"""Tutum testi orkestratoru — serverdə (self-hosted runner) işləyir.

CANLI SİSTEMƏ TOXUNMUR: Codex-in 2026-10-04 izolə stack-ini
(`emsarena-capacity-20261004`, `internal: true` şəbəkə, ayrıca Postgres/PgBouncer/
Redis/nginx/app) CANLI image ilə yenidən qaldırır, sintetik bazada ölçür və
dayandırır. Canlı sistemin sağlamlığı hər 10 s yoxlanır; iki ardıcıl uğursuzluq
və ya RAM < 15% olarsa yük dərhal dayandırılır.

Plan: `--plan "login:500@60,exam:500@60,journal:200@60,cabinet:500@60,mixed:1000@90"`
  <mode>:<users>@<spawn pəncərəsi saniyə>. Hər pillə ayrıca hesabat verir.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

CAP = Path("/home/wcu/emsarena-capacity-20261004")
PROJECT = "emsarena-capacity-20261004"
NETWORK = f"{PROJECT}_isolated"
LIVE_APP = "educationmanagementstudentarena-app-1"
APPS = ("app1", "app2", "app3", "app4")
P95_LIMIT_MS = 2500
ERROR_LIMIT = 0.01


def sh(args, check=True, capture=False, timeout=None, merge=False, **kw):
    if capture:
        err = subprocess.STDOUT if merge else subprocess.PIPE
        return subprocess.run(args, check=check, text=True, stdout=subprocess.PIPE, stderr=err, timeout=timeout, **kw).stdout
    return subprocess.run(args, check=check, timeout=timeout, **kw)


def log(*parts):
    print(time.strftime("%H:%M:%S"), *parts, flush=True)


def live_health() -> bool:
    try:
        out = sh(
            ["curl", "-sS", "--max-time", "8", "--resolve", "ems.wcu.edu.az:443:127.0.0.1", "https://ems.wcu.edu.az/health/"],
            capture=True,
            check=False,
            timeout=12,
        )
        return json.loads(out).get("status") == "healthy"
    except Exception:
        return False


def mem_available() -> float:
    data = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
    return int(data["MemAvailable"].split()[0]) / int(data["MemTotal"].split()[0])


class Stack:
    def __init__(self, args):
        self.args = args
        self.base = json.loads((CAP / "compose.json").read_text())
        self.image = json.loads(sh(["docker", "inspect", LIVE_APP], capture=True))[0]["Image"]
        self.compose_file = CAP / "cap-compose.json"
        self.env = self.base["services"]["app1"]["environment"]
        self.owner_url = self.env["MIGRATION_DATABASE_URL"]
        self.db_password = self.base["services"]["db"]["environment"]["POSTGRES_PASSWORD"]

    def build(self):
        cfg = json.loads(json.dumps(self.base))
        services = cfg["services"]
        for name in APPS:
            if name not in services:
                services[name] = json.loads(json.dumps(services["app1"]))
        services["db"]["cpus"] = self.args.db_cpus
        services["db"]["command"] = [
            "postgres",
            "-c", "max_connections=250",
            "-c", "shared_buffers=1GB",
            "-c", "effective_cache_size=3GB",
            "-c", "jit=off",
            "-c", "shared_preload_libraries=pg_stat_statements",
            "-c", "pg_stat_statements.track=top",
            "-c", "track_io_timing=on",
            "-c", "log_lock_waits=on",
            "-c", "deadlock_timeout=500ms",
            "-c", "log_min_duration_statement=1000",
        ]
        services["pool"]["cpus"] = 1.0  # prod PGBOUNCER_CPU_LIMIT defoltu
        services["redis"]["cpus"] = 0.5
        services["edge"]["cpus"] = 0.75
        # Prod nginx `upstream` bloku işlətmir (DNS ilə `app`) — replikaları «ölü» elan
        # etmir. Codex-in edge-i defolt max_fails=1 + 15 s timeout ilə yük altında
        # bütün replikaları atıb 502 kaskadı yaradırdı (prod-da olmayan artefakt).
        edge_conf = CAP / "cap-nginx.conf"
        edge_conf.write_text(
            "events { worker_connections 8192; } http { upstream backend { least_conn; "
            + " ".join(f"server {a}:8000 max_fails=0;" for a in APPS)
            + " keepalive 64; } server { listen 443 ssl; ssl_certificate /cert.pem; ssl_certificate_key /key.pem; "
            "location / { proxy_pass http://backend; proxy_http_version 1.1; proxy_set_header Connection \"\"; "
            "proxy_set_header Host $http_host; proxy_set_header X-Forwarded-Proto https; "
            "proxy_set_header X-Forwarded-For $http_x_test_client; proxy_read_timeout 60s; } } }"
        )
        services["edge"]["volumes"] = [
            v.replace(f"{CAP}/nginx.conf:", f"{edge_conf}:") for v in services["edge"].get("volumes", [])
        ]
        services["worker"]["cpus"] = 0.5
        for name in APPS + ("worker",):
            services[name]["image"] = self.image
            services[name]["volumes"] = [v for v in services[name].get("volumes", []) if "fix-" not in v and "phase4" not in v]
            services[name]["volumes"] += self.overlay_mounts()
        for name in APPS:
            services[name]["cpus"] = self.args.app_cpus
            services[name]["environment"]["MAX_INFLIGHT_LOGIN_REQUESTS"] = str(self.args.login_lane)
        self.compose_file.write_text(json.dumps(cfg))
        os.chmod(self.compose_file, 0o600)
        log("compose built", "image", self.image[:19], "app_cpus", self.args.app_cpus, "db_cpus", self.args.db_cpus)

    def overlay_mounts(self):
        """--overlay: branch-in Python kodu canlı image-in asılılıqları üzərində."""
        if not self.args.overlay:
            return []
        repo = Path(self.args.repo)
        return [f"{repo / d}:/app/{d}:ro" for d in ("apps", "core", "config", "templates")]

    def compose(self, *extra, **kw):
        return sh(["docker", "compose", "-p", PROJECT, "-f", str(self.compose_file), *extra], **kw)

    def up(self):
        self.compose("up", "-d")
        for _ in range(60):
            if self.db_ready():
                break
            time.sleep(2)
        log("db ready")

    def db_ready(self):
        return sh(["docker", "exec", f"{PROJECT}-db-1", "pg_isready", "-U", "capacity_owner", "-d", "capacity"], check=False, capture=True).strip().endswith("accepting connections")

    def psql(self, sql, db="capacity"):
        return sh(
            ["docker", "exec", f"{PROJECT}-db-1", "psql", "-X", "-q", "-A", "-t", "-F", "\t", "-U", "capacity_owner", "-d", db, "-c", sql],
            capture=True,
            check=False,
        )

    def manage(self, *cmd, env=None, mounts=(), timeout=3600):
        args = ["run", "--rm", "--no-deps", "--user", "0", "-v", f"{CAP}:/capacity", "-v", f"{self.args.harness}:/harness:ro"]
        for m in list(mounts) + self.overlay_mounts():
            args += ["-v", m]
        # release.sh ilə eyni: birdəfəlik owner əməliyyatları rol yoxlamasından keçmir.
        args += ["-e", f"DATABASE_URL={self.owner_url}", "-e", "EMS_DB_ROLE_ENFORCE=off"]
        for k, v in (env or {}).items():
            args += ["-e", f"{k}={v}"]
        args += ["app1", "python", "manage.py", *cmd]
        return self.compose(*args, timeout=timeout, check=False)

    def edge_ready(self):
        """Test şəbəkəsi `internal: true`-dur — host portu açılmır; yoxlama şəbəkə içindən."""
        probe = (
            "import ssl,urllib.request;"
            "ctx=ssl._create_unverified_context();"
            "print(urllib.request.urlopen('https://edge/ping/',context=ctx,timeout=5).status)"
        )
        out = ""
        for attempt in range(90):
            out = sh(["docker", "exec", f"{PROJECT}-app1-1", "python", "-c", probe], capture=True, check=False, merge=True)
            if out.strip().endswith("200"):
                return True
            if attempt % 15 == 14:
                log("edge not ready yet:", (out or "").strip().splitlines()[-1:] )
            time.sleep(2)
        return False

    def restart_apps(self):
        self.compose("restart", *APPS)
        time.sleep(8)
        # nginx upstream ünvanları start zamanı həll olunur — app-lar yenidən
        # başlayanda edge də yenidən başlamalıdır (Codex runner-ləri də belə edirdi).
        self.compose("restart", "edge")
        if not self.edge_ready():
            for svc in ("edge",) + APPS:
                tail = sh(["docker", "logs", "--tail", "25", f"{PROJECT}-{svc}-1"], capture=True, check=False, merge=True)
                log(f"--- {svc} logs ---\n" + "\n".join((tail or "").splitlines()[-25:]))
            raise RuntimeError("test edge did not become ready")

    def stop(self):
        self.compose("stop", check=False)


class Telemetry(threading.Thread):
    """5 s-lik nümunələr: konteyner CPU, DB gözləmələri, PgBouncer növbəsi, canlı sağlamlıq."""

    def __init__(self, stack, path):
        super().__init__(daemon=True)
        self.stack, self.path = stack, path
        self.stop_event = threading.Event()
        self.guard_tripped = None
        self.health_failures = 0

    def sample(self):
        row = {"t": round(time.time(), 1)}
        stats = sh(
            ["docker", "stats", "--no-stream", "--format", "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"],
            capture=True,
            check=False,
            timeout=30,
        )
        cpu = {}
        for line in stats.splitlines():
            parts = line.split("\t")
            if len(parts) >= 2 and (PROJECT in parts[0] or "cap-gen" in parts[0] or parts[0].startswith("educationmanagementstudentarena-app") or parts[0] == "emsarena-postgres"):
                try:
                    cpu[parts[0].replace(PROJECT + "-", "")] = float(parts[1].rstrip("%"))
                except ValueError:
                    pass
        row["cpu"] = cpu
        waits = self.stack.psql(
            "SELECT coalesce(wait_event_type,'cpu'), coalesce(wait_event,state), count(*) FROM pg_stat_activity "
            "WHERE datname='capacity' AND state <> 'idle' AND pid <> pg_backend_pid() GROUP BY 1,2"
        )
        row["db_active"] = {f"{a}:{b}": int(c) for a, b, c in (l.split("\t") for l in waits.splitlines() if l.count("\t") == 2)}
        pools = sh(
            ["docker", "exec", "-e", f"PGPASSWORD={self.stack.db_password}", f"{PROJECT}-db-1", "psql", "-X", "-q", "-A", "-F", "\t",
             "-h", "pool", "-p", "5432", "-U", "capacity_owner", "pgbouncer", "-c", "SHOW POOLS"],
            capture=True,
            check=False,
        )
        lines = [l.split("\t") for l in pools.splitlines()]
        if lines and "cl_waiting" in lines[0]:
            head = lines[0]
            for values in lines[1:]:
                if len(values) == len(head) and values[head.index("database")] == "capacity":
                    rec = dict(zip(head, values))
                    row["pool"] = {k: rec.get(k) for k in ("cl_active", "cl_waiting", "sv_active", "sv_idle", "maxwait")}
        healthy = live_health()
        self.health_failures = 0 if healthy else self.health_failures + 1
        row["live_healthy"] = healthy
        row["mem_available"] = round(mem_available(), 3)
        row["loadavg"] = Path("/proc/loadavg").read_text().split()[:3]
        return row

    def run(self):
        with self.path.open("w") as fh:
            while not self.stop_event.is_set():
                try:
                    row = self.sample()
                except Exception as exc:  # telemetriya testi yıxmamalıdır
                    row = {"t": time.time(), "error": repr(exc)}
                fh.write(json.dumps(row) + "\n")
                fh.flush()
                if self.health_failures >= 2 or row.get("mem_available", 1) < 0.15:
                    self.guard_tripped = row
                    log("HOST_GUARD_TRIP", json.dumps({k: row.get(k) for k in ("live_healthy", "mem_available", "loadavg")}))
                    stop_generators()
                    return
                self.stop_event.wait(5)


def stop_generators():
    names = sh(["docker", "ps", "-q", "--filter", "name=cap-gen-"], capture=True, check=False).split()
    if names:
        sh(["docker", "stop", "-t", "15", *names], check=False)


def capture_stage_errors(run_dir, name, since_iso):
    """Pillə ərzində app-ların ERROR sətirləri (503-lər çıxılmaqla) + traceback-ın sonu."""
    rows = []
    for svc in APPS:
        text = sh(["docker", "logs", "--since", since_iso, f"{PROJECT}-{svc}-1"], capture=True, check=False, merge=True)
        for line in (text or "").splitlines():
            if '"level": "ERROR"' not in line or "Service Unavailable" in line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            rows.append({"svc": svc, "message": rec.get("message", "")[:300], "exc": (rec.get("exc_info") or "")[-1500:]})
    (run_dir / f"{name}-errors.json").write_text(json.dumps(rows[-300:], indent=1))
    counts = {}
    for r in rows:
        key = r["message"][:120] + " || " + (r["exc"].strip().splitlines()[-1][:160] if r["exc"] else "")
        counts[key] = counts.get(key, 0) + 1
    for key, n in sorted(counts.items(), key=lambda kv: -kv[1])[:8]:
        log("APP_ERROR", n, key)


def run_stage(stack, args, spec, index, cursor, seed_path, run_dir, t_cursor=0):
    mode, rest = spec.split(":")
    users, window = rest.split("@") if "@" in rest else (rest, "60")
    users, window = int(users), int(window)
    name = f"{index:02d}-{mode}-{users}"
    workers = max(1, min(args.max_workers, math.ceil(users / args.users_per_worker)))
    teachers = len(json.loads(seed_path.read_text()).get("journals") or [])
    sessions_env = []
    if mode == "login":
        spawn_rate = max(1.0, users / window)
        go_at = 0.0
        run_time = window + 60
    else:
        exam_span = args.questions * (args.think_max + args.think_min) / 2 + 30
        tail = exam_span if mode in ("exam", "mixed", "journal") else args.cabinet_seconds
        if args.preauth == "session" and mode in ("exam", "cabinet", "mixed"):
            sessions_path = run_dir / f"{name}-sessions.json"
            log("session pool", name, users)
            t0 = time.monotonic()
            stack.manage(
                "shell", "-c", "exec(open('/harness/cap_sessions.py').read())",
                env={
                    "CAP_SESSION_START": str(cursor + 1),
                    "CAP_SESSION_COUNT": str(users),
                    "CAP_SESSION_OUT": sessions_path.as_posix().replace(str(CAP), "/capacity"),
                    "CAP_SESSION_THREADS": "8",
                },
            )
            log("session pool ready", round(time.monotonic() - t0, 1), "s")
            sessions_env = ["-e", f"CAP_SESSIONS={sessions_path.as_posix().replace(str(CAP), '/capacity')}"]
            spawn_rate = max(20.0, users / 30)
            preauth = users / spawn_rate
        else:
            spawn_rate = args.preauth_rate
            preauth = users / spawn_rate
        go_at = time.time() + preauth + 25
        run_time = int(preauth + 25 + window + tail + 60)
    stage_started_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    log("STAGE_START", name, f"users={users} window={window}s workers={workers} spawn={spawn_rate:.1f}/s run_time={run_time}s")
    stack.psql("SELECT pg_stat_statements_reset()")
    stop_generators()
    sh(["docker", "rm", "-f", "cap-gen-master"], check=False, capture=True)
    common = [
        "--network", NETWORK, "--user", "0",
        "-v", f"{CAP}:/capacity", "-v", f"{args.harness}:/harness:ro",
        "-e", f"CAP_SEED={seed_path.as_posix().replace(str(CAP), '/capacity')}",
        "-e", f"CAP_RUN_DIR={run_dir.as_posix().replace(str(CAP), '/capacity')}",
        "-e", f"CAP_MODE={mode}", "-e", f"CAP_STAGE={name}", "-e", f"CAP_GO_AT={go_at}",
        "-e", f"CAP_START_WINDOW={window}", "-e", f"CAP_THINK={args.think_min}:{args.think_max}",
        *sessions_env,
        "--entrypoint", "/capacity/toolenv/bin/locust", stack.image,
        "-f", "/harness/cap_locust.py",
    ]
    csv_prefix = f"{run_dir.as_posix().replace(str(CAP), '/capacity')}/{name}"
    master = [
        "docker", "run", "-d", "--name", "cap-gen-master", "--cpus", "0.5", "--memory", "1g", *common,
        "--master", "--expect-workers", str(workers), "--headless", "-u", str(users), "-r", f"{spawn_rate:.2f}",
        "--run-time", f"{run_time}s", "--stop-timeout", "30", "--host", "https://edge",
        "--csv", csv_prefix, "--csv-full-history", "--html", f"{csv_prefix}.html", "--exit-code-on-error", "0",
    ]
    sh(master, capture=True)
    student_share = users if mode != "journal" else 0
    for w in range(workers):
        lo = cursor + student_share * w // workers
        hi = cursor + student_share * (w + 1) // workers
        t_users = min(users, teachers) if mode == "journal" else max(1, users // 10)
        t_lo = (t_cursor + t_users * w // workers) % max(1, teachers)
        t_hi = t_lo + (t_users * (w + 1) // workers - t_users * w // workers)
        sh([
            "docker", "run", "-d", "--name", f"cap-gen-w{w}", "--cpus", "1", "--memory", "1500m",
            "-e", f"CAP_WORKER={w}", "-e", f"CAP_OFFSET={lo}", "-e", f"CAP_SHARD={hi - lo}",
            "-e", f"CAP_T_OFFSET={t_lo}", "-e", f"CAP_T_SHARD={t_hi - t_lo}",
            *common, "--worker", "--master-host", "cap-gen-master",
        ], capture=True)
    telemetry = Telemetry(stack, run_dir / f"{name}-telemetry.jsonl")
    telemetry.start()
    started = time.monotonic()
    while True:
        state = sh(["docker", "inspect", "-f", "{{.State.Running}}", "cap-gen-master"], capture=True, check=False).strip()
        if state != "true" or telemetry.guard_tripped:
            break
        if time.monotonic() - started > run_time + 180:
            log("STAGE_TIMEOUT", name)
            stop_generators()
            break
        time.sleep(5)
    telemetry.stop_event.set()
    telemetry.join(timeout=30)
    for cname in ["cap-gen-master"] + [f"cap-gen-w{w}" for w in range(workers)]:
        logs = sh(["docker", "logs", cname], capture=True, check=False, merge=True)
        (run_dir / f"{name}-{cname}.log").write_text(logs or "")
        sh(["docker", "rm", "-f", cname], check=False, capture=True)
    capture_stage_errors(run_dir, name, stage_started_iso)
    sql = stack.psql(
        "SELECT calls, round(total_exec_time::numeric,1), round(mean_exec_time::numeric,2), round(max_exec_time::numeric,1), "
        "rows, left(regexp_replace(query, '\\s+', ' ', 'g'), 300) FROM pg_stat_statements "
        "WHERE dbid=(SELECT oid FROM pg_database WHERE datname='capacity') ORDER BY total_exec_time DESC LIMIT 25"
    )
    (run_dir / f"{name}-sql.tsv").write_text("calls\ttotal_ms\tmean_ms\tmax_ms\trows\tquery\n" + sql)
    result = summarize_stage(run_dir, name, mode, users, window, telemetry)
    result["guard_tripped"] = bool(telemetry.guard_tripped)
    log("STAGE_RESULT", json.dumps({k: v for k, v in result.items() if k not in ("requests", "errors")}))
    used_t = (min(users, teachers) if mode == "journal" else (users // 10 if mode == "mixed" else 0))
    result["t_cursor_next"] = (t_cursor + used_t) % max(1, teachers)
    return result, cursor + student_share


def pct(row, key):
    try:
        return float(row.get(key) or 0)
    except ValueError:
        return 0.0


def summarize_stage(run_dir, name, mode, users, window, telemetry):
    stats_path = run_dir / f"{name}_stats.csv"
    rows = list(csv.DictReader(stats_path.open())) if stats_path.exists() else []
    per = []
    work_total = work_fail = 0
    work_p95 = 0.0
    for row in rows:
        if row["Name"] == "Aggregated":
            continue
        count, fails = int(row["Request Count"]), int(row["Failure Count"])
        item = {
            "name": row["Name"],
            "method": row["Type"],
            "count": count,
            "fail": fails,
            "p50": pct(row, "50%"),
            "p95": pct(row, "95%"),
            "p99": pct(row, "99%"),
            "max": round(pct(row, "Max Response Time")),
            "rps": round(pct(row, "Requests/s"), 2),
        }
        per.append(item)
        if not row["Name"].startswith("[pre]") and row["Type"] != "FIXTURE":
            work_total += count
            work_fail += fails
            work_p95 = max(work_p95, item["p95"])
    errors = []
    fail_path = run_dir / f"{name}_failures.csv"
    if fail_path.exists():
        for row in csv.DictReader(fail_path.open()):
            errors.append({"name": row["Name"], "error": row["Error"][:200], "count": int(row["Occurrences"])})
        errors.sort(key=lambda e: -e["count"])
    counters = {}
    for path in run_dir.glob(f"counters-{name}-w*.jsonl"):
        for line in path.read_text().splitlines():
            for k, v in json.loads(line).items():
                if isinstance(v, int):
                    counters[k] = counters.get(k, 0) + v
    samples = [json.loads(l) for l in telemetry.path.read_text().splitlines() if l.strip()] if telemetry.path.exists() else []
    peak = {}
    for s in samples:
        for k, v in (s.get("cpu") or {}).items():
            peak[k] = max(peak.get(k, 0.0), v)
    pool_wait = max((int((s.get("pool") or {}).get("cl_waiting") or 0) for s in samples), default=0)
    db_waits = {}
    for s in samples:
        for k, v in (s.get("db_active") or {}).items():
            db_waits[k] = max(db_waits.get(k, 0), v)
    error_rate = work_fail / work_total if work_total else 1.0
    passed = work_total > 0 and error_rate < ERROR_LIMIT and work_p95 < P95_LIMIT_MS and not telemetry.guard_tripped
    return {
        "stage": name,
        "mode": mode,
        "users": users,
        "window_s": window,
        "work_requests": work_total,
        "work_failures": work_fail,
        "error_rate": round(error_rate, 4),
        "worst_p95_ms": work_p95,
        "passed": passed,
        "counters": counters,
        "peak_cpu_percent": dict(sorted(peak.items(), key=lambda kv: -kv[1])[:14]),
        "pool_max_cl_waiting": pool_wait,
        "db_peak_active_by_wait": dict(sorted(db_waits.items(), key=lambda kv: -kv[1])[:10]),
        "live_health_failures": sum(1 for s in samples if s.get("live_healthy") is False),
        "min_mem_available": min((s.get("mem_available", 1) for s in samples), default=None),
        "requests": per,
        "errors": errors[:12],
    }


def write_report(run_dir, args, seed, results, reconcile):
    lines = ["# Tutum testi — " + run_dir.name, ""]
    lines.append(
        f"İzolə stack: {len(APPS)} app × {args.app_cpus} CPU, DB {args.db_cpus} CPU, PgBouncer 1 CPU, edge 0.75 CPU · "
        f"canlı image · imtahan `{seed.get('exam_slug')}` ({seed.get('questions')} sual) · "
        f"jurnal: {len(seed.get('journals') or [])} müəllim · düşünmə {args.think_min}-{args.think_max} s"
    )
    lines.append("")
    lines.append("| Pillə | VU | Pəncərə | İş sorğusu | Xəta | Xəta % | ən pis p95 ms | Nəticə |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---|")
    for r in results:
        lines.append(
            f"| {r['stage']} | {r['users']} | {r['window_s']} s | {r['work_requests']} | {r['work_failures']} | "
            f"{r['error_rate'] * 100:.2f} | {r['worst_p95_ms']:.0f} | {'✅ keçdi' if r['passed'] else '❌ keçmədi'} |"
        )
    for r in results:
        lines += ["", f"## {r['stage']}", "", "| Sorğu | Say | Xəta | p50 | p95 | p99 | max | rps |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
        for q in r["requests"]:
            lines.append(f"| {q['method']} {q['name']} | {q['count']} | {q['fail']} | {q['p50']:.0f} | {q['p95']:.0f} | {q['p99']:.0f} | {q['max']} | {q['rps']} |")
        if r["errors"]:
            lines += ["", "Xətalar:", ""] + [f"- {e['count']} × {e['name']}: `{e['error']}`" for e in r["errors"]]
        lines += [
            "",
            f"Sayğaclar: `{json.dumps(r['counters'])}`",
            f"Pik CPU %: `{json.dumps(r['peak_cpu_percent'])}`",
            f"PgBouncer max cl_waiting: {r['pool_max_cl_waiting']} · DB pik aktiv (gözləmə növü): `{json.dumps(r['db_peak_active_by_wait'])}`",
            f"Canlı sağlamlıq uğursuzluğu: {r['live_health_failures']} · min boş RAM: {r['min_mem_available']}",
        ]
    lines += ["", "## Bütövlük (reconcile)", "", "```", json.dumps(reconcile, indent=2, ensure_ascii=False), "```"]
    (run_dir / "summary.md").write_text("\n".join(lines))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--plan", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--harness", required=True)
    p.add_argument("--app-cpus", type=float, default=1.0)
    p.add_argument("--db-cpus", type=float, default=2.0)
    p.add_argument("--login-lane", type=int, default=4)
    p.add_argument("--teachers", type=int, default=0)
    p.add_argument("--questions", type=int, default=10)
    p.add_argument("--think-min", type=float, default=8)
    p.add_argument("--think-max", type=float, default=20)
    p.add_argument("--preauth-rate", type=float, default=8)
    p.add_argument("--users-per-worker", type=int, default=1500)
    p.add_argument("--max-workers", type=int, default=4)
    p.add_argument("--student-start", type=int, default=1000)
    p.add_argument("--stop-on-fail", action="store_true")
    p.add_argument("--stop-mode-on-fail", action="store_true")
    p.add_argument("--preauth", choices=("login", "session"), default="session")
    p.add_argument("--cabinet-seconds", type=int, default=180)
    p.add_argument("--overlay", action="store_true")
    p.add_argument("--repo", default="")
    p.add_argument("--out", required=True)
    p.add_argument("--replicas", type=int, default=4)
    args = p.parse_args()
    global APPS
    APPS = tuple(f"app{i}" for i in range(1, max(1, args.replicas) + 1))

    if not live_health():
        raise SystemExit("canlı sistem sağlam deyil — test başlamır")
    if mem_available() < 0.3:
        raise SystemExit("boş RAM < 30% — test başlamır")
    run_dir = CAP / "runs" / args.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stack = Stack(args)
    results, reconcile, seed = [], {}, {}
    try:
        stack.build()
        stack.up()
        log("migrate")
        stack.manage("migrate", "--noinput", timeout=1800)
        stack.psql("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")
        log("seed")
        seed_path = run_dir / "seed.json"
        stack.manage(
            "shell", "-c", "exec(open('/harness/cap_seed.py').read())",
            env={
                "CAP_RUN_ID": args.run_id.replace("_", "-"),
                "CAP_TEACHERS": str(args.teachers),
                "CAP_EXAM_QUESTIONS": str(args.questions),
                "CAP_JOURNAL_STUDENT_OFFSET": "45000",
                "CAP_OUT": seed_path.as_posix().replace(str(CAP), "/capacity"),
            },
        )
        seed = json.loads(seed_path.read_text())
        log("seeded", json.dumps({k: v for k, v in seed.items() if k != "journals"}), "journals", len(seed.get("journals") or []))
        stack.psql("ANALYZE")
        stack.restart_apps()
        cursor = args.student_start
        failed_modes = set()
        t_cursor = 0
        for i, spec in enumerate([s.strip() for s in args.plan.split(",") if s.strip()], start=1):
            if spec.split(":")[0] in failed_modes:
                log("SKIP", spec, "(bu rejim əvvəlki pillədə keçmədi)")
                continue
            if not live_health():
                log("canlı sistem sağlam deyil — qalan pillələr ləğv edildi")
                break
            result, cursor = run_stage(stack, args, spec, i, cursor, seed_path, run_dir, t_cursor)
            t_cursor = result.get("t_cursor_next", 0)
            results.append(result)
            write_report(run_dir, args, seed, results, {})
            if result["guard_tripped"]:
                break
            if not result["passed"]:
                if args.stop_on_fail:
                    log("pillə keçmədi — dayanılır (--stop-on-fail)")
                    break
                if args.stop_mode_on_fail:
                    failed_modes.add(result["mode"])
            if cursor > 44000:
                cursor = args.student_start
            time.sleep(20)
        log("reconcile")
        stack.manage(
            "shell", "-c", "exec(open('/harness/cap_reconcile.py').read())",
            env={"CAP_RUN_DIR": run_dir.as_posix().replace(str(CAP), "/capacity")},
        )
        rec = run_dir / "reconciliation.json"
        reconcile = json.loads(rec.read_text()) if rec.exists() else {"error": "reconcile output missing"}
    finally:
        stop_generators()
        logs_dir = run_dir / "app-logs"
        logs_dir.mkdir(exist_ok=True)
        for svc in APPS + ("db", "pool", "edge"):
            text = sh(["docker", "logs", "--since", "3h", f"{PROJECT}-{svc}-1"], capture=True, check=False, merge=True)
            lines = [l for l in (text or "").splitlines() if any(w in l for w in ("ERROR", "Error", "error", "WARNING", "FATAL", "LOG:  duration", "lock", "Traceback", "503", "concurrency"))]
            (logs_dir / f"{svc}.log").write_text("\n".join(lines[-4000:]))
        stack.stop()
        log("stack stopped; live healthy:", live_health())
        write_report(run_dir, args, seed, results, reconcile)
        for item in run_dir.iterdir():
            if item.is_file() and not item.name.endswith(".html"):
                shutil.copy2(item, out / item.name)
        if logs_dir.exists():
            shutil.copytree(logs_dir, out / "app-logs", dirs_exist_ok=True)
        (out / "results.json").write_text(json.dumps({"results": results, "reconcile": reconcile}, indent=2))
        print((run_dir / "summary.md").read_text())


if __name__ == "__main__":
    main()
