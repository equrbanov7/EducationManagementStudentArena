# Canlı viktorina — yük testi (LX-BE, 2026-09-29)

Harness: `scripts/load/live_exam_load.py` (+ `scripts/load/ws_client.py` — stdlib asyncio WebSocket müştərisi;
venv-də `websockets`/`aiohttp`/`httpx` yoxdur, yeni asılılıq əlavə olunmayıb; HTTP üçün mövcud `requests`).

## Nə edir

Real UI-nin etdiyini HTTP + WebSocket üzərindən edir — **hamısı eyni İP-dən** (sinif NAT-ı):

1. **Host**: `/accounts/login/muellim/` → `POST /live/create/<slug>/` (force_new) → `POST …/settings/`
   (2 uyğun sual yazılı cavab, `multi_scoring=partial`, autoplay) → lobby + play WS → `POST …/start/`.
   Hər sual: hamı cavab veribsə server özü reveal edir, əks halda `ends_at + 0.18 s`-də `POST …/reveal/` (UI autoMode);
   reveal-dən sonra `--reveal-hold` saniyə → `POST …/next/` → … → `finished`.
2. **N oyunçu**: `GET /live/join/<pin>/` → `POST …/enter/` (CSRF + cookie-lər) → `GET /live/wait/<pin>/` → lobby WS →
   `game_started` (+ `redirect_jitter_ms` səpələnməsi) → `GET /live/play/<pin>/` → play WS → `GET /live/state/<pin>/`.
   Cavablar: tək seçim (~65% düz), çox seçim (dəqiq / qismən / düz+səhv, `max_select`-ə qədər), yazılı (dəqiq,
   kiçik hərf, BÖYÜK+durğu, səhv, uzadılmış), ~3% cavabsız; `answer_ms: 0` saxta göndərilir (server vaxtı işləməlidir).
   `--flaky p`: hər reveal-dən sonra oyunçuların p hissəsi TCP-ni close kadrı olmadan qırır, 0.5–2 s sonra yenidən
   qoşulur + state snapshot (UI kimi); socket qopuqdursa cavab HTTP fallback ilə gedir.
3. **Yoxlama** (DB, yalnız oxu): hər oyunçu `score == Σ awarded_points`; sual başına təkrar cavab yoxdur; final
   `top` sırası = tie qaydası (`score ↓, qoşulma ↑, id ↑`); oyunçuya gələn final `rank` DB sırası ilə eyni; **server
   recompute** — saxlanan hər cavab eyni qaydalarla (`calculate_answer_score` / `calculate_typed_score`) yenidən
   hesablanır və `awarded_points`/`is_correct` ilə tutuşdurulur.
4. **Ölçülər**: `answer_ack` (göndəriş → `answer_saved`), `fanout:reveal|question` (paketin `server_time` → telefonda
   qəbul), `fanout:game_started` (host start → telefon), HTTP gecikmələri, status kodları, gözlənilməz WS bağlanmaları.

## Necə işlətmək

```bash
# 1) Baza (agent sandbox), miqrasiya, demo seed
PGPASSWORD=… psql -h 127.0.0.1 -p 55432 -U emsarena_agent -d postgres -c "CREATE DATABASE ems_lxbe_load"
export DJANGO_SETTINGS_MODULE=config.settings.local DEBUG=True USE_REDIS=False \
       DATABASE_URL=postgres://emsarena_agent:emsarena_agent_password@127.0.0.1:55432/ems_lxbe_load
venv/bin/python manage.py migrate && venv/bin/python manage.py seed_live_demo

# 2) Server (ayrı terminal). ASGI_THREADS=12 — prod ilə eyni (docker-compose.prod.yml)
ASGI_THREADS=12 venv/bin/daphne -b 127.0.0.1 -p 8019 config.asgi:application
#    Real Redis kanal qatı üçün: docker compose -f docker-compose.agent.yml --env-file .env.agent up -d redis
#    və serveri + harness-i USE_REDIS=True REDIS_URL=redis://127.0.0.1:56379/0 ilə işlədin.

# 3) Yük (eyni env — DB yoxlaması üçün)
venv/bin/python scripts/load/live_exam_load.py --players 90 --burst --out /tmp/lx90.json
venv/bin/python scripts/load/live_exam_load.py --players 150 --flaky 0.1 --same-ua
```

Açarlar: `--players N`, `--burst` (hamı pəncərə açılandan ~1.3 s ərzində), `--flaky p`, `--same-ua` (bütün telefonlar
eyni User-Agent — ən pis hal), `--reveal-hold s` (`-1` = UI kimi `next_question_at`-a qədər), `--typed-count k`,
`--skip-rate`, `--no-recompute` (köhnə kod versiyası üçün yalnız SQL invariantları), `--out file.json`.
Çıxış kodu 0 = yoxlama problemsiz və tapşırıq xətası yoxdur.

## Mühit

Apple M3 Pro (11 nüvə, 18 GB), PostgreSQL 16 (docker, **pgbouncer YOX**, `CONN_MAX_AGE=0` → hər DB çağırışı yeni
backend prosesi), tək daphne prosesi, `ASGI_THREADS=12`, `DEBUG=True` (sorğu jurnalı əlavə yük), yük generatoru eyni
maşında. 8 sual (2-si yazılı, 2-si çox seçimli), sual vaxtı 15 s. Prod (pgbouncer, ayrı maşın, `DEBUG=False`)
bundan yaxşı olmalıdır — rəqəmlər ehtiyatlı yuxarı həddir.

## Nəticələr (ms; p50 / p95 / max)

| Ssenari | Qoşulma OK | answer ack | reveal fan-out | sual fan-out | xətalar | yoxlama |
|---|---|---|---|---|---|---|
| **N=90**, burst, in-memory kanal | 90/90 | 32 / 56 / 101 | 28 / 118 / 119 | 25 / 31 / 32 | 0 | 687 cavab, problem 0 |
| **N=90**, burst, typed söndürülü | 90/90 | 30 / 88 / 203 | 24 / 27 / 28 | 29 / 31 / 31 | 0 | 693, 0 |
| **N=90**, UI tempi, flaky 10%, **Redis** | 90/90 | 34 / 59 / 186 | 31 / 114 / 115 | 28 / 43 / 62 | 0 (71 qopma → 71 bərpa, p50 30) | 699, 0 |
| **N=150**, burst, in-memory | 150/150 | 122 / 421 / 502 | 47 / 60 / 124 | 38 / 45 / 57 | 0 | 1171, 0 |
| **N=150**, burst, **Redis** | 150/150 | 196 / 391 / 480 | 43 / 148 / 150 | 33 / 130 / 132 | 0 | 1160, 0 |
| **N=150**, burst, flaky 5%, **Redis** (son kod) | 150/150 | 158 / 256 / 295 | 39 / 47 / 49 | 41 / 175 / 179 | 0 (62 qopma → 62 bərpa, p50 28) | 1166, 0 |
| **N=150**, UI tempi, flaky 10%, **eyni UA** | 150/150 | 27 / 52 / 318 | 46 / 51 / 122 | 40 / 146 / 147 | 0 (110 qopma → 110 bərpa, p50 19; 4429 = 0) | 1159, 0 |

Oyun başlanğıcı (N=150 burst, in-memory): `game_started` fan-out 149 / 151 ms; `GET player_screen` 460 / 703;
`GET state` 541 / 739; play WS qoşulma 653 / 746. Qoşulma mərhələsi (150 eyni anda join): 3.7 s; `POST enter`
467 / 1916 / 2658 (4 fərqli UA) — **eyni UA ilə 1169 / 7142 / 7724** (aşağıda R1).

### Əvvəl / sonra (eyni harness, eyni parametrlər: N=90, burst, in-memory, typed söndürülü)

| Ölçü | HEAD (dəyişiklikdən əvvəl, `cfe06c13`) | İndi |
|---|---|---|
| answer ack | 700 / 1408 / 1647 | **30 / 88 / 203** |
| reveal fan-out | 664 / 1220 / 1530 | **24 / 27 / 28** |
| play WS qoşulma | 707 / 1191 / 1240 | **105 / 162 / 199** |
| `GET state` (oyun başlanğıcı) | 31 / 99 / 187 | 130 / 200 / 206 ¹ |
| max iştirakçı | 100 (101-ci → 403) | 200 |

¹ Endpoint özü daha ucuzdur (8 data sorğusu, əvvəl ~10); fərq yük formasındandır — əvvəl WS qoşulmaları tək thread-də
növbəyə düzüldüyü üçün HTTP sorğuları ~1.2 s-ə yayılırdı, indi 90 telefonun hamısı eyni anda gəlir.

HEAD-də N=150 mümkün deyildi: 101-ci oyunçu `participant_limit_reached` (403) — müəllim limiti 100-dən yuxarı qaldıra
bilmirdi. İndi default və müəllim tavanı 200-dür.

## Tapıntılar və tövsiyələr (ops / digər sahiblər)

* **R1 — RequestQueueMiddleware anonim oyunçuları seriyalaşdırır.** Anonim POST-un aktor açarı `İP|UA|path`dir
  (`core/middleware.py`); bir NAT arxasında eyni telefon modelli tələbələr (eyni UA) BİR növbəyə düşür + qlobal
  `REQUEST_QUEUE_GLOBAL_UNSAFE_LIMIT=8`. Ölçü: eyni UA-da `POST enter` p95 **7.1 s** (4 UA ilə 1.9 s). Tövsiyə:
  `REQUEST_QUEUE_EXCLUDED_PATH_PREFIXES`-ə `/live/join/,/live/play/,/live/wait/` (bu endpoint-lərin öz idempotentliyi
  var: sətir kilidləri, unikal məhdudiyyət, rate-limit) və ya anonim aktor açarına `live_client_id` cookie-si.
* **R2 — join İP limiti sinif ölçüsünə bərabərdir.** `LIVE_EXAM_JOIN_IP_RATE_LIMIT=150/10m`: 150 tələbə + səhv
  ad/yenidən cəhd → 151-ci 429. Tövsiyə: ≥ `400/10m`.
* **R3 — pgbouncer + `ASGI_THREADS`.** Cavab yolu ~8 data sorğusu + RLS (3) + 2 say; lokal ack p95-in çoxu
  `CONN_MAX_AGE=0` ilə hər çağırışda yeni PostgreSQL backend-idir. Prod pgbouncer ilə bu ucuzdur; 150+ üçün
  `ASGI_THREADS` 12 → 16–24 (pgbouncer hovuzu ilə birgə ölçülsün).
* **R4 — HTTP admission control** (`MAX_INFLIGHT_REQUESTS`, prod 24): testlərdə 503 görünmədi (`game_started`
  yönləndirməsi `redirect_jitter_ms` ilə 1.5 s-ə səpələnir). FE bu sahəni istifadə etməlidir.
* **R5 — Redis kanal qatı** (prod) in-memory ilə eyni sıradadır; reveal/final şəxsi xəritəsi proses başına bir dəfə
  seriyalaşdırılır (channels_redis), consumer başına DB sorğusu yoxdur.
