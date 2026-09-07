"""RİM (Rəqəmsal İnkişaf Mərkəzi) əməkdaşı rolu — 2026-09-06 sahib tələbi.

`ikt_rehber` (səviyyə 88) MƏRKƏZİN RƏHBƏRİDİR: akademik və hesab əməllərinin
demək olar hamısı ondadır. Mərkəzin ƏMƏKDAŞLARI üçün ayrıca, MƏHDUD rol lazım
idi — bu modul onu verir. ``default_roles_student_services`` ilə eyni naxış
(ayrı fayl, `UNIVERSITY_ROLES`-a əlavə olunur; seed / migrasiya / test üçün fərq
yoxdur).

⚠️ SƏVİYYƏ 60 QƏSDƏNDİR (80-dən AŞAĞI): ``core.roles.ProfileRole`` `level >= 80`
olan rollara implicit ``org_admin`` aliası verir — əməkdaş tenant idarəetmə
səthini (üzv/rol/təşkilat ayarları) ALMAMALIDIR.

Səlahiyyət ayrılığı (sahib qərarı, 2026-09-06 — «dəstək operatoru» dəsti):

* **VAR** — bütün akademik səthlərin OXUSU (struktur, kataloq, fənn, qiymət,
  cədvəl, sillabus, dərs yükü), imtahan əməlləri (`exam.*`), QA/nəzarət
  (`qa.*`), analitika və audit izi, şəxs kataloqunun oxu dəsti (əlaqə daxil).
* **YOXDUR** — `role.*` (rol vermə), `RIM_ACCOUNT_PERMISSIONS` (parol
  sıfırlama / blok / soft-delete), `user.import`, `journal.correct` /
  `journal.close` / `journal.roster` / `journal.reassign`, `member.*` əməlləri,
  `unit.tree_manage`, `people.manage_*`.

Əlavə səlahiyyət lazım olarsa hər universitet onu permission-editordan verir —
rol şablonu YALNIZ təhlükəsiz başlanğıc dəstidir.
"""

from core.constants import RoleScopeType

from .default_roles_shared import PEOPLE_DIRECTORY_READ

#: RİM əməkdaşının səthi — «görür və köməklik edir», «dəyişdirmir».
_RIM_STAFF_PERMISSIONS = [
    "org.view",
    # Struktur və kataloq — yalnız oxu (fakültə/kafedra/qrup/fənn adları lazımdır).
    "unit.view",
    "catalog.view",
    "member.view",
    "course.view",
    "grade.view",
    "schedule.view",
    "syllabus.view",
    "workload.view",
    # İmtahan mərkəzi ilə birgə iş: sessiya, otaq, bilet, canlı nəzarət.
    "exam.view",
    "exam.create",
    "exam.edit",
    "exam.manage",
    "exam.host",
    # QA / nəzarət növbəsi + hesabatlar.
    "qa.view",
    "qa.flag",
    "qa.review",
    "analytics.view_all",
    "audit.view",
    # Şəxs kataloqu — YALNIZ OXU (əməl açarları `people.manage_*` qəsdən yoxdur).
    *PEOPLE_DIRECTORY_READ,
]

RIM_STAFF_ROLES = [
    {
        "name": "rim_staff",
        "display_name": "Rəqəmsal İnkişaf Mərkəzi (RİM) əməkdaşı",
        "level": 60,
        "scope_type": RoleScopeType.ORGANIZATION,
        "permissions": list(_RIM_STAFF_PERMISSIONS),
        "description": "RİM staff — read-only academic surfaces plus exam and QA operations (no account or role actions)",
    },
]
