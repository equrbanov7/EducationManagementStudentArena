"""Qəyyumlar Şurası üzvü + İnzibati şöbə müdiri — 2026-09-06 sahib qərarı.

Heyət siyahısı (119 nəfər) sistemə salınanda iki vəzifə qrupunun sistemdə
qarşılığı yox idi; sahib hər ikisi üçün rol yaradılmasını təsdiqlədi.

──────────────────────────────────────────────────────────────────────────────
1. ``trustee`` — Qəyyumlar Şurası üzvü (səviyyə 78)
──────────────────────────────────────────────────────────────────────────────

NƏZARƏT orqanıdır, İCRA orqanı deyil: universitetin gedişatına baxır, qərar
səthlərinə toxunmur. Ona görə dəstdə **bir dənə də yazma açarı yoxdur**.

⚠️ SƏVİYYƏ 78 QƏSDƏNDİR. ``core.roles.ProfileRole`` `level >= 80` olan hər rola
implicit ``org_admin`` aliası verir (bax `aliases_for_membership_role`) — yəni
80 və yuxarı qoysaq, qəyyum səssizcə bütün tenant idarəetmə səthini (üzv, rol,
təşkilat ayarları) alardı. Alternativ ``ADMIN_ALIAS_EXEMPT_ROLE_NAMES``-ə əlavə
etmək olardı, amma o siyahı «yüksək səviyyə lazımdır, amma admin yox» halları
üçündür; qəyyumun səviyyəyə əsaslanan heç bir səthə ehtiyacı yoxdur.

2026-10-17 (sahib: «qəyyumlar şurası üçün hər şeyi açıq edə bilərsən»): bütün OXU
açarları verildi — fərdi qiymətlər, jurnal, tələbə/müəllim kataloqu, kontakt və
demoqrafik sütunlar da. Yazma açarı əvvəlki kimi YOXDUR, view-as yalnız-oxu.

──────────────────────────────────────────────────────────────────────────────
2. ``admin_unit_head`` — İnzibati şöbə müdiri (səviyyə 65, UNIT əhatəsi)
──────────────────────────────────────────────────────────────────────────────

Mühasibatlıq, kadrlar, təsərrüfat, hüquq, beynəlxalq əlaqələr və s. — AKADEMİK
olmayan şöbələrin müdirləri (heyət siyahısında 39 nəfər).

⚠️ NİYƏ MÖVCUD ``section_head`` DEYİL: o rol `default_roles.py`-dakı MƏKTƏB
dəstindəndir, məzmunu akademikdir (`course.*`, `grade.*`, `exam.*`) və
``ROLE_NAME_NORMALIZATION`` onu ``department_head``-ə çevirir — o ad isə
``ADMIN_EQUIVALENT_ROLE_NAMES``-dədir, yəni org_admin aliası gəlir. İnzibati
şöbə müdirinə nə akademik yazma, nə də tenant idarəetməsi lazım deyil.

Dəst: öz vahidinin oxu səthi + şəxs kataloqu + vahid analitikası. Kadrlar/
mühasibatlıq kimi şöbələrə əlavə açar lazım olsa (məs. `people.manage_status`)
universitet onu permission-editordan verir — şablon YALNIZ təhlükəsiz
başlanğıcdır.
"""

from core.constants import RoleScopeType

from .default_roles_shared import PEOPLE_DIRECTORY_READ

#: Qəyyum: hər şeyi GÖRÜR, heç nəyi DƏYİŞMİR — bir dənə də yazma açarı yoxdur.
#: Sahib 2026-10-17: «qəyyumlar şurası üçün hər şeyi açıq edə bilərsən» → kataloqdakı BÜTÜN oxu açarları
#: (fərdi qiymətlər, jurnal, tələbə/müəllim kataloqu, kontakt və demoqrafik sütunlar da). Texniki
#: `system.monitoring.view` (server logları) nəzarət səthi deyil — verilmir.
TRUSTEE_READ_ALL_2026_10_17 = (
    "analytics.view_unit",
    "exam.view",
    "grade.view",
    "group.view",
    "journal.view",
    "people.hr_analytics",
    "people.view_contacts",
    "people.view_demographics",
    "people.view_students",
    "people.view_teachers",
    "plan.view",
    "role.view",
    "semester.view",
    "student.records_view",
    "student.registry_view",
    "survey.results.view",
    "user.search",
)
_TRUSTEE_PERMISSIONS = [
    "unit.view",
    "member.view",
    "catalog.view",
    "course.view",
    "schedule.view",
    "syllabus.view",
    "workload.view",
    "workload.report",
    # Nəzarət orqanının əsas iki səthi: aqreqat hesabatlar və audit izi
    # (CSV ixracı da — `audit.export`, audit 2026-09-13 F-06 / 2026-09-14).
    "analytics.view_all",
    "audit.view",
    "audit.export",
    *TRUSTEE_READ_ALL_2026_10_17,
]

#: İnzibati şöbə müdiri: öz vahidi + kataloq oxusu.
_ADMIN_UNIT_HEAD_PERMISSIONS = [
    "unit.view",
    "member.view",
    "catalog.view",
    "schedule.view",
    "analytics.view_unit",
    *PEOPLE_DIRECTORY_READ,
]

#: Sahib 2026-10-11: Qəyyumlar Şurasının sədri (Hüseynqulu Bağırov) — «rektor kimi hər şeyə çıxışı olsun,
#: superadmin olmasın, siyahının başında dursun». Ona görə `*` (təşkilat daxilində rektorla eyni) və səviyyə
#: 110 — rektordan (100) yuxarı, üzv reyestrinin «Rol (yuxarıdan aşağı)» sırasında birinci. Superadmin DEYİL:
#: platforma səthləri (`is_superuser`) və başqa təşkilatlar açılmır. Adi qəyyumlar 78-də, yalnız oxuda qalır.
BOARD_CHAIR_ROLE = "board_chair"

OVERSIGHT_ROLES = [
    {
        "name": BOARD_CHAIR_ROLE,
        "display_name": "Qəyyumlar Şurasının sədri",
        "level": 110,
        "scope_type": RoleScopeType.ORGANIZATION,
        "permissions": ["*"],
        "description": "Chair of the board of trustees — full organization access like the rector (not superadmin)",
    },
    {
        "name": "trustee",
        "display_name": "Qəyyumlar Şurası üzvü",
        "level": 78,
        "scope_type": RoleScopeType.ORGANIZATION,
        "permissions": list(_TRUSTEE_PERMISSIONS),
        "description": "Board of trustees member — sees everything read-only (no write keys)",
    },
    {
        "name": "admin_unit_head",
        "display_name": "İnzibati şöbə müdiri",
        "level": 65,
        "scope_type": RoleScopeType.UNIT,
        "permissions": list(_ADMIN_UNIT_HEAD_PERMISSIONS),
        "description": "Administrative department head — own unit read surface, no academic or tenant keys",
    },
]
