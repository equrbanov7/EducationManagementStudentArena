# FAZA 4 — Baseline vs Transaction Pool Nəticələri

**Status (2026-07-11 re-audit):** Tam capacity baseline **hələ ölçülməyib**.
Yalnız aşağıdakı bounded lokal liveness smoke icra edilib. Boş xanalar rəqəm
olmaması deməkdir; heç bir nəticə təxminlə doldurulmayıb.

Runbook: `docs/operations/FAZA4_STAGING_RUNBOOK.md`.

## 2026-07-11 bounded lokal liveness smoke

Bu test yalnız alətin, lokal Nginx/Daphne yolunun və DB+Redis health check-in
qısa yükdə cavab verdiyini göstərir. **Real imtahan capacity testi deyil.**

- k6: `v2.0.0 (go1.26.3, darwin/arm64)`
- host: Apple M3 Pro, 11 CPU, 19.3 GB RAM
- Docker Desktop limiti: 11 CPU, 8,217,432,064 bayt
- hədəf: `http://127.0.0.1` -> Nginx -> tək Daphne
- profil: 100 sabit VU x 10 saniyə
- iterasiya: `GET /ping/` + `GET /health/` + `sleep(1)`
- header: `Host: localhost`, `X-Forwarded-Proto: https`

### Tam command

```bash
VUS=100 DURATION=10s BASE_URL=http://127.0.0.1 k6 run --quiet - <<'EOF'
import http from 'k6/http';
import { sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';
const ping = new Trend('diag_ping_ms', true);
const health = new Trend('diag_health_ms', true);
const errors = new Rate('diag_errors');
export const options = {
  vus: Number(__ENV.VUS || 100),
  duration: __ENV.DURATION || '10s',
  summaryTrendStats: ['min','med','avg','p(90)','p(95)','p(99)','max'],
};
const params = { headers: { Host: 'localhost', 'X-Forwarded-Proto': 'https' } };
export default function () {
  let r = http.get(`${__ENV.BASE_URL}/ping/`, params);
  ping.add(r.timings.duration); errors.add(r.status !== 200);
  r = http.get(`${__ENV.BASE_URL}/health/`, params);
  health.add(r.timings.duration); errors.add(r.status !== 200);
  sleep(1);
}
EOF
```

### Tam k6 summary

```text
CUSTOM
diag_errors:      0.00% (0 / 1872)
diag_health_ms:   min=1.32ms med=42.37ms avg=45.61ms p90=99.03ms p95=131.57ms p99=145.5ms max=158.45ms
diag_ping_ms:     min=1.25ms med=45.85ms avg=93.53ms p90=109.45ms p95=136.35ms p99=1.07s max=1.08s

HTTP
http_req_duration: min=1.25ms med=43.41ms avg=69.57ms p90=101.53ms p95=135.74ms p99=1.07s max=1.08s
http_req_failed:   0.00% (0 / 1872)
http_reqs:         1872; 169.421409 req/s

EXECUTION
iteration_duration: min=1s med=1.09s avg=1.13s p90=1.25s p95=1.27s p99=2.12s max=2.13s
iterations:         936; 84.710704 iter/s
vus:                son sampling=41, min=41 max=100
vus_max:            100

NETWORK
data_received: 2.2 MB (200 kB/s)
data_sent:     182 kB (16 kB/s)
```

### Niyə capacity sübutu deyil

- PIN, auth, attempt start, question fetch, autosave, submit, result və
  WebSocket axını yoxdur.
- Lokal runtime image-i host HEAD-dən köhnədir.
- Lokal app DB rolu superuser/BYPASSRLS-dir.
- Test cəmi 10 saniyədir; steady/soak davranışı ölçülmür.
- PgBouncer wait, Redis latency, Celery queue lag və data-loss invariantı
  paralel toplanmayıb.

## Test mətriksi (500 VU + 1000 VU)

### Dashboard navigation (`k6/dashboard-navigation-test.js`)

| VU | Baseline (session) p50 / p95 / p99 | Transaction pool p50 / p95 / p99 | Failed % baseline | Failed % txn | PgBouncer wait max | Verdict |
|---:|-----------------------------------:|---------------------------------:|:---:|:---:|:---:|:---:|
| 100 | Ölçülməyib | Ölçülməyib | — | — | — | AÇIQ |
| 500 | Ölçülməyib | Ölçülməyib | — | — | — | AÇIQ |
| 1000 | Ölçülməyib | Ölçülməyib | — | — | — | AÇIQ |

### Mixed realistic (`k6/mixed-realistic-load-test.js`)

| VU | Baseline p50 / p95 / p99 | Transaction p50 / p95 / p99 | Failed % baseline | Failed % txn | pg_stat max | Verdict |
|---:|-------------------------:|----------------------------:|:---:|:---:|:---:|:---:|
| 100 | Ölçülməyib | Ölçülməyib | — | — | — | AÇIQ |
| 500 | Ölçülməyib | Ölçülməyib | — | — | — | AÇIQ |
| 1000 | Ölçülməyib | Ölçülməyib | — | — | — | AÇIQ |

### Student exam flow (`k6/student-exam-flow-test.js`)

| VU | Baseline p50 / p95 / p99 | Transaction p50 / p95 / p99 | Failed % baseline | Failed % txn | Verdict |
|---:|-------------------------:|----------------------------:|:---:|:---:|:---:|
| 100 | Ölçülməyib | Ölçülməyib | — | — | AÇIQ |
| 500 | Ölçülməyib | Ölçülməyib | — | — | AÇIQ |
| 1000 | Ölçülməyib | Ölçülməyib | — | — | AÇIQ |

## Kross-tenant smoke nəticələri

- [ ] Live exam websocket: 0 cross-tenant sızıntı (2 tenant × 5 player)
- [ ] Celery supervision sweep: yalnız öz tenant attempt-ləri toxundu
- [ ] Audit log-larda `organization_id` düzgün yazıldı

## Canary müşahidə (1-2 saatlıq iş-saatı pəncərəsi)

| Metrik | Baseline replika | Canary replika | Verdict |
|--------|-----------------:|---------------:|:---:|
| p95 dashboard | Ölçülməyib | Ölçülməyib | AÇIQ |
| p95 exam autosave | Ölçülməyib | Ölçülməyib | AÇIQ |
| 5xx rate | Ölçülməyib | Ölçülməyib | AÇIQ |
| Redis latency | Ölçülməyib | Ölçülməyib | AÇIQ |
| DB connection count | Ölçülməyib | Ölçülməyib | AÇIQ |

## Yekun qərar

- [ ] Bütün gate-lər keçdi → **tam rollout təsdiqləndi** (bax runbook §6)
- [ ] Bir və ya daha çox gate düşdü → **ROLLBACK** və düşən gate-ə issue aç
- [x] Capacity gate-ləri ölçülməyib → **NO-GO**, baseline rəqəmi verilmədi

## Növbəti ölçmə üçün məcburi hazırlıq

1. Current approved image digest və bütün migration-larla representative
   staging.
2. `NOSUPERUSER NOBYPASSRLS` app rolu və transaction-pooling konteksti.
3. Ən azı 1000 unikal synthetic tələbə, real exam/question/attempt cardinality.
4. Full PIN -> start -> question -> autosave -> submit -> result k6 ssenarisi.
5. Həqiqi WebSocket harness və reconnect storm.
6. PgBouncer, Redis, Celery queue lag, DB və app business SLI telemetry-si.
7. 100 VU x 30 dəq, 500 VU x 15 dəq, 1000 VU spike, 1 saat soak.
8. Autosave/submit data-loss reconciliation və raw JSON/CSV/HTML artefaktları.

Ətraflı gap analizi:
`docs/audits/2026-07-11-codex-tam-audit/REAUDIT_REPORT_AZ_2026-07-11.md`.
