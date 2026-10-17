#!/usr/bin/env python3
"""Claude Code PreToolUse hook — keyfiyyət qapılarını agentlərdən qoruyur (sahib 2026-10-17).

1. Lint / CI / arxitektura qapılarının faylları (aşağıdakı PROTECTED) dəyişdiriləndə — Edit/Write/
   MultiEdit/NotebookEdit və ya həmin fayla yazan Bash əmri — qərar «ask» olur: dəyişiklik bloklanmır,
   sahib təsdiqləməlidir. Məqsəd: agent testi keçirmək üçün qapını zəiflətməsin (qaydanı yox, kodu düzəlt).
   `EMS_GATE_GUARD=warn` → yalnız xəbərdarlıq (gecə avtonom işləri dayanmasın); `off` → söndürülür.
2. `git commit/push --no-verify` (və `git commit -n`) HƏMİŞƏ rədd edilir — yoxlamalar yan keçilmir.

Heç bir şəbəkə çağırışı yoxdur, heç nə yazmır; yalnız stdin JSON oxuyur və stdout-a qərar JSON-u verir.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import shlex
import sys

PROTECTED = (
    # CI qapıları (prod-*.yml əməliyyat workflow-ları buraya DAXİL DEYİL — onlar tez-tez dəyişir).
    ".github/workflows/_lint.yml",
    ".github/workflows/_security.yml",
    ".github/workflows/_unit-tests.yml",
    ".github/workflows/_js-tests.yml",
    ".github/workflows/_secret-scan.yml",
    ".github/workflows/_rls-txn-pool.yml",
    ".github/workflows/ci.yml",
    ".github/workflows/codeql.yml",
    # Arxitektura / ölçü / i18n / inline qapıları və onların baseline-ları.
    "scripts/check_*.py",
    "scripts/module_deps.py",
    "scripts/public_api_boundaries.py",
    "scripts/context_map.py",
    "scripts/*_baseline.json",
    # Lint / format konfiqurasiyası.
    "pyproject.toml",
    "setup.cfg",
    ".flake8",
    ".isort.cfg",
    ".pre-commit-config.yaml",
    "pytest.ini",
    ".coveragerc",
)

_REDIRECT = re.compile(r">>?\s*([^\s;&|]+)")


def _rel(path: str) -> str:
    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    path = os.path.normpath(path)
    if os.path.isabs(path):
        try:
            path = os.path.relpath(path, root)
        except ValueError:
            return path
    return path.replace(os.sep, "/")


def _protected(path: str) -> bool:
    rel = _rel(path)
    return any(fnmatch.fnmatch(rel, pattern) for pattern in PROTECTED)


_SEPARATORS = {";", "&&", "||", "|", "&"}
#: Dəyər alan bayraqlar — onlardan sonrakı token (məs. commit mesajı) bayraq kimi oxunmur.
_VALUE_FLAGS = {"-m", "--message", "-F", "--file", "-C", "-c", "--author", "--date", "-t", "--template"}


def _segments(command: str):
    """`;`, `&&`, `||`, `|` və yeni sətir üzrə hissələr — dırnaq içindəki mətnə (commit mesajı) toxunmadan."""
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|\n")
        lexer.whitespace_split = True
        lexer.whitespace = " \t\r"
        tokens = list(lexer)
    except ValueError:
        tokens = command.split()
    current: list[str] = []
    for token in tokens:
        if token and (token in _SEPARATORS or set(token) <= set(";&|\n")):
            if current:
                yield current
            current = []
            continue
        current.append(token)
    if current:
        yield current


def _flags(rest: list[str]) -> list[str]:
    out, skip = [], False
    for token in rest:
        if skip:
            skip = False
            continue
        if token in _VALUE_FLAGS:
            skip = True
            continue
        if token.startswith("-"):
            out.append(token)
    return out


def _no_verify(command: str) -> bool:
    for tokens in _segments(command):
        if "git" not in tokens:
            continue
        rest = tokens[tokens.index("git") + 1 :]
        flags = _flags(rest)
        sub = next((t for t in rest if not t.startswith("-") and t not in flags), "")
        if sub not in ("commit", "push", "merge", "rebase", "cherry-pick", "am"):
            continue
        if "--no-verify" in flags:
            return True
        if sub == "commit" and any(re.fullmatch(r"-[a-zA-Z]*n[a-zA-Z]*", t) and "m" not in t for t in flags):
            return True
    return False


def _bash_touches_protected(command: str) -> list[str]:
    """Yalnız qorunan FAYLIN ÖZÜNƏ yazan əmrlər: `> f`, `sed -i … f`, `tee f`, `cp/mv … f`, `rm f`, `truncate f`.

    Qapı skriptini İŞLƏTMƏK (`python scripts/check_module_size.py >/dev/null`) tutulmur.
    """
    hits = set()
    for target in _REDIRECT.findall(command):
        if _protected(target.strip("'\"")):
            hits.add(_rel(target.strip("'\"")))
    for tokens in _segments(command):
        if not tokens:
            continue
        head = os.path.basename(tokens[0])
        args = [t for t in tokens[1:] if not t.startswith("-")]
        if head == "sed" and any(t == "-i" or t.startswith("-i") for t in tokens[1:]):
            targets = args
        elif head in ("tee", "rm", "truncate"):
            targets = args
        elif head in ("cp", "mv", "ln") and args:
            targets = args[-1:]
        else:
            targets = []
        hits.update(_rel(t) for t in targets if _protected(t))
    return sorted(hits)


def _decision(kind: str, reason: str) -> None:
    out = {"hookSpecificOutput": {"hookEventName": "PreToolUse"}}
    if kind == "warn":
        out["systemMessage"] = reason
        out["hookSpecificOutput"]["additionalContext"] = reason
    else:
        out["hookSpecificOutput"]["permissionDecision"] = kind
        out["hookSpecificOutput"]["permissionDecisionReason"] = reason
    print(json.dumps(out, ensure_ascii=False))


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    tool = payload.get("tool_name", "")
    data = payload.get("tool_input") or {}
    mode = (os.environ.get("EMS_GATE_GUARD") or "ask").strip().lower()

    if tool == "Bash":
        command = str(data.get("command") or "")
        if _no_verify(command):
            _decision(
                "deny",
                "Qapı qoruyucusu: `--no-verify` / `git commit -n` qadağandır — yoxlamaları yan keçmə, "
                "xətanı düzəlt (CLAUDE.md, layihə qaydaları).",
            )
            return 0
        hits = _bash_touches_protected(command)
        if hits and mode != "off":
            reason = (
                "Qapı qoruyucusu: bu əmr keyfiyyət qapısı faylına yaza bilər (" + ", ".join(hits) + "). "
                "Qapını zəiflətmək əvəzinə kodu düzəlt; dəyişiklik həqiqətən lazımdırsa sahib təsdiqləsin."
            )
            _decision("warn" if mode == "warn" else "ask", reason)
        return 0

    if tool in ("Edit", "Write", "MultiEdit", "NotebookEdit") and mode != "off":
        path = str(data.get("file_path") or data.get("notebook_path") or "")
        if path and _protected(path):
            reason = (
                f"Qapı qoruyucusu: «{_rel(path)}» lint/CI/arxitektura qapısıdır. Testi keçirmək üçün qaydanı "
                "zəiflətmə — kodu düzəlt. Dəyişiklik qəsdəndirsə (məs. yeni qapı, CVE istisnası) sahib təsdiqləsin."
            )
            _decision("warn" if mode == "warn" else "ask", reason)
    return 0


if __name__ == "__main__":
    sys.exit(main())
