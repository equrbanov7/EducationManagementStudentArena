"""«Mühasib» (``accountant``) rolu + 25% təkrar imtahan açarlarının verilişi (sahib 2026-10-18).

Kataloq: ``permissions_accounting.py``. Mövcud tenantlar: miqrasiya ``0067_accounting_retake_permissions``
(eyni xəritə — miqrasiya şablonu İMPORT ETMİR, dəyərlər orada sətir-sətir köçürülüb).

──────────────────────────────────────────────────────────────────────────────
``accountant`` — Mühasib (səviyyə 58, ORGANIZATION əhatəsi)
──────────────────────────────────────────────────────────────────────────────

İşi: «Mühasibatlıq» bölməsi (müəllim × ay: keçirilmiş saat, plan, fərq, Excel) və 25% təkrar imtahanın
ödəniş qəbzinin yoxlanması. RİM rəhbəri «Rol təyin et»dən verir (rol ORGANIZATION əhatəlidir — vahid-əhatəli
aktor onu verə bilmir; səviyyə RİM-in 95-indən aşağıdır).

⚠️ SƏVİYYƏ 58 QƏSDƏNDİR:

* 80-dən AŞAĞI — ``core.roles.ProfileRole`` `level >= 80` olan rola implicit ``org_admin`` aliası verir
  (bax ``default_roles_oversight.py`` şərhi): mühasib tenant idarəetmə səthini ALMAMALIDIR;
* 60-dan AŞAĞI — ``User.is_teacher_or_above`` (``ROLE_LEVEL_TEACHER`` = 60) köhnə müəllim səthlərini
  (kurs/bloq rəyi və s.) səviyyə ilə açır; mühasib dərs demir.

Dəst MİNİMALDIR — yalnız iki iş açarı. Tələbə şəxsi məlumatı açarı YOXDUR (``student_privacy.STUDENT_ACCOUNT_PERMISSIONS``
-dan heç biri) və sahibin «tələbə PII-si yoxdur» qaydası ilə ``unit.view`` də verilmir: struktur ağacı qrupların
starostalarının adlarını göstərir. ``people.view_teachers`` / ``member.view`` də lazım deyil — bölmə müəllim
adlarını, fakültə / kafedra seçimlərini öz servisində (``accounts/services/accounting``) ``accounting.view`` ilə oxuyur.
"""

from core.constants import RoleScopeType

from .permissions_accounting import (
    PERM_ACCOUNTING_MANAGE_FEES,
    PERM_ACCOUNTING_VIEW,
    PERM_RETAKE_MANAGE,
    PERM_RETAKE_PAYMENT_VERIFY,
)

ACCOUNTANT_ROLE = "accountant"

ACCOUNTANT_PERMISSIONS = (
    PERM_ACCOUNTING_VIEW,
    PERM_RETAKE_PAYMENT_VERIFY,
    PERM_ACCOUNTING_MANAGE_FEES,
)

ACCOUNTING_ROLES = [
    {
        "name": ACCOUNTANT_ROLE,
        "display_name": "Mühasib",
        "level": 58,
        "scope_type": RoleScopeType.ORGANIZATION,
        "permissions": list(ACCOUNTANT_PERMISSIONS),
        "description": "Accountant — monthly held teaching hours vs plan (read-only) and retake payment checks",
    },
]

#: Mövcud rollara VERİLƏN açarlar. ``*`` daşıyanlar (rektor, Qəyyumlar Şurasının sədri, RİM rəhbəri) onsuz da
#: əhatəlidir — ``ikt_rehber`` siyahıdadır ki, tenantda ``*`` daraldılıbsa da açar qalsın.
ACCOUNTING_GRANTS: dict[str, tuple[str, ...]] = {
    "ikt_rehber": (PERM_ACCOUNTING_VIEW, PERM_RETAKE_MANAGE, PERM_ACCOUNTING_MANAGE_FEES),
    "trustee": (PERM_ACCOUNTING_VIEW,),
    "dean": (PERM_RETAKE_MANAGE,),
    "vice_dean": (PERM_RETAKE_MANAGE,),
    "teaching_office_head": (PERM_RETAKE_MANAGE,),
    "teaching_office_staff": (PERM_RETAKE_MANAGE,),
}


def _covered(permissions, key) -> bool:
    return key in permissions or f"{key.split('.', 1)[0]}.*" in permissions or "*" in permissions


def apply_accounting_grants(roles):
    """``ACCOUNTING_GRANTS``-ı rol şablonlarına idempotent tətbiq edir (yerində)."""
    for role in roles:
        permissions = role.setdefault("permissions", [])
        for key in ACCOUNTING_GRANTS.get(role.get("name"), ()):
            if not _covered(permissions, key):
                permissions.append(key)
    return roles


__all__ = [
    "ACCOUNTANT_PERMISSIONS",
    "ACCOUNTANT_ROLE",
    "ACCOUNTING_GRANTS",
    "ACCOUNTING_ROLES",
    "apply_accounting_grants",
]
