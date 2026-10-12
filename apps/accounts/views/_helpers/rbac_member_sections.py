"""Rol auditi 2026-10-13 (B7, B14) — ``member`` səthləri və «Bildiriş göndər» qapısı.

NİYƏ AYRI MODUL? ``rbac.py`` modul ölçü büdcəsinə (600) dayanıb — məntiq burada, ``rbac.py``-da bir sətirlik
çağırış qalır (``rbac_sections.py`` / ``rbac_university_sections.py`` ilə eyni naxış).

* **B7** — universitetdə ``member`` ≈ xəritələnməmiş ofis işçisidir (mühasib, kitabxanaçı …,
  ``services/staff_roster.py``), «onboarding» tələbəsi deyil. Ona görə universitet tenantında ``member`` tələbə /
  imtahan verən səthlərini (``courses``, ``assigned-exams``, ``assigned-courses``, ``my-results``,
  ``pending-answers``, ``my-appeals``) ALMIR. Məktəb / kurs mərkəzi / fərdi tenantda isə ``member`` hələ də
  «tələbə/müəllim təyinatından əvvəlki» öyrənən roludur (``default_roles.py`` təsvirləri) — orada səthlər qalır.
* **B14** — «Bildiriş göndər» (``publish-notification``) əvvəl rol BAYRAQLARI ilə açılırdı (org_admin aliası,
  müəllim, imtahan mərkəzi, HR) və icazə redaktorundan idarə olunmurdu. İndi açar: ``notification.publish``
  (şablonlar + miqrasiya ``organizations/0062``). ALICI əhatəsi dəyişmir — ``services/notification_scopes.py``
  hələ də rol bayraqları + struktur əhatəsi ilə daraldır; açar yalnız «göndərə bilərmi» sualına cavabdır.
"""

from __future__ import annotations

from core.constants import OrganizationType

from ...models import ProfileRole
from ...policies import user_has_any_role

#: B14 — «Bildiriş göndər» bölməsinin açarı (kataloq: ``organizations/permissions_role_audit.py``).
PERM_NOTIFICATION_PUBLISH = "notification.publish"

#: B7 — ``member`` universitetdə bunları ALMIR (tələbə / imtahan verən səthləri).
MEMBER_LEARNER_SECTIONS = frozenset(
    {"courses", "assigned-exams", "assigned-courses", "my-results", "pending-answers", "my-appeals"}
)


def member_is_learner(user, organization) -> bool:
    """``member`` rolu bu tenantda ÖYRƏNƏNDİRMİ (tələbə səthlərini alırmı)?

    Universitet tenantında YOX (ofis heyəti); digər tenant tiplərində və təşkilat konteksti olmayanda —
    köhnə davranış (bəli). Rol yoxdursa ``False``.
    """
    if not user_has_any_role(user, {ProfileRole.MEMBER}):
        return False
    return getattr(organization, "org_type", None) != OrganizationType.UNIVERSITY


def can_notify(user, organization, *, is_superadmin: bool, is_owner: bool) -> bool:
    """«Bildiriş göndər» — superadmin, təşkilat sahibi və ya REAL ``notification.publish`` açarı (``*`` daxil)."""
    if is_superadmin or is_owner:
        return True
    if organization is None:
        return False
    from core.permissions import has_permission

    from .rbac import _collect_actor_permissions

    permissions, _grantable = _collect_actor_permissions(user, organization)
    return has_permission(list(permissions), PERM_NOTIFICATION_PUBLISH)


__all__ = [
    "MEMBER_LEARNER_SECTIONS",
    "PERM_NOTIFICATION_PUBLISH",
    "can_notify",
    "member_is_learner",
]
