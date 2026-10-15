"""Parol siyasəti şablonlara (``minlength``, ipucu, brauzer köməkçisinin data-atributları).

Mənbə yeganədir — ``apps.accounts.password_policy``; şablon rəqəmi «bişirmir».
"""

from django import template

from ..password_policy import TRIVIAL_PASSWORDS, help_text, min_length

register = template.Library()


@register.simple_tag
def password_min_length() -> int:
    return min_length()


@register.simple_tag
def password_help_text() -> str:
    return help_text()


@register.simple_tag
def password_trivial_list() -> str:
    """Boşluqla ayrılmış qadağa siyahısı — ``data-pw-trivial`` üçün (siyahıdakı parollarda boşluq yoxdur)."""
    return " ".join(sorted(TRIVIAL_PASSWORDS))
