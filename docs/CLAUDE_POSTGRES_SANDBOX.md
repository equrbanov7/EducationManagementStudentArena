# Claude PostgreSQL sandbox

Bu repo üçün ayrıca Docker Compose əsaslı agent mühiti var. Məqsəd Claude Code
və ya başqa AI agentinin kilidli Linux sandbox-da `apt`, `sudo`, `postgres`,
`initdb` axtarmasına ehtiyac qalmadan real PostgreSQL ilə test işlədə bilməsidir.

## Tez istifadə

```bash
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

- `postgres:16-alpine` servisi: host portu default `55432`
- `redis:7-alpine` servisi: host portu default `56379`
- `agent` servisi: repo `/app` kimi mount olunur, Python test/dev paketləri,
  `postgresql-client`, `redis-tools`, `git`, `nodejs` və `npm` hazır gəlir

Default bağlantı:

```text
DATABASE_URL=postgres://emsarena_agent:emsarena_agent_password@postgres:5432/emsarena_agent
```

Host-dan qoşulmaq üçün:

```bash
psql postgres://emsarena_agent:emsarena_agent_password@127.0.0.1:55432/emsarena_agent
```

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

Port və DB adını environment dəyişənləri ilə dəyişə bilərsiniz:

```bash
AGENT_POSTGRES_PORT=65432 \
AGENT_POSTGRES_DB=emsarena_rls \
./scripts/claude_pg_sandbox.sh up
```

Tam təmizləmə:

```bash
./scripts/claude_pg_sandbox.sh clean
```

`clean` sandbox PostgreSQL/Redis volume-larını silir. Layihə fayllarına toxunmur.
