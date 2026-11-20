"""«Kənardan jurnal girişi» kabinet bölməsinin template tag-ı (sahib 2026-11-20).

``journal_removals_panel`` naxışı: bölmə konteksti profil qurucusuna əlavə olunmur — panel datasını bu tag-dan alır
(qapı render vaxtı YENİDƏN yoxlanır, fail-closed).
"""

from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def remote_journal_access_panel(context):
    from ..views.remote_journal_access import build_panel_context

    request = context.get("request")
    if request is None:
        return {"has_access": False, "access_denied_message": ""}
    return build_panel_context(request)
