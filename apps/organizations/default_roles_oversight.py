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

Qəsdən VERİLMƏYƏNLƏR: fərdi qiymətlər (`grade.view`), şəxs kataloqunun PII
sütunları (`people.view_contacts` / `people.view_demographics`), imtahan
əməlləri. Şura ÜMUMİ mənzərəni (analitika + audit izi) görür; fərdi tələbə
məlumatı lazım olarsa universitet onu permission-editordan əlavə edir.

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

#: Qəyyum: yalnız ÜMUMİ mənzərə — bir dənə də yazma açarı yoxdur.
_TRUSTEE_PERMISSIONS = [
    "org.view",
    "unit.view",
    "member.view",
    "catalog.view",
    "course.view",
    "schedule.view",
    "syllabus.view",
    "workload.view",
    # Nəzarət orqanının əsas iki səthi: aqreqat hesabatlar və audit izi.
    "analytics.view_all",
    "audit.view",
]

#: İnzibati şöbə müdiri: öz vahidi + kataloq oxusu.
_ADMIN_UNIT_HEAD_PERMISSIONS = [
    "org.view",
    "unit.view",
    "member.view",
    "catalog.view",
    "schedule.view",
    "analytics.view_unit",
    *PEOPLE_DIRECTORY_READ,
]

OVERSIGHT_ROLES = [
    {
        "name": "trustee",
        "display_name": "Qəyyumlar Şurası üzvü",
        "level": 78,
        "scope_type": RoleScopeType.ORGANIZATION,
        "permissions": list(_TRUSTEE_PERMISSIONS),
        "description": "Board of trustees member — read-only oversight (analytics and audit trail, no write keys)",
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
