"""Kredit yükü + «Alt qrupa tələbə əlavə et» template tag-ları (sahib 2026-10-18).

Bölmə kontekstləri profil qurucusuna (``context_builder/_stage*``, ölçü büdcəsinə dayanıb) əlavə olunmur —
``journal_hygiene_panel`` naxışı ilə tag-dan alınır:

* ``{% subgroup_placement_panel as sp %}`` — alətin çərçivəsi (açar qapısı daxil);
* ``{% student_credit_load as scl %}`` — tələbənin CARİ semestr kredit yükü («Bu semestr: 27 / 30 kredit»);
  tələbə deyilsə / dövr yoxdursa ``None``. Sorğu: dövr + qeyd + yazılışlar + plan kreditləri (4, sabit).
"""

from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def subgroup_placement_panel(context):
    from ..views.subgroup_placement import build_panel_context

    request = context.get("request")
    if request is None:
        return {"has_access": False, "access_denied_message": ""}
    return build_panel_context(request)


@register.simple_tag(takes_context=True)
def student_credit_load(context):
    request = context.get("request")
    user = getattr(request, "user", None)
    if request is None or user is None or not getattr(user, "is_authenticated", False):
        return None
    cached = getattr(request, "_ems_student_credit_load", False)
    if cached is not False:
        return cached
    from apps.accounts.views._helpers.tenant import _get_active_organization
    from apps.registrar.public import credit_load, student_active_record, subgroup_placement_lookups

    organization = _get_active_organization(request)
    result = None
    if organization is not None:
        record = student_active_record(user, organization)
        period = subgroup_placement_lookups.current_period(organization) if record is not None else None
        if period is not None:
            result = credit_load(user, period, organization=organization, record=record)
    request._ems_student_credit_load = result
    return result
