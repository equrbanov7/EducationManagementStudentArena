"""Tutum testi hesabatı — pillə xülasəsi (locust CSV + telemetriya) və summary.md.

`cap_run.py`-dan ayrılıb (modul ölçüsü). Host-da (runner) işləyir.
"""

from __future__ import annotations

import csv
import json

P95_LIMIT_MS = 2500
ERROR_LIMIT = 0.01


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
        f"İzolə stack: {args.replicas} app × {args.app_cpus} CPU, DB {args.db_cpus} CPU, PgBouncer 1 CPU, edge 0.75 CPU · "
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
