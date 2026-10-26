"""«Giriş tarixçəsi» paneli (view-as, sahib 2026-10-26) — template tag.

`password_reset_admin` naxışı: panel öz kontekstini bu tag-dan alır, profil context
qurucusuna (ölçü büdcəsinə dayanmış ``context_builder/_stage*``) toxunulmur. View-as
olmayan sorğuda tag DB-yə getmir (``None`` qaytarır) — kabinetin sorğu büdcəsi dəyişmir.
"""

from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def view_as_login_history(context):
    request = context.get("request")
    if request is None or not getattr(request, "is_view_as", False):
        return None
    from ..services.view_as_login_history import login_history_for_view_as

    return login_history_for_view_as(request)
