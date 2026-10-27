"""Hərəkətsiz jurnalın bağlanma dəqiqəsi — ``{% journal_idle_close_minutes as m %}`` (sahib 2026-10-27).

Mənbə yeganədir — ``core.runtime_settings_session.journal_idle_minutes`` («Sistem tənzimləmələri → Elektron jurnal»).
0 — söndürülü (partial heç nə render etmir).
"""

from django import template

from core.runtime_settings_session import journal_idle_minutes

register = template.Library()


@register.simple_tag
def journal_idle_close_minutes() -> int:
    return journal_idle_minutes()
