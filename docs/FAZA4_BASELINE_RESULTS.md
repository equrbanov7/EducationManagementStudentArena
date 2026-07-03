# FAZA 4 — Baseline vs Transaction Pool Nəticələri

**Status:** ⏳ Doldurulacaq — staging rollout icra edildikdən sonra.

Runbook: `docs/FAZA4_STAGING_RUNBOOK.md`.

## Test mətriksi (500 VU + 1000 VU)

### Dashboard navigation (`k6/dashboard-navigation-test.js`)

| VU | Baseline (session) p50 / p95 / p99 | Transaction pool p50 / p95 / p99 | Failed % baseline | Failed % txn | PgBouncer wait max | Verdict |
|---:|-----------------------------------:|---------------------------------:|:---:|:---:|:---:|:---:|
| 100 | | | | | | |
| 500 | | | | | | |
| 1000 | | | | | | |

### Mixed realistic (`k6/mixed-realistic-load-test.js`)

| VU | Baseline p50 / p95 / p99 | Transaction p50 / p95 / p99 | Failed % baseline | Failed % txn | pg_stat max | Verdict |
|---:|-------------------------:|----------------------------:|:---:|:---:|:---:|:---:|
| 100 | | | | | | |
| 500 | | | | | | |
| 1000 | | | | | | |

### Student exam flow (`k6/student-exam-flow-test.js`)

| VU | Baseline p50 / p95 / p99 | Transaction p50 / p95 / p99 | Failed % baseline | Failed % txn | Verdict |
|---:|-------------------------:|----------------------------:|:---:|:---:|:---:|
| 100 | | | | | |
| 500 | | | | | |
| 1000 | | | | | |

## Kross-tenant smoke nəticələri

- [ ] Live exam websocket: 0 cross-tenant sızıntı (2 tenant × 5 player)
- [ ] Celery supervision sweep: yalnız öz tenant attempt-ləri toxundu
- [ ] Audit log-larda `organization_id` düzgün yazıldı

## Canary müşahidə (1-2 saatlıq iş-saatı pəncərəsi)

| Metrik | Baseline replika | Canary replika | Verdict |
|--------|-----------------:|---------------:|:---:|
| p95 dashboard | | | |
| p95 exam autosave | | | |
| 5xx rate | | | |
| Redis latency | | | |
| DB connection count | | | |

## Yekun qərar

- [ ] Bütün gate-lər keçdi → **tam rollout təsdiqləndi** (bax runbook §6)
- [ ] Bir və ya daha çox gate düşdü → **ROLLBACK** və düşən gate-ə issue aç
- [ ] Yekun bal dəyişkənliyi (docs/AUDIT-də): Miqyas 75→? · Performans 77→? · ÜMUMİ ~83→?
