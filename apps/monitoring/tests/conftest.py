"""Monitorinq testləri üçün ortaq fixture-lar.

2026-10-21: ``monitoring.auto_pause_on_load`` defolt AÇIQDIR və host yükünü (``os.getloadavg``) oxuyur —
paralel test qaçışında (CI 2 vCPU, ``-n 6``) yük həddi keçə bilər və Prometheus/Loki-ni gözləyən mövcud testlər
«server yüklüdür» cavabı alardı. Ona görə bu qovluqda avto-pauza defolt SÖNÜLÜDÜR; xüsusiyyətin öz testləri
(``test_monitoring_switches_2026_10_21.py``) onu ``override_settings`` ilə açır və yükü saxtalaşdırır.
"""

import pytest


@pytest.fixture(autouse=True)
def _monitoring_auto_pause_off(settings):
    settings.MONITORING_AUTO_PAUSE_ON_LOAD = False
