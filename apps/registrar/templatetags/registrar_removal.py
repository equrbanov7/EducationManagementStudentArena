"""Jurnaldan çıxarılma səbəbinin seçim siyahısı — jurnal modallarının ortaq partial-ı üçün (sahib 2026-11-04).

``{% journal_removal_reasons as removal_reasons %}`` — ``[(value, label), …]`` aktiv dildə; jurnal səhifəsinin
view kontekstinə toxunmadan «Fəndən azad et» və alt qrup «Çıxar» paneli eyni siyahını göstərir.
"""

from __future__ import annotations

from django import template

register = template.Library()


@register.simple_tag
def journal_removal_reasons():
    from apps.registrar.journal_removal import reason_choices

    return reason_choices()
