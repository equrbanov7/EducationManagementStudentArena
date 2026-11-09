"""Read GitHub run receipts, retaining command IDs and safe numeric summaries only.

No dispatch, database connection, repair command, or raw log output is performed.
Workflow success is execution evidence, not proof of current academic correctness.
"""

import concurrent.futures
import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = "equrbanov7/EducationManagementStudentArena"
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def run(args):
    return subprocess.run(args, capture_output=True, text=True, check=True, timeout=90).stdout


def read_log(item):
    safe = {k: item[k] for k in ("id", "head_sha", "status", "conclusion", "created_at")}
    try:
        raw = run(["gh", "run", "view", str(item["id"]), "--repo", REPO, "--log"])
    except (subprocess.SubprocessError, OSError):
        return {**safe, "log_available": False}
    safe.update(log_available=True, log_sha256=hashlib.sha256(raw.encode()).hexdigest())
    summaries = []
    for line in raw.splitlines():
        content = line.split("\t", 2)[-1]
        content = re.sub(r"^\d{4}-\d{2}-\d{2}T\S+Z\s+", "", ANSI.sub("", content)).strip()
        match = re.fullmatch(r"COMMAND: ([a-z][a-z0-9_]+)", content)
        if match:
            safe["command"] = match[1]
        match = re.fullmatch(r"APPLY: (true|false)", content)
        if match:
            safe["requested_apply"] = match[1] == "true"
        match = re.fullmatch(r"([a-z][a-z0-9_]+): (.+)", content)
        if not match:
            continue
        pairs = {}
        for token in match[2].split():
            field = re.fullmatch(r"([a-z][a-z0-9_]*)=(-?\d+(?:\.\d+)?)", token)
            if field:
                pairs[field[1]] = float(field[2]) if "." in field[2] else int(field[2])
            else:
                field = re.fullmatch(r"(mode|status|result)=(apply|dry_run|undo|[a-z_]+)", token)
                if field:
                    pairs[field[1]] = field[2]
                field = re.fullmatch(r"(batch)=([a-z]+-\d{8}-\d{6}-[a-f0-9]{4,12})", token)
                if field:
                    pairs[field[1]] = field[2]
        if pairs and {"prefix": match[1], **pairs} not in summaries:
            summaries.append({"prefix": match[1], **pairs})
    safe["safe_summaries"] = summaries
    return safe


def main():
    pages = json.loads(
        run(
            [
                "gh",
                "api",
                f"repos/{REPO}/actions/workflows/prod-data-ops.yml/runs?per_page=100&created=%3E%3D2026-11-05",
                "--paginate",
                "--slurp",
            ]
        )
    )
    rows = [r for page in pages for r in page["workflow_runs"]]
    existing = HERE / "recent_operation_runs.json"
    cached = {r["id"]: r for r in json.loads(existing.read_text()).get("runs", [])} if existing.exists() else {}
    pending = [r for r in rows if r["id"] not in cached or not cached[r["id"]].get("log_available")]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        for index, result in enumerate(executor.map(read_log, pending), 1):
            cached[result["id"]] = result
            if index % 10 == 0:
                print(json.dumps({"logs_read": index, "pending_total": len(pending)}), flush=True)
    output = {
        "scope": "prod-data-ops workflow since2026-11-05UTC; GET only",
        "not_current_state_proof": True,
        "runs": sorted(cached.values(), key=lambda r: r["created_at"]),
    }
    existing.write_text(json.dumps(output, indent=2) + "\n")
    summary = Counter(
        (r.get("command", "unknown"), str(r.get("requested_apply")), r["conclusion"]) for r in output["runs"]
    )
    print(
        json.dumps(
            {
                "run_count": len(output["runs"]),
                "by_command": [
                    {"command": k[0], "requested_apply": k[1], "conclusion": k[2], "count": v}
                    for k, v in sorted(summary.items())
                ],
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
