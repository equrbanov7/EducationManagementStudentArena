"""«Jurnaldan çıxarılmalar» kabinet bölməsinin template tag-ı (sahib 2026-11-04).

``journal_hygiene_panel`` naxışı: bölmə konteksti profil qurucusuna əlavə olunmur — panel çərçivəsini və
cari səhifəni bu tag-dan alır (qapı render vaxtı YENİDƏN yoxlanır, fail-closed).
"""

from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def journal_removals_panel(context):
    from ..views.journal_removals import build_panel_context

    request = context.get("request")
    if request is None:
        return {"has_access": False, "access_denied_message": ""}
    return build_panel_context(request)
