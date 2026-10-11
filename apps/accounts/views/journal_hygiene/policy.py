"""«Jurnal təmizliyi» bölməsinin AKTOR qapısı (sahib 2026-10-10).

Görünürlük «Köçürülmüş nəticələr» və «Sistem tənzimləmələri» ilə EYNİDİR: YALNIZ RİM rəhbəri
(``ikt_rehber`` üzvlüyü) və superadmin — menyu qapısı ``_helpers/rbac_sections.py``-dadır, bu modul onu
hər endpoint-də təkrarlayır. Yazı hüququ əlavə olaraq registrar servis qatında yoxlanılır
(``journal_hygiene_actions.can_apply`` — təşkilat miqyaslı ``journal.correct`` və ya superadmin).
«Başqasının adından» (view-as) rejimində bölmə yalnız oxunur.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.registrar.public import journal_hygiene_actions as hygiene_write


@dataclass(frozen=True)
class HygieneActor:
    """Sorğu üçün həll olunmuş aktor (fail-closed)."""

    user: object
    organization: object | None
    has_access: bool
    can_apply: bool
    view_as: bool


_NOBODY = HygieneActor(user=None, organization=None, has_access=False, can_apply=False, view_as=False)


def _is_superadmin(user) -> bool:
    return bool(getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False))


def resolve_actor(request) -> HygieneActor:
    """Sorğudan aktoru qurur; heç vaxt exception atmır."""
    from apps.accounts.views._helpers.rbac_sections import _is_rim_head
    from apps.accounts.views._helpers.tenant import _get_active_organization

    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return _NOBODY
    organization = _get_active_organization(request)
    view_as = bool(getattr(request, "is_view_as", False))
    if organization is None or not (_is_superadmin(user) or _is_rim_head(user, organization)):
        return HygieneActor(user=user, organization=organization, has_access=False, can_apply=False, view_as=view_as)
    can_apply = not view_as and hygiene_write.can_apply(user, organization)
    return HygieneActor(user=user, organization=organization, has_access=True, can_apply=can_apply, view_as=view_as)


__all__ = ["HygieneActor", "resolve_actor"]
