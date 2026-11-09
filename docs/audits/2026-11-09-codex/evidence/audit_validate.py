"""Validate report artifacts offline; never import Django or contact a database."""

import ast
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
AUDIT = HERE.parent
ROOT = HERE.parents[3]
BASE = "45892d9011e6e31d9ad39f9999fa3cb7f6717f84"
PREFIX = "docs/audits/2026-11-09-codex/"
FORBIDDEN = {
    "first_name",
    "last_name",
    "father_name",
    "full_name",
    "fin",
    "pin",
    "email",
    "phone",
    "username",
    "password",
    "birth_date",
    "date_of_birth",
    "topic",
    "body_text",
}
IDENTIFIERS = {"student_id", "source_student_id", "mark_id", "source_point_id", "enrollment_id"}
GRADE_FIELDS = {
    "score",
    "current_score",
    "source_score",
    "old_score",
    "new_score",
    "points",
    "grade",
    "value",
    "point",
    "winner_score",
    "raw_score",
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect(value, path, violations):
    if isinstance(value, dict):
        individual = bool(IDENTIFIERS.intersection(value))
        for key, item in value.items():
            location = f"{path}.{key}"
            if key.lower() in FORBIDDEN and item not in (None, [], {}, ""):
                violations.append(location)
            if individual and key in GRADE_FIELDS and isinstance(item, (int, float, str)):
                violations.append(location)
            inspect(item, location, violations)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            inspect(item, f"{path}[{index}]", violations)


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout


def main():
    violations = []
    files = [p for p in AUDIT.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    json_files = [p for p in files if p.suffix == ".json" and p.name != "audit_validation.json"]
    for path in json_files:
        inspect(json.loads(path.read_text()), path.name, violations)
    checks = {"json_identity_and_individual_grade_fields_absent": not violations}
    broken = []
    for path in AUDIT.glob("*.md"):
        for match in re.finditer(r"\]\(([^)]+)\)", path.read_text()):
            target = match[1].split("#", 1)[0]
            if target and not re.match(r"[a-z]+:", target) and not (path.parent / target).exists():
                broken.append([path.name, target])
    checks["markdown_local_links_resolve"] = not broken
    scripts = [p for p in files if p.suffix == ".py"]
    for path in scripts:
        ast.parse(path.read_text(), filename=str(path))
    checks["python_ast_valid_and_under_600_lines"] = all(len(p.read_text().splitlines()) <= 600 for p in scripts)
    changed = git("diff", "--name-only", BASE).splitlines()
    untracked = git("ls-files", "--others", "--exclude-standard").splitlines()
    checks["all_git_changes_inside_authorized_audit_directory"] = all(p.startswith(PREFIX) for p in changed + untracked)
    report = (AUDIT / "REPORT_AZ.md").read_text()
    reviewed = re.findall(r"\| `((?:operations/)?REVIEWED_[^`]+\.md)` \|", report)
    expected = {
        str(p.relative_to(ROOT / "docs")) for p in (ROOT / "docs").rglob("REVIEWED_*.md") if "audits" not in p.parts
    }
    checks["all_19_reviewed_documents_have_status_rows"] = len(reviewed) == 19 and set(reviewed) == expected
    checks["all_19_findings_have_registry_rows"] = all(f"| F-{i:02} |" in report for i in range(1, 20))
    manifests = {}
    for name in ("cells_validation.json", "syllabus_validation.json"):
        value = json.loads((HERE / name).read_text())
        entries = value.get("artifacts", [])
        manifests[name] = all(
            (AUDIT / row["path"]).is_file() and digest(AUDIT / row["path"]) == row["sha256"] for row in entries
        )
    checks["owned_manifest_hashes_current"] = all(manifests.values())
    result = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "read_head": BASE,
        "all_passed": all(checks.values()),
        "checks": checks,
        "json_files": len(json_files),
        "python_files": len(scripts),
        "reviewed_documents": len(reviewed),
        "privacy_violations_paths_only": violations,
        "broken_local_links": broken,
        "owned_manifest_checks": manifests,
        "database_writes": 0,
        "application_files_changed": 0 if checks["all_git_changes_inside_authorized_audit_directory"] else None,
        "artifacts": [
            {"path": str(p.relative_to(AUDIT)), "bytes": p.stat().st_size, "sha256": digest(p)}
            for p in sorted(files)
            if p.name != "audit_validation.json"
        ],
        "limits": [
            "Structural/privacy validation does not prove academic correctness or full production coverage.",
            "No application tests or test database creation in report-only phase.",
        ],
    }
    (HERE / "audit_validation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: value for key, value in result.items() if key != "artifacts"}, ensure_ascii=False))
    if not result["all_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
