"""Fixture sütun tiplərini real MyEdu sxemi ilə tutuşdurur.

`legacy_int` / `legacy_flag` tip üzrə **fail-closed**-dur: mətn görəndə
`legacy_rehearsal_source_value_type_unsupported` atır.  Ona görə
`test_rehearsal_source_integration.py`-dakı birdəfəlik MariaDB fixture-ı real
sxemdəki tipləri GÜZGÜLƏMƏLİDİR.  Uyğunsuzluq başqa cür yalnız 15-17 dəqiqəlik
MariaDB determinizm dəstində üzə çıxır — bu skript onu saniyələrdə tapır.

⚠️ YALNIZ LOKAL: `emsarena-legacy-source-rehearsal` konteynerinin işləməsini
tələb edir, ona görə CI qapısı DEYİL.

İstifadə::

    DATABASE_URL="sqlite:///tmp/typecheck.sqlite3" \
        python scripts/check_legacy_fixture_types.py
"""

import ast
import os
import pathlib
import subprocess
import sys

# Repo kökündən işə salınır; `config` paketi tapılsın deyə yol əlavə olunur.
sys.path.insert(0, os.getcwd())
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

REPO = pathlib.Path(".")
TEST = REPO / "apps/legacy_import/tests/test_rehearsal_source_integration.py"
CONTRACTS = REPO / "apps/legacy_import/services/field_contracts.py"


def literal_map(source: str, name: str) -> dict[str, tuple[str, ...]]:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
    return {}


def contracts_by_table() -> dict[str, tuple[str, ...]]:
    """Kontraktları modulun ÖZÜNDƏN oxu — bəziləri dəyişən istinadı işlədir."""
    import django

    django.setup()
    from apps.legacy_import.services import field_contracts as fc

    out: dict[str, tuple[str, ...]] = {}
    for name in dir(fc):
        obj = getattr(fc, name)
        table = getattr(obj, "source_table", None)
        fields = getattr(obj, "allowed_fields", None)
        if isinstance(table, str) and isinstance(fields, tuple):
            out[table] = tuple(dict.fromkeys(out.get(table, ()) + tuple(fields)))
    return out


def real_types(table: str) -> dict[str, str]:
    cmd = [
        "docker",
        "exec",
        "emsarena-legacy-source-rehearsal",
        "sh",
        "-c",
        f'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" myedudb -N -e '
        f'"SELECT column_name, data_type FROM information_schema.columns '
        f"WHERE table_schema='myedudb' AND table_name='{table}';\"",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    out = {}
    for line in res.stdout.strip().splitlines():
        parts = line.split("\t")
        if len(parts) == 2:
            out[parts[0]] = parts[1]
    return out


# Bilinən-zərərsiz uyğunsuzluqlar: hər biri üçün SƏBƏB yazılıb.  Siyahıya
# yalnız SÜBUT edilmiş hal əlavə edilir — «yəqin işləyir» kifayət deyil.
_BENIGN = {
    ("groups", "start_year"): (
        "MySQL YEAR sütunu sürücüdə onsuz da Python int qaytarır; " "fixture-dakı BIGINT eyni tipi verir."
    ),
    ("semestr_jurnal", "is_current"): (
        "`_legacy_flag_text` ilə MƏTN kimi oxunur (V9: is_current heç vaxt "
        "köçürülmür) — həm int, həm str qəbul edilir."
    ),
    ("students", "sex"): "proyeksiyada var, KODDA heç yerdə oxunmur.",
    ("students", "join_date"): "proyeksiyada var, KODDA heç yerdə oxunmur.",
    ("students", "status"): "proyeksiyada var, KODDA heç yerdə oxunmur.",
    ("workers", "sex"): "proyeksiyada var, KODDA heç yerdə oxunmur.",
}

INT_TYPES = {"int", "bigint", "smallint", "tinyint", "mediumint"}
FLOAT_TYPES = {"float", "double", "decimal"}
DT_TYPES = {"datetime", "timestamp"}


def main() -> int:
    test_src = TEST.read_text()
    ints = literal_map(test_src, "_INT_COLUMNS")
    floats = literal_map(test_src, "_FLOAT_COLUMNS")
    datetimes = literal_map(test_src, "_DATETIME_COLUMNS")
    times = literal_map(test_src, "_TIME_COLUMNS")
    contracts = contracts_by_table()

    problems = []
    benign = []
    for table, fields in sorted(contracts.items()):
        actual = real_types(table)
        if not actual:
            print(f"  ⏭  {table}: real sxemdə tapılmadı (ötürülür)")
            continue
        for field in fields:
            if field == "id":
                continue
            real = actual.get(field)
            if real is None:
                problems.append(f"{table}.{field}: kontraktda var, REAL SXEMDƏ YOXDUR")
                continue
            declared = (
                "int"
                if field in ints.get(table, ())
                else (
                    "float"
                    if field in floats.get(table, ())
                    else (
                        "datetime"
                        if field in datetimes.get(table, ())
                        else "time" if field in times.get(table, ()) else "varchar"
                    )
                )
            )
            expected = (
                "int"
                if real in INT_TYPES
                else (
                    "float"
                    if real in FLOAT_TYPES
                    else "datetime" if real in DT_TYPES else "time" if real == "time" else "varchar"
                )
            )
            if declared != expected:
                reason = _BENIGN.get((table, field))
                if reason:
                    benign.append(f"{table}.{field}: {reason}")
                    continue
                problems.append(f"{table}.{field}: real={real} (→{expected}) amma fixture={declared}")

    print()
    if benign:
        print(f"ℹ️  {len(benign)} bilinən-zərərsiz fərq (sübutlu):")
        for b in benign:
            print(f"   · {b}")
        print()
    if problems:
        print(f"❌ {len(problems)} uyğunsuzluq:")
        for p in problems:
            print(f"   • {p}")
        return 1
    print("✅ Bütün kontrakt sahələri fixture tipləri ilə uyğundur.")
    return 0


raise SystemExit(main())
