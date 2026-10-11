"""«Kadr analitikası» (sahib 2026-10-11) — İnsan resursları üçün müəllim heyəti analitikası.

Modul bölgüsü (SOFT_CAP=600):

* ``constants`` — açarlar, etiketlər, tablar, problem kodları
* ``policy``    — aktor qapısı (`people.hr_analytics` / RİM rəhbəri / superadmin) + əhatə
* ``dataset``   — müəllim başına bir sətir (sabit sorğu sayı)
* ``filters``   — ``hr_*`` GET parametrləri (allowlist) + yaddaşda süzgəc
* ``aggregates``— KPI, ştat, tərkib, yük, fəaliyyət, keyfiyyət bölgüləri
* ``panel``     — server-render panel konteksti
* ``export``    — Excel cədvəlləri (ixrac view-u audit edir)
"""

from .constants import PERM_HR_ANALYTICS, SECTION
from .panel import build_panel, resolve
from .policy import HrActor, resolve_actor

__all__ = ["HrActor", "PERM_HR_ANALYTICS", "SECTION", "build_panel", "resolve", "resolve_actor"]
