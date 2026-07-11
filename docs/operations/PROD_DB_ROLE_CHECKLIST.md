# Production `.env` və DB rolu — servere qoşulanda ediləcək addımlar

**Kontekst:** 2026-07-11 Codex auditinin **EXAM-P0-01** tapıntısı — tətbiq
PostgreSQL-ə bootstrap **superuser** rolu ilə qoşulur. Superuser `FORCE ROW
LEVEL SECURITY` olduqda belə RLS-i yan keçir, yəni bir queryset-də tenant
filtri unudulsa bütün tenantların məlumatı açıla bilər. Kod tərəfi hazırdır;
aşağıdakı operator addımları atılana qədər **prod hələ superuser ilə işləyir**.

> Bu bir dəfəlik quraşdırma tapşırığıdır. Servere sudo/DB girişi olan zaman
> ardıcıllıqla icra et; hər addım idempotentdir.

## 1. `.env`-ə əlavə ediləcək dəyişənlər

Serverdəki `.env` faylına (adətən `/opt/emsarena/app/.env` və ya
`APP_DIR/.env`) bu sətirləri əlavə et:

```dotenv
# ── Tətbiq DB rolu (EXAM-P0-01) ──────────────────────────────────────────
# Runtime üçün RLS-ə TAM TABE olan ayrıca rol. Boş qalsa köhnə (superuser)
# davranışa düşür və app loglarında organizations.W011 xəbərdarlığı çıxır.
APP_DATABASE_USER=emsarena_app
APP_DATABASE_PASSWORD=<GÜCLÜ-TƏSADÜFİ-PAROL>

# DB rol yoxlaması: əvvəlcə warn, rol qurulub yoxlanandan SONRA error et.
EMS_DB_ROLE_ENFORCE=warn
```

`APP_DATABASE_PASSWORD` üçün güclü təsadüfi parol:

```sh
openssl rand -base64 32
```

Digər dəyişənlərin tamlığı `docker-compose.prod.yml` ilə tutuşdurulub —
`.env.production.example` referans faylı bütün məcburi dəyişənləri (SECRET_KEY,
POSTGRES_*, REDIS_PASSWORD, ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS, SITE_URL,
GRAFANA_ADMIN_PASSWORD) əhatə edir; yeni əlavələr yalnız yuxarıdakı üç sətirdir.

## 2. DB rolunu yaradan skripti işə sal

Postgres konteynerinin işlədiyi hostda (rol artıq varsa yalnız atributları
yeniləyir):

```sh
cd <APP_DIR>
APP_DATABASE_USER=emsarena_app \
APP_DATABASE_PASSWORD='<yuxarıdakı parol>' \
  ./scripts/provision-app-db-role.sh
```

Gözlənilən çıxışın sonu:

```
 rolname      | rolsuper | rolbypassrls | rolcanlogin
--------------+----------+--------------+-------------
 emsarena_app | f        | f            | t
```

`rolsuper=f` **və** `rolbypassrls=f` olması vacibdir — əks halda RLS yenə
bypass olunur.

> Fresh (boş) DB volume-da bu addım avtomatikdir:
> `docker/postgres-init/10-create-app-role.sh` `APP_DATABASE_USER` təyin
> olunubsa rolu initdb zamanı yaradır.

## 3. Stack-i yenidən qaldır

```sh
docker compose -f docker-compose.prod.yml up -d app celery_worker celery_beat
```

Miqrasiyalar avtomatik olaraq **owner** rolu ilə gedir
(`MIGRATION_DATABASE_URL`, `docker/release.sh` içində
`EMS_DB_ROLE_ENFORCE=off`) — DDL üçün superuser burada qanunidir. Runtime isə
`emsarena_app` rolu ilə qoşulur.

## 4. Yoxla və sərtləşdir

App loglarında artıq `organizations.W011` xəbərdarlığı **olmamalıdır**:

```sh
docker compose -f docker-compose.prod.yml logs app | grep -i W011   # boş olmalı
```

Təsdiqlədikdən sonra `.env`-də sərtliyi artır ki, gələcəkdə səhvən superuser-ə
qayıdış deploy-u **bloklasın**:

```dotenv
EMS_DB_ROLE_ENFORCE=error
```

və app-ı yenidən başlat. Bundan sonra `manage.py check` (deploy-da işləyir)
superuser aşkarlasa `organizations.E011` ilə fail edəcək.

## 5. Geri qaytarma (lazım olsa)

`.env`-dən `APP_DATABASE_USER`/`APP_DATABASE_PASSWORD`-u sil (və ya
`EMS_DB_ROLE_ENFORCE=warn`) → app yenidən köhnə davranışa (bootstrap user)
düşür. Rolu DB-dən silmək lazım deyil.

---

**Əlaqəli:** audit [EXAM-P0-01](../audits/2026-07-11-codex-tam-audit/FIX_REPORT_2026-07-11.md),
RLS coverage [migration 0017](../../apps/organizations/migrations/0017_rls_exam_gap_tables.py),
system check `apps/organizations/checks.py`.
