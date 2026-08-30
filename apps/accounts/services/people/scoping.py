"""Kataloqun struktur daraltmaları — scope + istifadəçinin seçdiyi fakültə/kafedra.

İKİ AYRI daraltma var və onları qarışdırmaq təhlükəlidir:

1. **Scope** — istifadəçinin ÜMUMİYYƏTLƏ görə bildiyi sahə (dekan → öz fakültəsi).
   Bu, icazə qatından gəlir və istifadəçi onu dəyişə bilməz.
2. **Filtr** — istifadəçinin öz görünüş sahəsi İÇİNDƏ seçdiyi daralma
   («yalnız İnformatika kafedrası»). Sırf rahatlıq üçündür.

Filtr heç vaxt scope-u genişləndirmir: hər ikisi AND ilə birləşir və tanınmayan
unit id-si «heç nə» (`Q(pk__in=[])`) qaytarır — yəni başqa fakültənin id-sini
əl ilə yazmaq boş nəticə verir, bütün təşkilatı yox.
"""

from __future__ import annotations

from django.db.models import Q

_NOTHING = Q(pk__in=[])


def unit_subtree_q(organization, unit_id, *, path_field, id_field) -> Q:
    """Verilmiş OrgUnit-in alt-ağacı üçün Q (özü + bütün törəmələri).

    Unit tapılmasa «heç nə uyğun gəlmir» qaytarılır — fail-closed.
    """
    if not unit_id:
        return Q()

    from apps.organizations.models import OrgUnit

    unit = OrgUnit.objects.filter(organization=organization, pk=unit_id, is_active=True).only("id", "path").first()
    if unit is None:
        return _NOTHING
    condition = Q(**{id_field: unit.pk})
    if unit.path:
        condition |= Q(**{f"{path_field}__startswith": f"{unit.path}/"})
    return condition


def structure_filter_q(organization, filters, *, path_field, id_field) -> Q:
    """Fakültə + kafedra filtrlərinin birləşməsi.

    Kafedra seçilibsə fakültə filtri artıqdır (kafedra onsuz da fakültənin
    altındadır), amma hər ikisi tətbiq olunur: uyğunsuz cüt («A fakültəsi +
    B kafedrası») BOŞ nəticə verməlidir, B kafedrasının siyahısını yox.
    """
    condition = Q()
    for unit_id in (filters.faculty, filters.kafedra):
        if unit_id:
            condition &= unit_subtree_q(organization, unit_id, path_field=path_field, id_field=id_field)
    return condition


__all__ = ["structure_filter_q", "unit_subtree_q"]
