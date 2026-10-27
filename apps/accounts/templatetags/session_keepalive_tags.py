"""Açıq səhifənin sessiya pingi üçün parametrlər (``templates/partials/_session_keepalive.html``, 2026-10-27).

Mənbə yeganədir — :mod:`apps.accounts.session_policy`; şablon rəqəmi «bişirmir». Xarici JS
(``static/js/core/session_keepalive.js``) dəyərləri data-atributlardan oxuyur.
"""

from django import template

from ..session_policy import heartbeat_seconds, presence_seconds

register = template.Library()


@register.simple_tag(takes_context=True)
def session_keepalive_config(context) -> dict:
    request = context.get("request")
    user = getattr(request, "user", None)
    if request is None or not getattr(user, "is_authenticated", False) or not hasattr(request, "session"):
        return {"enabled": False}
    # View-as altında qayda ƏSL istifadəçiyə aiddir (sessiya onundur).
    actor = getattr(request, "real_user", None) or user
    presence = presence_seconds(request, actor)
    return {"enabled": True, "presence": presence, "heartbeat": heartbeat_seconds(presence)}
