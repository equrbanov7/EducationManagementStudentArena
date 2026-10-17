"""«Sistem monitorinqi → Loglar» zondu (OXU-YALNIZ; sahib 2026-10-17: «loglar boş göstərir»).

`prod_logs_diag.sh` bunu app konteynerində `manage.py shell <` ilə işlədir — yəni Django-nun
gördüyü şəbəkədən və onun konfiqurasiya etdiyi URL ilə. Yalnız SAY, STATUS və MÜDDƏT çap
olunur; heç bir log sətrinin MƏZMUNU çap olunmur (PII). Heç bir yazı/POST yoxdur.

Yoxlanır:
* `settings.MONITORING_LOKI_URL` + Loki `/ready` (status, ms);
* `/loki/api/v1/labels` (yalnız etiket ADLARI) və `container` dəyərlərinin sayı;
* UI-ın öz sorğusu (`{job="docker"}`, son 1 saat, limit 21) — sətir sayı, ən yeni sətrin
  yaşı, müddət; UI timeout-u (5 s) aşırsa qeyd;
* son 1 saatda compose servisi üzrə sətir sayı (`count_over_time`, yalnız rəqəm);
* Loki öz metrikaları (qəbul edilən / atılan sətirlər, səbəb üzrə);
* promtail `/ready` + metrikaları (docker-dən oxunan / göndərilən / atılan, push status kodları)
  və 15 s ərzində artım — axın canlıdırmı;
* Prometheus: Loki scrape `up`, son 1 saatda qəbul olunan sətir, query_range p95 (24 saat).
"""

import re
import time

from django.conf import settings

import requests

LOKI = (getattr(settings, "MONITORING_LOKI_URL", "") or "http://loki:3100").rstrip("/")
PROM = (getattr(settings, "MONITORING_PROMETHEUS_URL", "") or "http://prometheus:9090").rstrip("/")
PROMTAIL = "http://promtail:9080"
#: apps/monitoring/clients.py REQUEST_TIMEOUT_SECONDS — UI bu müddətdən sonra «degraded» göstərir.
UI_TIMEOUT = 5
NS = 1_000_000_000
UI_SELECTOR = '{job="docker"}'


def get(url, params=None, timeout=15):
    started = time.monotonic()
    try:
        response = requests.get(url, params=params, timeout=timeout)
        return response, (time.monotonic() - started) * 1000, None
    except Exception as exc:  # noqa: BLE001 — zond heç vaxt yıxılmamalıdır
        return None, (time.monotonic() - started) * 1000, type(exc).__name__


def status_of(response, error):
    return str(response.status_code) if response is not None else f"XƏTA {error}"


def json_of(response):
    try:
        return response.json()
    except Exception:  # noqa: BLE001
        return {}


_METRIC_RE = re.compile(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{[^}]*\})?\s+([-+0-9.eE]+|NaN|\+Inf|-Inf)")


def metric_sums(text, names, by_label=None):
    """Prometheus mətn formatından seçilmiş metrikaların cəmi (``by_label`` üzrə qruplaşdırılmış)."""
    sums = {}
    for line in (text or "").splitlines():
        match = _METRIC_RE.match(line)
        if not match or match.group(1) not in names:
            continue
        key = match.group(1)
        if by_label and match.group(2):
            label = re.search(rf'{by_label}="([^"]*)"', match.group(2))
            if label:
                key += f"{{{by_label}={label.group(1)}}}"
        try:
            sums[key] = sums.get(key, 0.0) + float(match.group(3))
        except ValueError:
            continue
    return sums


def print_sums(title, sums):
    if not sums:
        print(f"{title}: — (metrika yoxdur)")
        return
    print(f"{title}:")
    for key in sorted(sums):
        print(f"   {key} = {sums[key]:.0f}")


def promq(query):
    response, _, error = get(PROM + "/api/v1/query", {"query": query})
    if response is None or response.status_code != 200:
        return f"n/a ({status_of(response, error)})"
    result = (json_of(response).get("data") or {}).get("result") or []
    if not result:
        return "—"
    return ", ".join(
        "{}={}".format(",".join(f"{k}:{v}" for k, v in sorted(item.get("metric", {}).items())) or "*", item["value"][1])
        for item in result[:8]
    )


print("== Django → Loki")
print(f"MONITORING_LOKI_URL = {LOKI}")
response, ms, error = get(LOKI + "/ready", timeout=UI_TIMEOUT)
ready_text = (response.text.strip()[:40] if response is not None else "") or "—"
print(f"Loki /ready: {status_of(response, error)} «{ready_text}» ({ms:.0f} ms)")

response, ms, error = get(LOKI + "/loki/api/v1/labels")
labels = json_of(response).get("data") if response is not None else None
print(f"labels: {status_of(response, error)} ({ms:.0f} ms) → {', '.join(labels or []) or '—'}")

response, ms, error = get(LOKI + "/loki/api/v1/label/container/values")
containers = (json_of(response).get("data") or []) if response is not None else []
app_streams = sum(1 for name in containers if "-app-" in name)
print(
    f"container dəyərləri (son 6 saat): {status_of(response, error)} → cəmi {len(containers)}, "
    f"app replikası {app_streams}, nginx {'var' if any('nginx' in n for n in containers) else 'YOXDUR'}"
)

now = time.time_ns()
for title, query in (
    ("UI defolt sorğusu", UI_SELECTOR),
    ("app", '{job="docker", service="app"}'),
    ("nginx", '{job="docker", service="nginx"}'),
    ("celery_worker", '{job="docker", service="celery_worker"}'),
):
    response, ms, error = get(
        LOKI + "/loki/api/v1/query_range",
        {"query": query, "start": now - 3600 * NS, "end": now, "limit": 21, "direction": "backward"},
    )
    if response is None or response.status_code != 200:
        body = (response.text.strip().splitlines() or [""])[0][:160] if response is not None else ""
        print(f"{title} `{query}` 1 saat: {status_of(response, error)} ({ms:.0f} ms) {body}")
        continue
    streams = (json_of(response).get("data") or {}).get("result") or []
    stamps = [int(value[0]) for stream in streams for value in stream.get("values", [])]
    newest = f"{(now - max(stamps)) / NS:.0f} s əvvəl" if stamps else "—"
    slow = " ⚠️ UI timeout-u (5 s) aşır" if ms > UI_TIMEOUT * 1000 else ""
    print(f"{title} `{query}` 1 saat: 200, {len(stamps)} sətir, ən yenisi {newest} ({ms:.0f} ms){slow}")

response, ms, error = get(
    LOKI + "/loki/api/v1/query", {"query": f"sum by (service) (count_over_time({UI_SELECTOR}[1h]))", "time": now}
)
rows = ((json_of(response).get("data") or {}).get("result") or []) if response is not None else []
print(f"son 1 saatda servis üzrə sətir sayı: {status_of(response, error)} ({ms:.0f} ms)")
for row in sorted(rows, key=lambda item: -float(item["value"][1]))[:20]:
    print(f"   {row.get('metric', {}).get('service', '?')}: {float(row['value'][1]):.0f}")

response, _, error = get(LOKI + "/metrics")
print_sums(
    "Loki qəbul/atma (prosesin başlanğıcından)",
    metric_sums(
        response.text if response is not None else "",
        {"loki_distributor_lines_received_total", "loki_discarded_samples_total", "loki_ingester_memory_streams"},
        by_label="reason",
    ),
)

print("== promtail")
response, ms, error = get(PROMTAIL + "/ready", timeout=UI_TIMEOUT)
print(f"promtail /ready: {status_of(response, error)} ({ms:.0f} ms)")
PROMTAIL_METRICS = {
    "promtail_docker_target_entries_total",
    "promtail_docker_target_parsing_errors_total",
    "promtail_sent_entries_total",
    "promtail_dropped_entries_total",
}
response, _, error = get(PROMTAIL + "/metrics")
before = metric_sums(response.text if response is not None else "", PROMTAIL_METRICS, by_label="reason")
print_sums("promtail sayğacları (prosesin başlanğıcından)", before)
print_sums(
    "promtail → Loki push cavabları",
    metric_sums(
        response.text if response is not None else "", {"promtail_request_duration_seconds_count"}, "status_code"
    ),
)
if before:
    # Axın canlıdırmı? 15 s sonra eyni sayğaclar: docker-dən oxunan və Loki-yə göndərilən artım.
    time.sleep(15)
    response, _, error = get(PROMTAIL + "/metrics")
    after = metric_sums(response.text if response is not None else "", PROMTAIL_METRICS, by_label="reason")
    print_sums("promtail son 15 s artım", {key: after.get(key, 0.0) - value for key, value in before.items()})

print("== Prometheus (Loki haqqında)")
print("up{job=emsarena-loki}:", promq('up{job="emsarena-loki"}'))
print("son 1 saatda qəbul olunan sətir:", promq("sum(increase(loki_distributor_lines_received_total[1h]))"))
print("son 24 saatda atılan sətir (səbəb):", promq("sum by (reason) (increase(loki_discarded_samples_total[24h]))"))
print(
    "query_range p95 (24 saat, s):",
    promq(
        "histogram_quantile(0.95, sum by (le) "
        '(rate(loki_request_duration_seconds_bucket{route=~"loki_api_v1_query_range"}[24h])))'
    ),
)
