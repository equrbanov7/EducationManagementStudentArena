"""«Tələbəni bərpa et» düyməsinin vəziyyəti — jurnal səhifəsinin view kontekstinə toxunmadan (sahib 2026-11-15).

``{% journal_roster_restore_state offering request.user as rrs %}`` → ``{"show", "count", "blocked"}``:

* ``show`` — aktor çıxara bilir (``journal.correct`` org-wide və ya əhatəli ``journal.roster``) VƏ bu jurnaldan
  çıxarılmış / dondurulmuş sətir var;
* ``blocked`` — jurnal bağlıdır / keçmiş dövrdür (düymə səbəblə deaktiv görünür).

Nəticə sorğu obyektində saxlanılır — eyni səhifədə düymə və modal include-u təkrar sorğu etmir.
"""

from __future__ import annotations

from django import template

register = template.Library()

_CACHE_ATTR = "_ems_roster_restore_state"


@register.simple_tag(takes_context=True)
def journal_roster_restore_state(context, offering, user):
    request = context.get("request")
    cache = getattr(request, _CACHE_ATTR, None) if request is not None else None
    key = str(getattr(offering, "pk", ""))
    if isinstance(cache, dict) and key in cache:
        return cache[key]
    from apps.registrar import journal_roster_restore as service

    state = {"show": False, "count": 0, "blocked": ""}
    if offering is not None and getattr(user, "is_authenticated", False) and service.can_view(user, offering):
        count = service.removed_count(offering)
        if count:
            state = {"show": True, "count": count, "blocked": service.block_reason(offering)}
    if request is not None:
        if not isinstance(cache, dict):
            cache = {}
            setattr(request, _CACHE_ATTR, cache)
        cache[key] = state
    return state
