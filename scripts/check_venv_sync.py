#!/usr/bin/env python3
"""venv ↔ requirements sinxron yoxlaması (məsləhət xarakterli).

Niyə? (audit 2026-09-13, F-T3 / H1)
-----------------------------------
`requirements/test.txt`-də `pytest-cov` və `pytest-timeout` pinlənsə də lokal
venv-də quraşdırılmamışdı: lokal coverage ölçülə bilmirdi, `@pytest.mark.timeout`
heç vaxt tətbiq olunmurdu → CI-də timeout-la kəsilən test lokalda «keçirdi».
Bu skript quraşdırılmış paketləri (`importlib.metadata`, yəni `pip freeze`
ekvivalenti — alt-proses yoxdur) requirements faylı ilə tutuşdurur və
ÇATIŞMAYAN / VERSİYASI FƏRQLİ paketləri sadalayır.

İstifadə
--------
    venv/bin/python scripts/check_venv_sync.py                 # requirements/test.txt
    venv/bin/python scripts/check_venv_sync.py -r requirements/local.txt
    venv/bin/python scripts/check_venv_sync.py --strict        # sürüşmə varsa exit 1
    venv/bin/python scripts/check_venv_sync.py --extras        # requirements-də olmayan paketləri də göstər

Skript hansı interpretator ilə çağırılırsa ONUN mühitini yoxlayır — venv-i
yoxlamaq üçün `venv/bin/python` ilə çağırın. `-r` daxilolmaları rekursiv
oxunur; `>=`/`~=` kimi qeyri-dəqiq pinlər yalnız mövcudluq üzrə yoxlanır.
Defolt rejim MƏSLƏHƏTDİR (exit 0) — CI-yə qoşulmur (`docs/DEVELOPMENT.md`).
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REQUIREMENTS = ROOT / "requirements" / "test.txt"

# `name[extra]==1.2.3  # şərh` → (name, operator, version)
_SPEC_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]*\])?\s*(==|>=|<=|~=|!=|>|<)?\s*([^\s;#]*)")


def _display(path: Path) -> str:
    """Kök daxilindəki yol nisbi, kənar yol olduğu kimi (`-r` ilə kənar fayl da verilə bilər)."""
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def normalize(name: str) -> str:
    """PEP 503 ad normallaşdırması: `Pillow` == `pillow`, `typing_extensions` == `typing-extensions`."""
    return re.sub(r"[-_.]+", "-", name).lower()


@dataclass(frozen=True)
class Requirement:
    name: str
    operator: str
    version: str
    source: str

    @property
    def exact(self) -> bool:
        return self.operator == "=="


def parse_requirements(path: Path, *, _seen: set[Path] | None = None) -> list[Requirement]:
    """`-r` daxilolmalarını rekursiv açaraq bütün paket sətirlərini qaytarır."""
    seen = _seen if _seen is not None else set()
    path = path.resolve()
    if path in seen:
        return []
    seen.add(path)
    requirements: list[Requirement] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith(("-r", "--requirement")):
            included = line.split(None, 1)[1].strip() if " " in line else line[2:].strip()
            requirements.extend(parse_requirements(path.parent / included, _seen=seen))
            continue
        if line.startswith("-"):
            continue  # --index-url, --extra-index-url, -e … — paket deyil
        match = _SPEC_RE.match(line)
        if not match or not match.group(1):
            continue
        name, operator, version = match.group(1), match.group(2) or "", match.group(3) or ""
        requirements.append(Requirement(normalize(name), operator, version, _display(path)))
    return requirements


def installed_versions() -> dict[str, str]:
    """Cari interpretatorun görə bildiyi bütün distribusiyalar (name → version)."""
    found: dict[str, str] = {}
    for dist in metadata.distributions():
        name = dist.metadata["Name"] if dist.metadata else None
        if name:
            found[normalize(name)] = dist.version
    return found


def compare(requirements: list[Requirement], installed: dict[str, str]):
    """(missing, mismatched) — mismatched yalnız `==` pinlər üçün."""
    missing: list[Requirement] = []
    mismatched: list[tuple[Requirement, str]] = []
    for requirement in requirements:
        current = installed.get(requirement.name)
        if current is None:
            missing.append(requirement)
        elif requirement.exact and current != requirement.version:
            mismatched.append((requirement, current))
    return missing, mismatched


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-r", "--requirements", type=Path, default=DEFAULT_REQUIREMENTS)
    parser.add_argument("--strict", action="store_true", help="sürüşmə varsa exit 1 (defolt: məsləhət, exit 0)")
    parser.add_argument(
        "--extras", action="store_true", help="requirements-də olmayan quraşdırılmış paketləri də göstər"
    )
    args = parser.parse_args(argv)

    requirements_path = args.requirements if args.requirements.is_absolute() else ROOT / args.requirements
    if not requirements_path.exists():
        print(f"✖ requirements faylı tapılmadı: {requirements_path}")
        return 2

    requirements = parse_requirements(requirements_path)
    installed = installed_versions()
    missing, mismatched = compare(requirements, installed)

    print(f"Interpretator: {sys.executable}")
    print(f"Requirements: {_display(requirements_path)} ({len(requirements)} paket, -r daxil)")

    if missing:
        print(f"\n✖ ÇATIŞMIR ({len(missing)}):")
        for requirement in sorted(missing, key=lambda item: item.name):
            spec = f"{requirement.operator}{requirement.version}" if requirement.operator else ""
            print(f"  {requirement.name}{spec}    ({requirement.source})")
    if mismatched:
        print(f"\n✖ VERSİYA FƏRQİ ({len(mismatched)}):")
        for requirement, current in sorted(mismatched, key=lambda item: item[0].name):
            print(
                f"  {requirement.name}: quraşdırılıb {current}, tələb =={requirement.version}    ({requirement.source})"
            )
    if args.extras:
        required_names = {requirement.name for requirement in requirements}
        extras = sorted(name for name in installed if name not in required_names)
        print(f"\nℹ requirements-də olmayan ({len(extras)}): " + ", ".join(extras))

    if not missing and not mismatched:
        print("\n✔ venv requirements ilə sinxrondur.")
        return 0

    print(f"\nDüzəliş: {Path(sys.executable).parent / 'pip'} install -r {_display(requirements_path)}")
    return 1 if args.strict else 0


if __name__ == "__main__":
    sys.exit(main())
