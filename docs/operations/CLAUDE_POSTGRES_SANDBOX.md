# Claude PostgreSQL sandbox

Bu repo üçün ayrıca Docker Compose əsaslı agent mühiti var. Məqsəd Claude Code
və ya başqa AI agentinin kilidli Linux sandbox-da `apt`, `sudo`, `postgres`,
`initdb` axtarmasına ehtiyac qalmadan real PostgreSQL ilə test işlədə bilməsidir.

## Tez istifadə

Parol repoda saxlanmır (audit 2026-09-28 AD-03) — əvvəlcə `.env.agent`-i yükləyin
(bax «Parol və şəbəkə» bölməsi):

```bash
set -a; . ./.env.agent; set +a        # AGENT_POSTGRES_PASSWORD shell-ə export olunur
./scripts/claude_pg_sandbox.sh up
./scripts/claude_pg_sandbox.sh shell
```

Shell açıldıqdan sonra konteyner içində bunlar hazır olur:

```bash
echo "$DATABASE_URL"
python manage.py check
pytest --ds=config.settings.test -m postgres apps/organizations/tests/test_rls.py
psql
```

Host-dan birbaşa işlətmək üçün:

```bash
./scripts/claude_pg_sandbox.sh check
./scripts/claude_pg_sandbox.sh migrate
./scripts/claude_pg_sandbox.sh postgres-tests
./scripts/claude_pg_sandbox.sh test apps/organizations/tests/test_rls.py -m postgres
```

## Nə yaradır

- `postgres:16-alpine` servisi: host portu default `127.0.0.1:55432` (yalnız loopback)
- `redis:7-alpine` servisi: host portu default `127.0.0.1:56379` (yalnız loopback)
- `agent` servisi: repo `/app` kimi mount olunur, Python test/dev paketləri,
  `postgresql-client`, `redis-tools`, `git`, `nodejs` və `npm` hazır gəlir

Bağlantı (parol `.env.agent`-dəki `AGENT_POSTGRES_PASSWORD`-dir):

```text
DATABASE_URL=postgres://emsarena_agent:${AGENT_POSTGRES_PASSWORD}@postgres:5432/emsarena_agent
```

Host-dan qoşulmaq üçün:

```bash
set -a; . ./.env.agent; set +a
psql "postgres://emsarena_agent:${AGENT_POSTGRES_PASSWORD}@127.0.0.1:55432/emsarena_agent"
```

## Parol və şəbəkə (audit 2026-09-28 AD-03)

Sandbox-da istehsal nüsxəsi bazaları (`ems_prodcopy`, `ems_restore_*` …) saxlanılır —
yəni tələbələrin şəxsi məlumatı və qiymətləri. Əvvəl port `0.0.0.0:55432`-də açıq
idi və parolun defoltu repoda yazılmışdı: eyni Wi-Fi/LAN-dakı istənilən cihaz
qoşula bilərdi. İndi:

- `docker-compose.agent.yml` portları yalnız `127.0.0.1`-ə bağlayır (Postgres və Redis);
- `AGENT_POSTGRES_PASSWORD` **məcburidir** (`${AGENT_POSTGRES_PASSWORD:?…}`) — təyin
  edilməyibsə `docker compose` heç bir əmri icra etmir;
- parol repoda deyil, izlənməyən `.env.agent` faylındadır (`.gitignore`-dakı `.env.*`
  onu artıq əhatə edir):

```bash
# bir dəfə (sahib): fayl yarat, yalnız özün oxu
printf 'AGENT_POSTGRES_PASSWORD=%s\n' "<parol>" > .env.agent
chmod 600 .env.agent
```

Compose-u birbaşa işlədəndə faylı `--env-file` ilə verin:

```bash
docker compose --env-file .env.agent -f docker-compose.agent.yml -p emsarena-agent ps
```

`scripts/claude_pg_sandbox.sh` hələ `--env-file` ötürmür — ondan əvvəl dəyişəni shell-ə
export edin (`set -a; . ./.env.agent; set +a`).

### İşləyən konteyneri yeni qaydaya keçirmək (yalnız sahib, agentlər işləmədikdə)

Port bağlaması konteyner **yenidən yaradılanda** tətbiq olunur. Paralel agentlər
sandbox-dan istifadə edərkən bunu etməyin:

```bash
set -a; . ./.env.agent; set +a
docker compose --env-file .env.agent -f docker-compose.agent.yml -p emsarena-agent \
  up -d --force-recreate postgres redis
docker ps --format '{{.Names}}\t{{.Ports}}' | grep emsarena-agent   # 127.0.0.1:55432->5432 olmalıdır
```

Volume (`agent_postgres_data`) və bazalar qalır. **Diqqət:** `POSTGRES_PASSWORD` yalnız
ilk `initdb` zamanı tətbiq olunur — mövcud volume-da rolun parolu köhnə qalır.
Uyğunluq üçün ilk addımda `.env.agent`-ə mövcud parolu yazın (loopback bağlaması
LAN ifşasını onsuz da bağlayır). Parolu dəyişmək istəsəniz, recreate-dən sonra:

```bash
docker exec -it emsarena-agent-postgres psql -U emsarena_agent -d postgres \
  -c "ALTER ROLE emsarena_agent PASSWORD '<yeni parol>'"
# sonra .env.agent-i və agentlərin DATABASE_URL-ini yeniləyin
```

Əlavə tövsiyələr: artıq lazım olmayan `ems_prodcopy` / `ems_restore_*` bazalarını
silin (`dropdb`), macOS firewall-u yandırın (System Settings → Network → Firewall),
lokal dump-ları `chmod 600` saxlayın (`find backups -type f -perm -004` boş olmalıdır).

## Claude Code ilə istifadə

Ən sadə yol Claude-a bu repo daxilində aşağıdakı əmrlərdən istifadə etməyi
tapşırmaqdır:

```bash
./scripts/claude_pg_sandbox.sh shell
./scripts/claude_pg_sandbox.sh test <test yolu və ya pytest arg-ları>
./scripts/claude_pg_sandbox.sh postgres-tests
```

Claude Code-u birbaşa konteyner içində işə salmaq istəyirsinizsə, `shell`
açıldıqdan sonra öz Claude autentifikasiya üsulunuzu ayrıca qurun. Bu repo
host-un `~/.claude` və ya başqa şəxsi token qovluqlarını avtomatik mount etmir.

## Parametrləri dəyişmək

Port və DB adını environment dəyişənləri ilə dəyişə bilərsiniz (parol yenə
`.env.agent`-dən gəlir):

```bash
set -a; . ./.env.agent; set +a
AGENT_POSTGRES_PORT=65432 \
AGENT_POSTGRES_DB=emsarena_rls \
./scripts/claude_pg_sandbox.sh up
```

Tam təmizləmə:

```bash
./scripts/claude_pg_sandbox.sh clean
```

`clean` sandbox PostgreSQL/Redis volume-larını silir. Layihə fayllarına toxunmur.
