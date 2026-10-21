"""Tətbiq daxili monitorinqin açarları: söndürmə, yükdə avto-pauza, ortaq keş intervalı (sahib 2026-10-21).

Açarlar «Sistem tənzimləmələri → Monitorinq» qrupundadır (``core.runtime_settings_monitoring``). Bu modul
onları birləşdirib bir QAPI verir:

* :func:`current_gate` — monitorinq sorğuları indi göndərilə bilərmi (``reason``: ``""`` / ``disabled`` /
  ``load``). Yük ``os.getloadavg()``-dan oxunur: Linux-da load average namespace-lənmir, konteyner içində də
  HOST-un yüküdür (``scripts/ops/selfheal/emsarena-autoheal.sh`` ``/proc/loadavg``-ın eyni ilk sahəsini
  oxuyur). Nüvə sayı — prosesə icazəli CPU-lar (``sched_getaffinity``; app konteynerində CPU tavanı yoxdur).
* :func:`monitoring_gate` — API view dekoratoru: qapı bağlıdırsa Prometheus/Loki/Alertmanager-ə HEÇ BİR
  sorğu getmir, UI-ın tanıdığı ``status="degraded"`` cavabı (səbəb mətni ilə) qaytarılır — mövcud banner
  «Monitorinq söndürülüb» / «Server yüklüdür» göstərir.
* :func:`cache_ttl` — müştəri cavablarının ortaq (Redis) keş müddəti = «yenilənmə intervalı».

Nəyə TOXUNULMUR (qəsdən): Prometheus alertləri, Watchdog, ``/metrics/``, alertlərin mənbəyi olan
``monitoring.collect_celery_stats`` / ``collect_backup_age`` (CeleryBeatStale/BackupTooOld yalançı yanmasın),
Alertmanager webhook-u (insident axını), DB-dən oxuyan «İnsidentlər»/«Təhlükəsizlik» tabları və imtahan
nəzarəti (müəllim paneli, zal monitoru).
"""

from __future__ import annotations

import functools
import os
from dataclasses import dataclass

from django.http import JsonResponse
from django.utils.translation import pgettext

from core import runtime_settings_monitoring as switch_settings

_CTX = "monitoring.switch"

REASON_DISABLED = "disabled"
REASON_LOAD = "load"


@dataclass(frozen=True)
class MonitoringGate:
    active: bool
    reason: str = ""
    load1: float | None = None
    cores: int = 1
    threshold: float | None = None


def host_load() -> tuple[float | None, int]:
    """(load1, nüvə sayı). Load oxunmasa ``None`` — bu halda avto-pauza işə düşmür (fail-open)."""
    try:
        load1 = float(os.getloadavg()[0])
    except (AttributeError, OSError):
        load1 = None
    try:
        cores = len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        cores = os.cpu_count() or 1
    return load1, max(1, int(cores))


def current_gate() -> MonitoringGate:
    if not switch_settings.in_app_enabled():
        return MonitoringGate(active=False, reason=REASON_DISABLED)
    if not switch_settings.auto_pause_on_load():
        return MonitoringGate(active=True)
    load1, cores = host_load()
    threshold = round(switch_settings.load_pause_factor() * cores, 2)
    if load1 is not None and load1 > threshold:
        return MonitoringGate(active=False, reason=REASON_LOAD, load1=load1, cores=cores, threshold=threshold)
    return MonitoringGate(active=True, load1=load1, cores=cores, threshold=threshold)


def is_active() -> bool:
    return current_gate().active


def cache_ttl() -> int:
    """Prometheus/Loki/Alertmanager cavablarının ortaq keş müddəti (saniyə)."""
    return switch_settings.ui_refresh_seconds()


def paused_message(gate: MonitoringGate) -> str:
    if gate.reason == REASON_LOAD:
        return pgettext(
            _CTX,
            "Server yüklüdür (yük %(load)s > hədd %(threshold)s) — monitorinq sorğuları yük azalana qədər "
            "avtomatik dayandırılıb. Alertlər işləyir.",
        ) % {"load": f"{gate.load1:.1f}", "threshold": f"{gate.threshold:g}"}
    return pgettext(
        _CTX,
        "Monitorinq söndürülüb («Sistem tənzimləmələri → Monitorinq»). Prometheus/Loki sorğuları göndərilmir; "
        "alertlər (e-poçt) və imtahan nəzarəti işləyir.",
    )


def paused_payload(gate: MonitoringGate) -> dict:
    """UI-ın tanıdığı degraded forması + səbəb (``paused``) və yük məlumatı."""
    message = paused_message(gate)
    return {
        "status": "degraded",
        "service": "monitoring",
        "paused": gate.reason,
        "message": message,
        "last_successful_update": None,
        "load1": None if gate.load1 is None else round(gate.load1, 2),
        "threshold": gate.threshold,
        "refresh_seconds": cache_ttl(),
        # «Loglar» tabının renderer-i səbəbi ``error``-dan oxuyur (naməlum növ → ümumi mətn; banner izah edir).
        "error": {"kind": "paused", "status": None, "detail": message},
    }


def monitoring_gate(view):
    """Qapı bağlıdırsa view-u çağırmadan (heç bir xarici sorğu olmadan) degraded cavab qaytarır.

    İcazə dekoratorundan SONRA (daxildə) qoyulur — icazəsiz cəhd yenə 403 + SecurityEvent alır.
    """

    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        gate = current_gate()
        if not gate.active:
            response = JsonResponse(paused_payload(gate))
            response["Cache-Control"] = "no-store"
            return response
        return view(request, *args, **kwargs)

    return wrapper


__all__ = [
    "REASON_DISABLED",
    "REASON_LOAD",
    "MonitoringGate",
    "cache_ttl",
    "current_gate",
    "host_load",
    "is_active",
    "monitoring_gate",
    "paused_message",
    "paused_payload",
]
