"""«Lab qrupları» kabinet bölməsinin template tag-ı (sahib 2026-11-07).

``subgroup_students_panel`` naxışı: bölmə konteksti profil qurucusuna əlavə olunmur — jurnal siyahısı, KPI və
seçilmiş jurnalın iş sahəsi bu tag-dan gəlir (qapı və əhatə render vaxtı YENİDƏN yoxlanır, fail-closed).
"""

from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def lab_groups_panel(context):
    from ..views.lab_groups_section import build_panel_context

    request = context.get("request")
    if request is None:
        return {"has_access": False, "access_denied_message": ""}
    return build_panel_context(request)
