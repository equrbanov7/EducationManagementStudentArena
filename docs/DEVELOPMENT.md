# Lokal inkişaf mühiti

Dev serveri (`ddaphne`, klon bazası, portlar) üçün bax: [`DEV_RUN.md`](DEV_RUN.md).
Testlər üçün agent Postgres sandbox-u: `scripts/claude_pg_sandbox.sh` (`:55432`).

## venv ↔ requirements sinxronu (`scripts/check_venv_sync.py`)

**Problem (audit 2026-09-13, F-T3).** `requirements/test.txt`-də pinlənmiş
`pytest-cov` və `pytest-timeout` lokal venv-də quraşdırılmamışdı. Nəticə:
lokal coverage ölçülə bilmirdi, `@pytest.mark.timeout(...)` heç vaxt tətbiq
olunmurdu — CI-də timeout-la kəsilən test lokalda «keçirdi». `pip install -r`
bir dəfə çağırılır, sonra requirements dəyişir, venv isə geridə qalır.

**Yoxlama (məsləhət xarakterli, CI-yə qoşulmur):**

```bash
venv/bin/python scripts/check_venv_sync.py              # requirements/test.txt (-r base.txt daxil)
venv/bin/python scripts/check_venv_sync.py -r requirements/local.txt
venv/bin/python scripts/check_venv_sync.py --strict     # sürüşmə varsa exit 1 (pre-commit hook üçün)
venv/bin/python scripts/check_venv_sync.py --extras     # requirements-də olmayan quraşdırılmış paketlər
```

Çıxış: **ÇATIŞMIR** (requirements-də var, venv-də yox) və **VERSİYA FƏRQİ**
(`==` pin başqa versiya ilə qarşılanır). `>=`/`~=` pinlər yalnız mövcudluq
üzrə yoxlanır. Skript alt-proses açmır — `importlib.metadata` ilə cari
interpretatorun paketlərini oxuyur, ona görə **məhz `venv/bin/python` ilə**
çağırın (sistem `python3` sistem paketlərini yoxlayar).

**Düzəliş:** `venv/bin/pip install -r requirements/test.txt`
(və ya skriptin sonda çap etdiyi əmr). Requirements faylını hər dəyişdirəndə
(o cümlədən `git pull`-dan sonra) bu yoxlamanı çalışdırmaq kifayətdir.

Əlaqəli: `pyproject.toml`-dakı `timeout` markeri plugin olmayanda sadəcə
qeydsiz qalır (xəbərdarlıq yoxdur) — yəni sinxron pozulanda pytest özü heç nə
demir; bu skript o boşluğu görünən edir.
