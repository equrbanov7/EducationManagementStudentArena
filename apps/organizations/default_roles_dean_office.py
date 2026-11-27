"""Dekanlıq: tələbə hərəkəti (dondurma / bərpa / xaric / qrup dəyişmə) + «Dekanlıq laborantı» rolu — sahib 2026-11-27.

Sahibin sözü: «dekanlıqda dondurma, bərpa, xaric və s. edə bilsin. Köhnə qrup tələbəsini bərpa edərkən hansı qrupa
bərpa olur, onu seçmək olsun» + «hansısa rol nəyisə etməlidirsə və o özəllik yoxdursa, əlavə et».

──────────────────────────────────────────────────────────────────────────────
1. Dekan / dekan müavini — hərəkət əmri
──────────────────────────────────────────────────────────────────────────────
Hərəkət İKİQAT qapıdır (``accounts.services.people.movements``): ``student.movement`` (əmri yazmaq) VƏ
``people.manage_academic`` (akademik qeydə toxunmaq). Hər ikisi EYNİ rolda olmalıdır — bərpa əmri hesabın girişini
açan SECURITY DEFINER funksiyası (``accounts/0021``) rolun açarlarını ``?&`` ilə yoxlayır. ``student.registry_view`` —
«Tələbə reyestri» bölməsi (əmr tarixçəsi, «Hərəkət əmri» düyməsi).

Əhatə UNIT-dir: üzvlüyün ``scope_unit``-i (fakültə) alt-ağacı. Yazı əhatəsi DAR qalır
(``people.permissions._FACULTY_READ_PERMISSIONS`` yalnız oxu açarlarını genişləndirir) — A fakültəsinin dekanı B
fakültəsinin tələbəsini tapmır (404), hədəf qrup da əhatədə olmalıdır (``movements._target_group``).

Müavinə (``default_roles_vice_dean``) bunlardan əlavə dekanın gündəlik «Qruplar» açarı ``unit.group_manage`` (tələbə
əlavə et, «Qrupu dəyiş», starosta, «Qrupu məzun et»). Qərar açarları (``member.invite`` / ``member.edit`` /
``unit.edit`` / ``journal.reassign``) müavinə VERİLMİR. Tyutor / proqram koordinatoru bu dəstdən KƏNARDADIR
(``permissions_tutor_circle``: «dekanlıq, tyutor yox»).

──────────────────────────────────────────────────────────────────────────────
2. «Dekanlıq laborantı» (``dean_office_assistant``)
──────────────────────────────────────────────────────────────────────────────
Əvvəl yox idi: heyət siyahısında dekanlıq laborantları ``lab_assistant``-a (kafedra rolu — dərs yükü, kafedra
müraciətləri) düşürdü. Yeni rol dekanlığın gündəlik səthidir: «Qruplar» (baxış + idarə, tələbə əlavə et, starosta),
jurnal siyahısı (alt qrup), tələbə hərəkəti, «Tələbə reyestri», dərs cədvəli, «Dekanlıq» müraciətləri, kataloq
(yalnız oxu). Dərs yükü, sillabus / sual təsdiqi, üzv idarəsi YOXDUR.

⚠️ SƏVİYYƏ 58 QƏSDƏNDİR (mühasib kimi): 80-dən aşağı — ``org_admin`` aliası yoxdur; 60-dan aşağı —
``User.is_teacher_or_above`` köhnə müəllim səthlərini açmır (laborant dərs demir; dərs deyirsə müəllim üzvlüyü ayrıdır).

Mövcud tenantlar: miqrasiya ``organizations/0089``; mövcud laborant üzvlükləri ƏMRLƏ köçürülür
(``reassign_dean_office_laborants_20261127``, defolt dry-run).
"""

from __future__ import annotations

from core.constants import RoleScopeType

from .default_roles_shared import PEOPLE_DIRECTORY_READ

DEAN_OFFICE_ASSISTANT_ROLE = "dean_office_assistant"
DEAN_OFFICE_ASSISTANT_LEVEL = 58

#: Tələbə hərəkətinin açarları (dekan / müavin / laborant üçün EYNİ; miqrasiya 0089 dondurur).
DEAN_OFFICE_MOVEMENT_PERMISSIONS = (
    "student.movement",
    "people.manage_academic",
    "student.registry_view",
)

#: Mövcud rollara verilən açarlar (şablon: ``apply_dean_office_grants``; mövcud tenantlar: 0089).
DEAN_OFFICE_GRANTS: dict[str, tuple[str, ...]] = {
    "dean": DEAN_OFFICE_MOVEMENT_PERMISSIONS,
    "vice_dean": (*DEAN_OFFICE_MOVEMENT_PERMISSIONS, "unit.group_manage"),
}

DEAN_OFFICE_ASSISTANT_PERMISSIONS = (
    # «Qruplar» — baxış + idarə (tələbə əlavə et, «Qrupu dəyiş», starosta, «Qrupu məzun et»).
    "unit.view",
    "unit.group_manage",
    "member.view",
    "course.view",
    # Jurnal siyahısı: alt qrupdan əlavə / geri götürmə, «Fəndən azad et».
    "journal.roster",
    # Tələbə hərəkəti + reyestr + «Tarixçə».
    *DEAN_OFFICE_MOVEMENT_PERMISSIONS,
    "student.records_view",
    # Dərs cədvəli.
    "schedule.view",
    "schedule.manage",
    # «Dekanlıq» şöbəsinin müraciətləri (``applications.constants`` → ``dekan``).
    "application.create",
    "application.handle",
    # Kataloq — yalnız oxu.
    *PEOPLE_DIRECTORY_READ,
)

DEAN_OFFICE_ROLES = [
    {
        "name": DEAN_OFFICE_ASSISTANT_ROLE,
        "display_name": "Dekanlıq laborantı",
        "level": DEAN_OFFICE_ASSISTANT_LEVEL,
        "scope_type": RoleScopeType.UNIT,
        "permissions": list(DEAN_OFFICE_ASSISTANT_PERMISSIONS),
        "description": "Dean's office assistant — groups, student movement, registry, schedule, dean's office requests",
    },
]

#: Laborant fakültəyə / dekanlığa bağlıdırsa bu rol, kafedraya bağlıdırsa ``lab_assistant`` (``staff_roster``).
DEAN_OFFICE_UNIT_TYPES = frozenset({"faculty", "deanery"})


def apply_dean_office_grants(roles):
    """``DEAN_OFFICE_GRANTS`` — şablonlara idempotent əlavə (``*`` / ``<prefiks>.*`` daşıyana toxunmur)."""
    for role in roles:
        keys = DEAN_OFFICE_GRANTS.get(role.get("name"), ())
        permissions = role.setdefault("permissions", [])
        if "*" in permissions:
            continue
        for key in keys:
            if key not in permissions and f"{key.split('.', 1)[0]}.*" not in permissions:
                permissions.append(key)
    return roles


__all__ = [
    "DEAN_OFFICE_ASSISTANT_LEVEL",
    "DEAN_OFFICE_ASSISTANT_PERMISSIONS",
    "DEAN_OFFICE_ASSISTANT_ROLE",
    "DEAN_OFFICE_GRANTS",
    "DEAN_OFFICE_MOVEMENT_PERMISSIONS",
    "DEAN_OFFICE_ROLES",
    "DEAN_OFFICE_UNIT_TYPES",
    "apply_dean_office_grants",
]
