# Audit yoxlamalarının təkrarı

Əsas mənbə: `/Users/elvin/Developer/EMSArena`. Mövcud `.env` və real bazanın URL-i ilə audit/test əmri işlədilməməlidir. Audit boyu DATABASE_URL proses səviyyəsində ayrıca konteynerə yönəldildi.

## İzolə mühit

- Ayrı yaradılmış PostgreSQL 16 konteyneri: `CODEX_TEST_emsarena_pg_20260912`.
- Yalnız loopback portu: `127.0.0.1:55439`.
- Baza: `codex_audit`; Django test runner ayrıca `test_codex_audit` və xdist worker bazaları yaradır.
- Saxlama: həmin konteynerin ayrıca tmpfs-i; real PostgreSQL volume-ları mount edilməyib.
- MEDIA_ROOT: hər proses üçün `tempfile.mkdtemp(prefix="CODEX_TEST_final_media_")`.
- Email: locmem; Celery: test settings-in eager/in-memory konfiqurasiyası.
- Brauzer demo settings: ayrıca `audit_settings`, Clarity boş, DEBUG=True, UNIVERSITY_MODE=True.
- Regresiya settings: `config.settings.test` üzərindən ayrıca `audit_final_settings`; yalnız test media/email və test SECRET_KEY override olunur. Clarity-nin server HTML testi üçün baza setting-i saxlanır; test runner brauzer açmır.

Parol və baza URL-i bu sənəddən götürülmür: yalnız yeni yaradılmış disposable mühitin məlumatlarından istifadə edilməlidir. Real backup və DB bu testə qoşulmamalıdır.

## Tam PostgreSQL dəsti

Repo venv Python 3.11.6, Django 5.2.17, pytest 9.1.1, pytest-django 4.12.0, xdist 3.8.0 ilə işlədildi. Repo `requirements/test.txt` faylında olan pytest-timeout 2.4.0 ayrıca `/tmp` target-də yüklənərək son testdə aktiv edildi. Paketlərin real tətbiq venv-ində versiyaları dəyişdirilmədi.

Mühit düzgün qurulduqdan sonra test arqumentləri:

```text
venv/bin/pytest apps core tests -n 4 --dist loadfile -p no:cacheprovider -m 'not mariadb' -q --tb=short
```

`DATABASE_URL`, `DJANGO_SETTINGS_MODULE=audit_final_settings`, `USE_REDIS=False`, `PYTHONDONTWRITEBYTECODE=1` həmin proses üçün verildi. `PYTHONPATH` ayrıca settings və timeout plugin qovluqlarını ehtiva etdi.

## SQLite və coverage

```text
DATABASE_URL=sqlite://
DJANGO_SETTINGS_MODULE=config.settings.test
pytest apps core tests --no-migrations -p no:cacheprovider -m 'not postgres and not mariadb' -q --tb=short
```

Əmr audit wrapper-i vasitəsilə işlədildi: wrapper `django.setup()`-dan sonra müvəqqəti MEDIA_ROOT və locmem email təyin edir. Coverage apps/core/config üzrə aparıldı; hesabatdan tests və migrations çıxarıldı. SQLite-nin uğursuzluqları gizlədilmir; istehsal qərarı üçün PostgreSQL nəticəsi əsasdır.

## Məcburi kod qapıları

```text
venv/bin/black --check .
venv/bin/isort --check-only --profile black .
venv/bin/flake8 .
venv/bin/python scripts/check_module_size.py --check
venv/bin/python scripts/module_deps.py --check
venv/bin/python scripts/check_i18n_catalogs.py
venv/bin/python scripts/check_worker_atomic_coverage.py --check
```

Django `check` və `makemigrations --check --dry-run` yalnız disposable URL və settings ilə işlədildi.

## Brauzer və sintetik HTTP yoxlaması

Playwright CLI ayrıca `CODEX_TEST_emsarena` sessiyasında 127.0.0.1:8765 ünvanına qoşuldu. Session cookie-ləri yalnız sintetik hesablar üçün Django Client.force_login ilə yaradıldı. Prod sessiyası/parolu istifadə edilmədi. Tələbə/müəllim/statistika və mərkəz importu, 390 px ekran, CSV tətbiqi və drag/drop idempotent preview yoxlandı. AI düyməsi real provider-ə sorğu göndərmək üçün basılmadı.

HTTP smoke: ThreadPoolExecutor(5), 60 lokal GET, dörd tələbə bölməsi; latency və statuslar `synthetic-http-smoke.json` faylındadır. Production capacity nəticəsi deyil.

## Real bazanın yalnız oxu yoxlaması

Yalnız mövcud `emsarena-postgres` konteynerində `psql -X` istifadə edildi. Hər prosesə `PGOPTIONS=-c default_transaction_read_only=on -c statement_timeout=20000` verildi; son say sorğusu ayrıca `BEGIN READ ONLY` içində idi. DB istifadəçi/parolu stdout-a çıxarılmadı. COUNT-lar və əlaqə tutuşdurmaları nəticə fayllarında var. Yanlış cədvəl adı ilə ilk son-say sorğusu xəta verdi, düz cədvəl adı ilə təkrar oxu tamamlandı; heç bir yazı olmadı.

## Təhlükəsizlik skanları

`pip-audit --path <repo-venv-site-packages> --format json` ayrıca scanner venv-dən işlədildi. Nəticə: `dependency-audit.json`.

`bandit -r apps core config -x 'tests,migrations' --severity-level high --confidence-level high -f json` nəticəsi: `bandit-high.json`. Aşağı/orta severity üçün təmiz nəticə iddia edilmir.

## Migrasiya round-trip

Yalnız `codex_audit` + port 55439 yoxlanıldıqdan sonra MigrationExecutor planı iki yeni registrar migrasiyası ilə məhdudlaşdırıldı: 0072/0071 geri, sonra 0072-yə irəli. Sintetik final score/score-entry snapshot-ları eyni qaldı. Yeni sheet cədvəli geriyə migrasiyada silinir; real data yazıldıqdan sonra bu downgrade təhlükəsiz deyil.

Gzip backup bütövlüyü tam streaming oxu və SHA-256 ilə yoxlandı; restore edilmədi. Backup faylları açılıb yenidən yazılmadı.

## Yekun təmizləmə

Auditin disposable PostgreSQL konteyneri silinib, brauzer sessiyası və test serveri bağlanıb. Təkrar üçün yeni ayrıca mühit yaradılmalıdır. Mövcud real konteynerlər saxlanılıb.
