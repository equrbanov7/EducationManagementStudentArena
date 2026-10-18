"""«Tələbə reyestri» çekməcəsi — semestr kredit yükü + alt qrup yerləşdirmə izi (sahib 2026-10-18).

Sahib (2026-09-07): «alt qrupa yazılıbsa onun da tarixçəsi qalsın, biz də bilək» — koordinator / dekanlıq tələbənin
kartında hər yerləşdirməni (kim, nə vaxt, sənəd, səbəb, kredit) və geri götürmələri görür. Kart onsuz da
``student.registry_view`` qapısından keçir (``movements.load_registry_record``); burada yalnız əlavə blok qurulur.
«Alt qrupa əlavə et» keçidi yalnız ``retake.manage`` açarı olan aktora verilir (alətin özü əhatəni yenidən yoxlayır).
"""

from __future__ import annotations

from django.urls import reverse

from apps.registrar.public import credit_load, subgroup_access, subgroup_placement_history, subgroup_placement_lookups


def card_payload(request, record) -> dict:
    """Çekməcə JSON-una əlavə sahələr (sabit sorğu sayı: dövr + yük + tarixçə)."""
    organization = record.organization
    period = subgroup_placement_lookups.current_period(organization)
    load = credit_load(record.student, period, organization=organization) if period is not None else None
    placement_url = ""
    if subgroup_access.has_placement_key(request.user, organization) and not getattr(request, "is_view_as", False):
        placement_url = f"{reverse('accounts:profile')}?section=subgroup-placement&student={record.student_id}"
    return {
        "semester_credit": (
            {key: load[key] for key in ("total", "own", "subgroup", "limit", "over_limit")}
            if load and load.get("has_record")
            else None
        ),
        "subgroup_placements": subgroup_placement_history.student_placements(
            student=record.student, organization=organization
        ),
        "subgroup_placement_url": placement_url,
    }


__all__ = ["card_payload"]
