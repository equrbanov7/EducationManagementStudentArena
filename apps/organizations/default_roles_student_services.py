"""Tələbə Xidmətləri Mərkəzi rolu — qəbul və reyestrin sahibi (handoff Mərhələ 3).

``default_roles_university`` modul ölçü büdcəsinə (SOFT_CAP=600) dayandığı üçün
rol AYRI faylda saxlanılır və oradan ``UNIVERSITY_ROLES``-a əlavə olunur —
seed axını, migration və testlər üçün fərq yoxdur (eyni siyahıdır).
``default_roles_teaching_office`` ilə EYNİ naxış.

⚠️ SƏVİYYƏ 60 QƏSDƏNDİR (80-dən AŞAĞI): ``core.roles.ProfileRole``
``level >= 80`` olan rollara implicit ``org_admin`` aliası verir. Tələbə
Xidmətləri Mərkəzi əməliyyat rolu (qəbul, reyestr, hərəkət əmri) olduğu üçün
tenant idarəetmə səthini (üzv/rol/təşkilat ayarları) ALMAMALIDIR, ona görə
``ADMIN_ALIAS_EXEMPT_ROLE_NAMES`` siyahısına da ehtiyac yoxdur — səviyyə
onsuz da hədddən aşağıdır (``teaching_office_head`` 85-də olduğu üçün oraya
əlavə edilməli idi; bura DEYİL).

Səlahiyyət ayrılığı (əsasnamə 5.5) burada da saxlanılır:

* ``user.import``          — YENİ kimlik gətirmək (ekran 08). RİM-in
  ``user.credentials`` / ``user.block`` açarları VERİLMİR: qəbul operatoru
  mövcud hesabın parolunu sıfırlaya bilməməlidir.
* ``student.movement``     — əmr-əsaslı akademik hərəkət (ekran 09).
* ``people.manage_academic`` — hərəkətin FAKTİKİ icrası mövcud mexanizmdən
  (``registrar.transfer`` + status state-machine) keçir; açar ona görə lazımdır.
"""

from core.constants import RoleScopeType

#: Tələbə Xidmətləri Mərkəzinin səthi — qəbul (08), reyestr (09), tələbə
#: kataloqu (people-students) və müraciətlərin «telebe» şöbəsi (11).
_STUDENT_SERVICES_PERMISSIONS = [
    "org.view",
    # Struktur/kataloq — YALNIZ OXU (qrup, ixtisas, fakültə adları lazımdır).
    "unit.view",
    "catalog.view",
    "member.view",
    # Ekran 08 — ATİS qəbulu.
    "user.import",
    "student.assign_group",
    # Ekran 09 — reyestr + hərəkət əmrləri.
    "student.registry_view",
    "student.movement",
    # Kataloq səthi + hərəkətin faktiki icrası.
    "people.view_students",
    "people.view_contacts",
    "people.view_demographics",
    "people.manage_academic",
]

STUDENT_SERVICES_ROLES = [
    {
        "name": "student_services",
        "display_name": "Tələbə Xidmətləri Mərkəzi",
        "level": 60,
        "scope_type": RoleScopeType.ORGANIZATION,
        "permissions": list(_STUDENT_SERVICES_PERMISSIONS),
        "description": "Student services centre — admission intake, student registry and movement orders",
    },
]

#: Mövcud rollara verilən YENİ `student.*` açarları (rol yaradılmır).
#:
#: * RİM (`ikt_rehber`) — operator: hər üç açar.
#: * dekan / proqram koordinatoru — YALNIZ REYESTR BAXIŞI; əmr yazmaq
#:   Tələbə Xidmətləri Mərkəzinin işidir (handoff §5/09 «Tələbə hərəkəti
#:   rektor əmri ilə rəsmiləşir»). Onların gördüyü dəst struktur SCOPE-una
#:   tabedir (dekan öz fakültəsi, koordinator öz ixtisası) — §8/8.
#: * prorektor — nəzarət baxışı.
#: * rektorda `*` var, siyahıda yoxdur.
STUDENT_SERVICES_GRANTS: dict[str, tuple[str, ...]] = {
    "ikt_rehber": ("student.registry_view", "student.movement", "student.assign_group"),
    "dean": ("student.registry_view",),
    "program_coordinator": ("student.registry_view",),
    "vice_rector": ("student.registry_view",),
}


def apply_student_services_grants(roles):
    """``STUDENT_SERVICES_GRANTS``-i rol siyahısına idempotent tətbiq edir."""
    for role in roles:
        wanted = STUDENT_SERVICES_GRANTS.get(role.get("name"))
        if not wanted:
            continue
        permissions = role.setdefault("permissions", [])
        if "*" in permissions:
            continue
        for permission in wanted:
            prefix_wildcard = f"{permission.split('.', 1)[0]}.*"
            if permission in permissions or prefix_wildcard in permissions:
                continue
            permissions.append(permission)
    return roles


__all__ = [
    "STUDENT_SERVICES_ROLES",
    "STUDENT_SERVICES_GRANTS",
    "apply_student_services_grants",
]
