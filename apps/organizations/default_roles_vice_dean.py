"""Dekan müavini rolu (`vice_dean`) — 2026-09-06 heyət siyahısı tələbi.

`core/constants.py` bu vəzifəni SƏVİYYƏ cədvəlində (85) tanıyırdı, amma
universitet rol kataloqunda YOX idi: real heyət siyahısında iki dekan müavini
var və onlara rol verilə bilmirdi.

DƏST: dekanın OXU və gündəlik əməliyyat səthi, QƏRAR açarları OLMADAN.
Yəni müavin fakültəni idarə etməyə kömək edir, amma:

* `member.invite` / `member.edit` — YOXDUR (heyət qərarı dekanındır);
* `people.manage_status` — YOXDUR (hesabın girişini dayandırmaq RİM işidir);
* `journal.reassign` — YOXDUR (fənnin təhvili dekan qərarıdır);
* `unit.edit` — YOXDUR (struktur dəyişikliyi).

2026-11-27 (sahib: «dekanlıqda dondurma, bərpa, xaric və s. edə bilsin»): tələbə hərəkəti əmri
(`student.movement` + `people.manage_academic` + `student.registry_view`) və dekanın gündəlik «Qruplar»
açarı `unit.group_manage` ``default_roles_dean_office.apply_dean_office_grants`` ilə verilir (mövcud: 0090).
Bu modul «Dekanlıq laborantı» rolunu da (``DEAN_OFFICE_ROLES``) universitet kataloquna ötürür.

⚠️ SƏVİYYƏ 75 (dekan 80-dir, `chair_head` 70): müavin kafedra müdirindən
yuxarı, dekandan aşağı olmalıdır ki, rol-təyinat iyerarxiyası düzgün işləsin.
`ADMIN_ALIAS_EXEMPT_ROLE_NAMES`-ə ehtiyac yoxdur — 80-dən aşağıdır.
"""

from core.constants import RoleScopeType

from .default_roles_dean_office import DEAN_OFFICE_ROLES
from .default_roles_shared import PEOPLE_DIRECTORY_READ

_VICE_DEAN_PERMISSIONS = [
    "unit.view",
    "member.view",
    "course.view",
    "grade.view",
    "group.view",
    "exam.view",
    "syllabus.view",
    "syllabus.review",
    # Jurnal siyahısı (alt qrupdan əlavə/geri götürmə) — gündəlik dekanlıq işi.
    "journal.roster",
    # Dərs cədvəli: müavin cədvəli qurur (dekanlığın əsas gündəlik yükü).
    "schedule.view",
    "schedule.manage",
    "workload.view",
    "workload.report",
    "analytics.view_unit",
    *PEOPLE_DIRECTORY_READ,
]

VICE_DEAN_ROLES = [
    {
        "name": "vice_dean",
        "display_name": "Dekan müavini",
        "level": 75,
        "scope_type": RoleScopeType.UNIT,
        "permissions": list(_VICE_DEAN_PERMISSIONS),
        "description": "Vice dean — faculty read/day-to-day surface without decision keys",
    },
]

__all__ = ["DEAN_OFFICE_ROLES", "VICE_DEAN_ROLES"]
