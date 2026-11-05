"""«Alt qrup tələbələri» kabinet bölməsinin template tag-ı (sahib 2026-11-05).

``journal_removals_panel`` naxışı: bölmə konteksti profil qurucusuna əlavə olunmur — panel çərçivəsini, statistikanı
və cari səhifəni bu tag-dan alır (qapı və əhatə render vaxtı YENİDƏN yoxlanır, fail-closed).
"""

from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def subgroup_students_panel(context):
    from ..views.subgroup_students import build_panel_context

    request = context.get("request")
    if request is None:
        return {"has_access": False, "access_denied_message": ""}
    return build_panel_context(request)
