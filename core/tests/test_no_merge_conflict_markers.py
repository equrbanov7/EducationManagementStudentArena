"""Git konflikt işarələri (``<<<<<<<`` / ``>>>>>>>``) heç bir mənbə faylında qalmamalıdır.

2026-10-07: birləşmə zamanı iki şablonda işarələr commit-ə düşmüşdü və səhifənin yuxarısında
görünürdü — bu qapı onu CI-da tutur.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCAN_DIRS = ("apps", "core", "config", "templates", "static", "locale", "scripts", "tests", "docker")
SUFFIXES = {".py", ".html", ".txt", ".js", ".css", ".po", ".json", ".yml", ".yaml", ".sh", ".md", ".conf"}
MARKERS = ("<<<<<<< ", ">>>>>>> ")


def test_no_merge_conflict_markers():
    offenders = []
    for top in SCAN_DIRS:
        base = ROOT / top
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.suffix not in SUFFIXES or not path.is_file() or "node_modules" in path.parts:
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (UnicodeDecodeError, OSError):
                continue
            for number, line in enumerate(lines, start=1):
                if line.startswith(MARKERS):
                    offenders.append(f"{path.relative_to(ROOT)}:{number}")
    assert offenders == [], f"konflikt işarələri qalıb: {offenders[:20]}"
