"""Rol şablonlarının paylaşılan icazə dəstləri."""

#: RİM-in GÜNDƏLİK hesab əməliyyatları. ``user.*`` wildcard-ı QƏSDƏN
#: işlədilmir — o, ``user.grant_privileged``-i də əhatə edərdi
#: (bax permissions.py «users» kateqoriyası).
RIM_ACCOUNT_PERMISSIONS = [
    "user.search",
    "user.credentials",
    "user.block",
    "user.soft_delete",
    "user.edit",
]

#: «Müəllimlər»/«Tələbələr» kataloqunun YALNIZ-OXU dəsti — siyahı + PII sütunları.
#: Əməl açarları (`people.manage_*`) QƏSDƏN xaricdədir: baxış hüququ heç bir rola
#: avtomatik olaraq hesab dayandırma səlahiyyəti VERMİR.
PEOPLE_DIRECTORY_READ = [
    "people.view_teachers",
    "people.view_students",
    "people.view_contacts",
    "people.view_demographics",
]

#: Kataloqun tam dəsti (oxu + əməl) — yalnız RİM rəhbəri üçün nəzərdə tutulub.
PEOPLE_DIRECTORY_FULL = PEOPLE_DIRECTORY_READ + [
    "people.manage_status",
    "people.manage_teacher_role",
]
