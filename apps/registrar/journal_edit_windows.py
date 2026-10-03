"""Jurnal redaktə pəncərələri (sahib 2026-10-03: RİM rəhbəri «Sistem tənzimləmələri»ndən dəyişir).

* dərs sətri (tarix/növ/mövzu/saat/silmə) — yaranışdan sonra ``lesson_edit_window()``;
* q/b, i/e və bal — yazılışdan sonra ``mark_edit_window()``; Postgres trigger-i eyni açarı
  (``journal.mark_edit_hours``) oxuyur (registrar 0084), ona görə servis və DB qaydası üst-üstə düşür.

Dəyişiklik yoxdursa defolt 2 saatdır (əvvəlki sabit qayda).
"""

from __future__ import annotations

from datetime import timedelta

LESSON_EDIT_WINDOW = timedelta(hours=2)  # dərs sətri yaranışdan sonra (defolt)
MARK_EDIT_WINDOW = timedelta(hours=2)  # iştirak/bal yazıldıqdan sonra (defolt)


def lesson_edit_window() -> timedelta:
    from core import runtime_settings

    hours = runtime_settings.override("journal.lesson_edit_hours")
    return timedelta(hours=int(hours)) if hours else LESSON_EDIT_WINDOW


def mark_edit_window() -> timedelta:
    from core import runtime_settings

    hours = runtime_settings.override("journal.mark_edit_hours")
    return timedelta(hours=int(hours)) if hours else MARK_EDIT_WINDOW


__all__ = ["LESSON_EDIT_WINDOW", "MARK_EDIT_WINDOW", "lesson_edit_window", "mark_edit_window"]
