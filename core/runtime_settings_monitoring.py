"""«Monitorinq» — «Sistem tənzimləmələri» açarları (sahib 2026-10-21).

Sahib: «Sistemin yüklənməsində əsas yüklərdən biri monitorinqə görə ola bilər — əgər sistemi çox yükləsə, onu
söndürmək də olsun. Və onun performans optimizasiyasını nəzərə al.»

Açarlar YALNIZ tətbiq daxili monitorinqi (kabinetin «Sistem monitorinqi» səhifəsi, onun Prometheus/Loki/
Alertmanager sorğuları və in-app insident uzlaşdırması) idarə edir. Prometheus alertləri (e-poçt), Watchdog,
``/metrics/`` və alertlərin mənbəyi olan Celery/backup kollektorları HƏMİŞƏ işləyir — monitorinq konteynerlərini
(cadvisor/promtail/loki/grafana) dayandırmaq web tətbiqdən mümkün deyil və olmamalıdır (docker socket proxy
yalnız GET-dir); bunun üçün ``prod-host-maint.yml`` → ``monitoring-pause`` / ``monitoring-resume``.
İmtahan nəzarəti (müəllimin nəzarət paneli, imtahan mərkəzinin zal monitoru) bu açarlardan ASILI DEYİL.

Oxu nöqtələri bu moduldakı funksiyalardır — ``apps.monitoring.switches`` onları çağırır, açarı birbaşa oxumur.
``Spec`` sinfi IMPORT EDİLMİR (dövri import olmasın) — ``runtime_settings`` onu :func:`register`-ə ötürür.
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.utils.translation import pgettext_lazy

_CTX = "core.runtime_settings"

GROUP = ("monitoring", pgettext_lazy(_CTX, "Monitorinq"))

KEY_IN_APP_ENABLED = "monitoring.in_app_enabled"
KEY_AUTO_PAUSE_ON_LOAD = "monitoring.auto_pause_on_load"
KEY_LOAD_PAUSE_FACTOR = "monitoring.load_pause_factor"
KEY_UI_REFRESH_SECONDS = "monitoring.ui_refresh_seconds"

LOAD_PAUSE_FACTOR_DEFAULT = Decimal("1.5")
LOAD_PAUSE_FACTOR_MIN = 0.5
LOAD_PAUSE_FACTOR_MAX = 10.0
UI_REFRESH_SECONDS_DEFAULT = 30
UI_REFRESH_SECONDS_MIN = 10
UI_REFRESH_SECONDS_MAX = 600


def _default_in_app_enabled() -> bool:
    return bool(getattr(settings, "MONITORING_IN_APP_ENABLED", True))


def _default_auto_pause_on_load() -> bool:
    return bool(getattr(settings, "MONITORING_AUTO_PAUSE_ON_LOAD", True))


def _default_load_pause_factor() -> Decimal:
    return Decimal(str(getattr(settings, "MONITORING_LOAD_PAUSE_FACTOR", LOAD_PAUSE_FACTOR_DEFAULT)))


def _default_ui_refresh_seconds() -> int:
    return int(getattr(settings, "MONITORING_UI_REFRESH_SECONDS", UI_REFRESH_SECONDS_DEFAULT))


def build_specs(spec_cls) -> tuple:
    return (
        spec_cls(
            KEY_IN_APP_ENABLED, GROUP[0], "bool", _default_in_app_enabled,
            pgettext_lazy(_CTX, "Tətbiq daxili monitorinq («Sistem monitorinqi» səhifəsi)"),
            pgettext_lazy(
                _CTX,
                "Söndürüləndə «Sistem monitorinqi» səhifəsi «Monitorinq söndürülüb» bildirişi göstərir və "
                "Prometheus/Loki/Alertmanager-ə heç bir sorğu göndərmir; in-app insident uzlaşdırması dayanır. "
                "Alertlər (e-poçt), Watchdog və imtahan nəzarəti işləməyə davam edir. Monitorinq konteynerlərini "
                "dayandırmaq üçün «Prod host maintenance» → monitoring-pause əməliyyatı var.",
            ),
        ),
        spec_cls(
            KEY_AUTO_PAUSE_ON_LOAD, GROUP[0], "bool", _default_auto_pause_on_load,
            pgettext_lazy(_CTX, "Server yüklü olanda monitorinqi avtomatik dayandır"),
            pgettext_lazy(
                _CTX,
                "Yandırılıbsa server yükü (son 1 dəqiqənin orta yükü) aşağıdakı həddi keçəndə «Sistem "
                "monitorinqi» səhifəsinin sorğuları və in-app insident uzlaşdırması müvəqqəti dayanır; yük azalan "
                "kimi özü bərpa olunur. Alertlər bundan asılı deyil.",
            ),
        ),
        spec_cls(
            KEY_LOAD_PAUSE_FACTOR, GROUP[0], "decimal", _default_load_pause_factor,
            pgettext_lazy(_CTX, "Avtomatik dayandırma həddi (yük ÷ nüvə sayı)"),
            pgettext_lazy(
                _CTX,
                "Son 1 dəqiqənin orta yükü «bu dəyər × prosessor nüvələrinin sayı»nı keçəndə monitorinq "
                "dayandırılır. Məs. 1,5 və 10 nüvədə hədd 15-dir. Avtomatik bərpa (autoheal) yük altında "
                "restartları 2 × nüvədə dayandırır — monitorinq ondan əvvəl geri çəkilsin deyə defolt 1,5-dir.",
            ),
            pgettext_lazy(_CTX, "× nüvə"), min=LOAD_PAUSE_FACTOR_MIN, max=LOAD_PAUSE_FACTOR_MAX,
        ),
        spec_cls(
            KEY_UI_REFRESH_SECONDS, GROUP[0], "int", _default_ui_refresh_seconds,
            pgettext_lazy(_CTX, "Monitorinq məlumatının yenilənmə intervalı"),
            pgettext_lazy(
                _CTX,
                "Prometheus/Loki/Alertmanager cavabları bu müddət ərzində ortaq keşdən verilir — səhifəni neçə "
                "nəfər açıq saxlasa da, eyni sorğu bu intervalda bir dəfədən çox göndərilmir. Böyük dəyər yükü "
                "azaldır, qrafiklər isə bir o qədər gec yenilənir.",
            ),
            pgettext_lazy(_CTX, "saniyə"), min=UI_REFRESH_SECONDS_MIN, max=UI_REFRESH_SECONDS_MAX,
        ),
    )  # fmt: skip


def register(groups: tuple, specs: dict, spec_cls) -> tuple:
    """``runtime_settings``-ə qrup və açarları əlavə edir; yeni ``GROUPS``-u qaytarır (idempotent)."""
    specs.update({spec.key: spec for spec in build_specs(spec_cls)})
    if any(code == GROUP[0] for code, _label in groups):
        return groups
    return groups + (GROUP,)


def _get(key: str, fallback):
    try:
        from core import runtime_settings

        return runtime_settings.get(key)
    except Exception:  # noqa: BLE001 — tənzimləmə oxunmasa defolt (monitorinq səhifəsi sınmasın)
        return fallback()


def in_app_enabled() -> bool:
    """Tətbiq daxili monitorinq yandırılıbmı (defolt: bəli)."""
    return bool(_get(KEY_IN_APP_ENABLED, _default_in_app_enabled))


def auto_pause_on_load() -> bool:
    """Yük altında avtomatik dayandırma aktivdirmi (defolt: bəli)."""
    return bool(_get(KEY_AUTO_PAUSE_ON_LOAD, _default_auto_pause_on_load))


def load_pause_factor() -> float:
    """Hədd əmsalı (load1 > əmsal × nüvə → dayandır), hədlərə sıxılmış."""
    try:
        value = float(_get(KEY_LOAD_PAUSE_FACTOR, _default_load_pause_factor))
    except (TypeError, ValueError):
        value = float(LOAD_PAUSE_FACTOR_DEFAULT)
    return max(LOAD_PAUSE_FACTOR_MIN, min(LOAD_PAUSE_FACTOR_MAX, value))


def ui_refresh_seconds() -> int:
    """Monitorinq cavablarının ortaq keş müddəti / UI yenilənmə intervalı (saniyə), hədlərə sıxılmış."""
    try:
        value = int(_get(KEY_UI_REFRESH_SECONDS, _default_ui_refresh_seconds))
    except (TypeError, ValueError):
        value = UI_REFRESH_SECONDS_DEFAULT
    return max(UI_REFRESH_SECONDS_MIN, min(UI_REFRESH_SECONDS_MAX, value))


__all__ = [
    "GROUP",
    "KEY_AUTO_PAUSE_ON_LOAD",
    "KEY_IN_APP_ENABLED",
    "KEY_LOAD_PAUSE_FACTOR",
    "KEY_UI_REFRESH_SECONDS",
    "auto_pause_on_load",
    "build_specs",
    "in_app_enabled",
    "load_pause_factor",
    "register",
    "ui_refresh_seconds",
]
