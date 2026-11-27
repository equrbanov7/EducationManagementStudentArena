"""Hesab əməliyyatlarının (blok / blokun açılması / bərpa) audit sətrinin təşkilatı."""

from __future__ import annotations


def audit_organization(user, actor=None, organization=None):
    """Audit sətrinin təşkilatı: açıq ``organization`` > hədəfin ``profile.organization`` > hədəfin aktiv
    üzvlüyü > aparanın təşkilatı > None.

    2026-11-27: blok / blokun açılması / bərpa sətirləri ``organization=None`` yazılırdı — təşkilat
    audit jurnalı (``scoped_queryset``) yalnız öz təşkilatının sətirlərini göstərdiyi üçün «kim blokladı»
    sualının cavabı RİM-ə görünmürdü (Dmitriy Sevaçyev hadisəsi).
    """
    if organization is not None:
        return organization
    own = getattr(getattr(user, "profile", None), "organization", None)
    if own is not None:
        return own
    from apps.organizations.models import Membership

    membership = (
        Membership.objects.filter(user=user, is_active=True)
        .select_related("organization")
        .order_by("-is_primary", "created_at")
        .first()
    )
    if membership is not None:
        return membership.organization
    return getattr(getattr(actor, "profile", None), "organization", None)
