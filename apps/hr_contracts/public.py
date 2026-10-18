"""``apps.hr_contracts`` PUBLIC API — «Əmək müqavilələri» (sahib tələbi, 2026-10-19).

Digər modullar (accounts kabineti, şəxs səhifəsi) YALNIZ bu fasaddan və şablon tag-larından
(``{% load hr_contracts_tags %}``) istifadə edir.

══════════════════════════════════════════════════════════════════════════════
MODEL VƏ AXINLAR
══════════════════════════════════════════════════════════════════════════════
* ``EmploymentContract`` — hər HEYƏT üzvü üçün (müəllim, inzibati heyət…; tələbə yox): №, növ (müddətli /
  müddətsiz / əvəzçilik / saathesabı / digər), vəzifə, bölmə, tarixlər, sınaq müddəti, həftəlik saat, ştat,
  fayl (qorunan media), qeyd, status (qaralama / qüvvədədir / xitam / yenilənib), yenilənmə zənciri
  (``renewed_by``), «göndərildi» (``sent_at``) və işçinin təsdiqi (``acknowledged_at``).
* ``EmploymentContractEvent`` — APPEND-ONLY hadisə jurnalı (yaradıldı, redaktə + fərq, fayl, göndərildi,
  təsdiqləndi, xatırlatma (hədd), xitam, yeniləndi).
* Gündəlik iş ``hr_contracts.send_contract_reminders`` (Celery beat 08:30) / ``manage.py send_contract_reminders``
  — hədlər «Sistem tənzimləmələri»ndə (``hr.contract_reminder_days``), hər hədd müqavilə başına BİR dəfə.

══════════════════════════════════════════════════════════════════════════════
KABİNET (accounts) ÜÇÜN
══════════════════════════════════════════════════════════════════════════════
* ``HR_SECTION = "hr-contracts"`` — «Əmək müqavilələri» (``hr.contracts_view`` / ``hr.contracts_manage``);
  ``EMPLOYEE_SECTION = "my-contracts"`` — «Müqavilələrim» (müqaviləsi olan hər əməkdaş).
* ``hr_section_visible(permissions, privileged=…)`` — menyu (sıfır sorğu).
* ``employee_section_visible(user, organization)`` — menyu; ``Organization.settings["hr_contracts_employees"]``
  xülasəsindən SORĞUSUZ (müqavilə yazıları onu atomik yeniləyir).
* Şablon tag-ları: ``hr_contracts_panel``, ``my_contracts_panel``, ``hr_contract_person_card``.
"""

from __future__ import annotations

from core.permissions import has_permission

from .constants import EMPLOYEE_SECTION, HR_SECTION, NON_EMPLOYEE_ROLE_NAMES, PERM_MANAGE, PERM_VIEW, SNAPSHOT_KEY


def hr_section_visible(permissions, *, privileged: bool = False) -> bool:
    permissions = list(permissions or [])
    return bool(privileged or has_permission(permissions, PERM_VIEW) or has_permission(permissions, PERM_MANAGE))


def _student_only(user, organization) -> bool:
    """Middleware-in istifadəçiyə bağladığı aktiv üzvlüklər YALNIZ tələbə ailəsidirsə — sorğusuz «yox»."""
    bound = getattr(user, "_active_organization", None)
    memberships = getattr(user, "_active_org_memberships", None)
    if bound is None or getattr(bound, "pk", None) != organization.pk or not memberships:
        return False
    names = {getattr(getattr(m, "role", None), "name", "") for m in memberships}
    return bool(names) and names <= NON_EMPLOYEE_ROLE_NAMES


def employee_section_visible(user, organization) -> bool:
    """İşçinin görünən müqaviləsi varmı — ``Organization.settings`` xülasəsindən, SORĞUSUZ.

    ``request.organization`` hər sorğuda onsuz da yüklənir; xülasəni müqavilə yazıları
    (``services.contracts.sync_employee_snapshot``) atomik yeniləyir. Açar yoxdursa — müqavilə də yoxdur.
    """
    if organization is None or user is None or not getattr(user, "is_authenticated", False):
        return False
    if _student_only(user, organization):
        return False
    settings = getattr(organization, "settings", None)
    ids = settings.get(SNAPSHOT_KEY) if isinstance(settings, dict) else None
    if not isinstance(ids, list):
        return False
    return user.pk in ids


__all__ = [
    "EMPLOYEE_SECTION",
    "HR_SECTION",
    "PERM_MANAGE",
    "PERM_VIEW",
    "employee_section_visible",
    "hr_section_visible",
]
