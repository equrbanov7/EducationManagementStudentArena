# İnfrastruktur/əməliyyat handoff — kod ilə həll OLUNMAYAN işlər

> **Re-audit qeydi:** Bu handoff ilkin fix dalğasından sonrakı vəziyyəti təsvir
> edir və bəzi scope-ları artıq natamamdır. Cross-FK/M2M RLS, audit attribution
> tamper-i, lab grade clamp, faktiki Cloudflare topologiyası və deploy drift-i
> üçün cari authoritative plan
> [REAUDIT_REPORT_AZ_2026-07-11.md](./REAUDIT_REPORT_AZ_2026-07-11.md)-dədir.

Bu sənəd 2026-07-11 auditinin **kod dəyişikliyi ilə bağlana bilməyən** qalan
bəndlərini toplayır. Bunlar server girişi, CI/CD infrastruktur qərarı, yük
generatoru və ya məhsul-səviyyə dizayn tələb edir — hamısı **sənə** qalır.

## 1. Server/DB əməliyyatları

| İş | Nə etmək lazımdır | Status |
|---|---|---|
| **DB rolu (EXAM-P0-01)** | `.env`-ə APP_DATABASE_USER/PASSWORD, `scripts/provision-app-db-role.sh`, sonra `EMS_DB_ROLE_ENFORCE=error` | Kod hazır, [checklist](../../operations/PROD_DB_ROLE_CHECKLIST.md) |
| **Köhnə CF iptables** | `scripts/deploy/remote_deploy.sh`-dakı `EMSARENA-CF-WEB` zənciri serverdə varsa köhnə CF qalığıdır — nəzərdən keçir/sil (CF istifadə olunmur) | Serverdə yoxla |
| **Yeni migrasiyaların tətbiqi** | `organizations 0017/0018/0019`, `exams 0045/0046/0047` prod DB-yə migrate olunmalıdır (release.sh avtomatik edir) | Deploy zamanı |

## 2. Off-site backup + restore drill (audit P1)

- Hazırda backup eyni hostdadır (host/ransomware itkisinə davamsız).
- **Lazım:** off-site şifrələnmiş backup (S3/başqa region), aylıq **restore drill**, ölçülmüş **RPO/RTO**, media+DB point-in-time consistency.
- Bu, real infrastruktur + ehtiyat saxlama yeri tələb edir — kod deyil.

## 3. Immutable image promotion + rollback (audit P1)

- Hazırda deploy source-u serverə rsync edib yerində rebuild edir; test edilmiş image digest promote OLUNMUR.
- **Lazım:** CI-də build → scan → eyni digest-i staging→prod promote; avtomatik rollback gate; migration backward-compat siyasəti.
- Bu, CI/CD registry + infrastruktur qərarıdır.

## 4. Yük/capacity testi (audit performans — ÖLÇÜ YOXDUR)

- `docs/performance/FAZA4_BASELINE_RESULTS.md` boşdur; k6 default 1 VU; stress script yalnız `/ping`+`/health` vurur.
- **Lazım (real yük generatoru ilə):**
  - Real imtahan yolu: PIN → start → question → autosave → submit → result.
  - 100 VU×30dəq, 500 VU×15dəq, 1000 VU spike, 1 saat soak.
  - 1000 paralel WebSocket (supervision/live/final-center), reconnect storm.
  - Ölç: p50/p95/p99, error rate, DB conn, PgBouncer pool, Redis latency, Celery queue lag, data-loss invariantı.
- Nəticələrə görə **PgBouncer/Redis/Celery ölçüləndirmə**.

## 5. Observability tamamlanması (audit P1)

- Kod tərəfi əlavə olundu: exam biznes SLI Counter-ları (`apps/exams/metrics.py` — start/submit/autosave/result/PIN/supervision).
- **Qalan (Grafana/Prometheus konfiqurasiyası):** bu metriklər üçün dashboard + alert qaydaları; Celery queue lag, beat heartbeat, Redis/PgBouncer exporter alertləri; multi-replica scrape (hər replika `/metrics/`).

## 6. Məhsul-həssas / dizayn tələb edən kod işləri

Bunlar kodla həll oluna bilər, amma **məhsul qərarı + browser E2E verifikasiyası**
tələb etdiyi üçün bu dalğada edilmədi:

| ID | İş | Niyə təxirə salındı |
|---|---|---|
| EXAM-P1-09 | Access code şifrələmə | Access code müəllim-görünən paylaşılan sirdir (tələbələrə göstərilir) — birtərəfli hash giriş axışını sındırır. Düzgün həll: PIN-lər kimi Fernet-at-rest + display/form/compare yollarının tam izlənməsi. |
| EXAM-P1-04 | Server-side per-question timer | Per-question deadline modeli + "question shown" siqnalı + save enforcement + take_exam UI-nin browser E2E verifikasiyası. Feature-ölçülü. |
| EXAM-P1-06 | Autosave server OCC | Client `base_revision` göndərməli + 409 UI-si; server tək başına dormant qalır. Multi-tab browser verifikasiyası lazımdır. |
| EXAM-P1-01 | Formal exam state machine | draft→review→approved→published→ended keçidləri; böyük refaktor, mövcud lifecycle_status və publish yollarına toxunur. |
| EXAM-P1-11 | Client telemetry proctoring | Dizayn məhdudiyyəti — server attestation olmadan client telemetriyası spoof edilə bilər; ayrıca beta capability kimi. |
| EXAM-P1-14 | Coding sandbox limitləri | Coding prod-da disabled; aktivləşdirmə üçün executor semaphore/memory backpressure — ayrı iş. |
| EXAM-P1-16 | Sync OCR fallback | Artıq `JOB_WORKER_PICKUP_TIMEOUT` ilə bounded, konfiqurasiya olunan **qəsdi** resilience (worker-ölü halı). Heavy OCR-ı inline-dan çıxarmaq resilience-i pozur — məhsul tradeoff qərarı. |

## 7. Assignment/project/lab concurrency (qismən)

- Kod tərəfi: grade clamp + deterministic bulk ordering **edildi** (Wave B).
- **Qalan:** concurrent max-attempt bypass üçün row lock / unique attempt number — hər modulun submission axını fərqli olduğu üçün ayrıca, ölçülü dəyişiklik lazımdır (audit bunu ayrıca bənd kimi qeyd edir).

## 8. Digər keyfiyyət gate-ləri (audit P1)

- JS unit/lint/type pipeline yoxdur; a11y automation (axe/pa11y) yoxdur; query-budget testləri çox azdır.
- Privacy/retention schedule + istifadəçi-facing Terms/Privacy səhifələri.
- Bunlar CI konfiqurasiyası + məhsul/hüquq işidir.

## 9. Tövsiyə olunan sequence — icra statusu (2026-07-11, davam)

İstifadəçinin tələbi ilə tövsiyə olunan kod ardıcıllığına başlanıldı. Təhlükəsiz
(test ilə doğrulanan, kritik axışı riskə atmayan) hissələr icra edildi;
browser-E2E və ya məhsul-qərarı tələb edənlər dəqiq işarələndi.

**Bitdi (kod + test, push olundu):**
- Appeal 3-günlük pəncərə UX: bağlananda read-only nəticə/appeal baxışı + aydın
  xəbərdarlıq; create_appeal servisində defense-in-depth pəncərə invariantı.
- Seq1 — grade-event append-only ledger + original grader identity (exams 0048,
  organizations 0022 RLS); appeal reviewer independence müəllif + ilk grader-ə.
- Seq2 — full delivered snapshot v2 (mətn/media/variant mətni/label dondurulur;
  `delivered_question_view` accessor; geriyə-uyğun).
- Seq6 (qismən) — exam biznes SLI-ları call site-lara wire olunub (start/submit/
  autosave/result/PIN/supervision); `attach_test_result_summaries` query-budget
  testi mövcuddur.

**Qalan — browser E2E tələb edir (kritik exam-taking axışı, vizual verifikasiya):**
- Seq3 — formal exam/result state machine + atomik publish gate (draft/review/
  published/appeal_closed). Böyük; publish UX browser-də yoxlanmalıdır.
- Seq4 — server-authoritative per-question deadline + autosave OCC/409 conflict
  UX. JS + multi-tab browser E2E tələb edir.
- Seq2-nin qalanı — nəticə/appeal template-inin canlı `q.text` əvəzinə
  `delivered_question_view`-dən render etməsi (vizual regresiya riski).

**Qalan — məhsul-həssas qərar:**
- Seq5 — access code at-rest şifrələmə: access code müəllim-görünən paylaşılan
  sirdir (tələbələrə göstərilir) və bir çox oxu/müqayisə/display sahəsinə toxunur;
  Fernet-at-rest (PIN pattern-i) + tam trace tələb edir. PIN one-use: finals
  reconnect axışını poza bilər (məhsul qərarı).

**Qalan — riskli optimizasiya / ayrıca iş:**
- Registrar `get_offering_results` N+1 (compute_final_result per-enrollment):
  batch-prefetch restrukturu final-qiymət məntiqinə (100+ test) toxunur, ayrıca
  ehtiyatlı optimizasiya kimi edilməlidir.
- Assignment/project/lab max-attempt concurrency row-lock: 3 modulun submission
  axışına ayrıca toxunuş.
