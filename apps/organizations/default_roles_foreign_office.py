"""«Əcnəbi tələbələrlə iş şöbəsi» rolları — YALNIZ əcnəbi qrupları üzrə (sahib 2026-11-25).

Sahibin sözü: «Beynəlxalq şöbə əməkdaşı rolu olsun, burdakı əməkdaşlar əcnəbilərdən bu formada (01-əcnəbilər2026 …)
əcnəbi qruplarını görsün, 5 ədəddi bizdə; qrupla tələbə əlavə etmək, dondurmaq, uzaqlaşdırmaq olsun. Sonra tələbəni
sistemə əlavə etmək də olsun … tələbənin köhnə datasını görə bilsin, yenidən dönsə belə statistik olaraq dondurana kimi
neçə qiyməti var idi baxa bilsin … əcnəbilərin hər şeyini görə bilsinlər, elə bil proqram koordinatorunun».

──────────────────────────────────────────────────────────────────────────────
Rollar
──────────────────────────────────────────────────────────────────────────────
* ``foreign_students_head``  — «Əcnəbi tələbələrlə iş şöbəsinin müdiri» (səviyyə 55);
* ``foreign_students_staff`` — «Əcnəbi tələbələrlə iş şöbəsinin əməkdaşı» (səviyyə 50).

Hər ikisi EYNİ dəsti daşıyır. Səviyyə 80-dən AŞAĞIDIR (``core.roles`` ``level >= 80``-ə ``org_admin`` aliası verir).

──────────────────────────────────────────────────────────────────────────────
ƏHATƏ — UNIT, hər əcnəbi QRUPU üçün ayrıca üzvlük
──────────────────────────────────────────────────────────────────────────────
Əcnəbi qrupları «Lifelong» fakültəsinin «Lifelong» ixtisasının altındadır, orada başqa qruplar da var (0055 / …).
Ona görə üzvlük fakültəyə / ixtisasa YOX, hər qrupun özünə bağlanır (``Membership.scope_unit`` = qrup;
``unique_together`` rol+bölmə üzrədir — bir nəfərə 5 üzvlük). Mövcud qapıların hamısı (``get_permission_scope``)
əlavə kod olmadan həmin 5 qrupla daralır.

⚠️ OXU genişlənməsi QƏSDƏN söndürülüb: ``scoping.faculty_read_scope`` qrup / ixtisas köklərini fakültəyə genişləndirir
(tyutor və kafedra müdiri üçün sahib qaydası, 2026-10-14). Bu rollar üçün kök OLDUĞU KİMİ qalır
(``EXACT_SCOPE_ROLE_NAMES``) — əks halda şöbə bütün «Lifelong» fakültəsini görərdi.

Yeni əcnəbi qrupu açılanda şöbəyə əhatə «Rol təyin et» ilə və ya ``sync_foreign_students_office`` əmri ilə verilir
(əmr ADINDA «əcnəbi» olan aktiv qrupları tapır — miqrasiya ``organizations/0087`` də eyni qaydanı işlədir).

──────────────────────────────────────────────────────────────────────────────
Açarlar
──────────────────────────────────────────────────────────────────────────────
Proqram koordinatorunun YEKUN dəsti (``default_roles_university._COORDINATOR_PERMISSIONS`` + sonrakı modulların
verilişləri, tyutor paritetinin dəsti), bunlardan BAŞQA:

* ＋ ``student.movement`` — dondurmaq (akademik məzuniyyət), uzaqlaşdırmaq (xaric), bərpa; əmr nömrəsi + tarix məcburi
  (``accounts.services.people.movements``). Əhatə akademik qeydin QRUPU ilə yoxlanır (``people.manage_academic``).
* ＋ ``user.import`` — tələbəni sistemə əlavə etmək (tək-tək forma + toplu fayl). Əhatə qapısı tələbənin QRUPUNA
  baxır: əhatəsi org-wide olmayan aktor yalnız öz qruplarına yaza bilər (``accounts.services.intake.scope``).
* ＋ ``journal.view`` / ``grade.view`` — öz qruplarının jurnalları (bal / davamiyyət oxu).
* － ``workload.view`` / ``workload.review`` — dərs yükü kafedraların işidir; ``application.handle`` — müraciət
  emalçısı deyil (yalnız ``application.create``, hamıdakı kimi).

Dondurulmuş / qayıtmış tələbənin dondurulana qədərki statistikası (fənn üzrə bal sayı, orta bal, iştirak / qayıb):
qrup çekmecəsində «Tarixçə» — ``organizations.group_student_history`` (``student.records_view`` daşıyana).
"""

from __future__ import annotations

from core.constants import RoleScopeType

FOREIGN_STUDENTS_HEAD_ROLE = "foreign_students_head"
FOREIGN_STUDENTS_STAFF_ROLE = "foreign_students_staff"

#: Əhatəsi fakültəyə GENİŞLƏNMƏYƏN rollar (``scoping.faculty_read_scope``).
EXACT_SCOPE_ROLE_NAMES = frozenset({FOREIGN_STUDENTS_HEAD_ROLE, FOREIGN_STUDENTS_STAFF_ROLE})

#: Şöbənin dəsti — iki rol üçün EYNİ (miqrasiya 0087 eyni dəsti sətir-sətir dondurur; test kilidləyir).
FOREIGN_STUDENTS_PERMISSIONS = (
    # ── proqram koordinatoru pariteti ──
    "member.view",
    "course.view",
    "exam.view",
    "appeal.create",
    "people.view_students",
    "people.view_contacts",
    "people.view_demographics",
    "people.manage_academic",
    "group.manage",
    "unit.view",
    "unit.group_manage",
    "student.assign_group",
    "student.records_view",
    "student.registry_view",
    "journal.roster",
    "journal.reassign",
    "journal.lab_groups",
    "journal.level_cohorts",
    "catalog.view",
    "plan.view",
    "schedule.view",
    "schedule.manage",
    "syllabus.view",
    "subject_folder.view_unit",
    "analytics.view_unit",
    # ── şöbənin əlavələri ──
    "student.movement",
    "user.import",
    "journal.view",
    "grade.view",
)

FOREIGN_STUDENTS_ROLES = [
    {
        "name": FOREIGN_STUDENTS_HEAD_ROLE,
        "display_name": "Əcnəbi tələbələrlə iş şöbəsinin müdiri",
        "level": 55,
        "scope_type": RoleScopeType.UNIT,
        "permissions": list(FOREIGN_STUDENTS_PERMISSIONS),
        "description": "Foreign students office head — full student circle limited to the foreign-student groups",
    },
    {
        "name": FOREIGN_STUDENTS_STAFF_ROLE,
        "display_name": "Əcnəbi tələbələrlə iş şöbəsinin əməkdaşı",
        "level": 50,
        "scope_type": RoleScopeType.UNIT,
        "permissions": list(FOREIGN_STUDENTS_PERMISSIONS),
        "description": "Foreign students office staff — full student circle limited to the foreign-student groups",
    },
]

#: Şöbə bölməsindəki köhnə rol → yeni rol (miqrasiya 0087 / ``sync_foreign_students_office``).
DEPARTMENT_ROLE_MAP = {"admin_unit_head": FOREIGN_STUDENTS_HEAD_ROLE, "member": FOREIGN_STUDENTS_STAFF_ROLE}
#: Bölmə / qrup adındakı açar söz (İ/I/ı və böyük/kiçik hərf fərqsiz).
UNIT_KEYWORD = "əcnəbi"
#: Şöbə akademik bölmə ola bilməz (qrup adında da «əcnəbi» var — o, ƏHATƏDİR, şöbə deyil).
ACADEMIC_UNIT_TYPES = frozenset({"faculty", "chair", "specialty", "group", "deanery"})


def fold(text) -> str:
    value = str(text or "")
    for source, target in (("İ", "i"), ("I", "i"), ("ı", "i"), ("Ə", "ə")):
        value = value.replace(source, target)
    return value.lower()


def is_foreign_office_unit(name, unit_type="") -> bool:
    """«Əcnəbi tələbələrlə iş şöbəsi»dirmi (akademik bölmə deyil, adında «əcnəbi»)."""
    return unit_type not in ACADEMIC_UNIT_TYPES and UNIT_KEYWORD in fold(name)


def is_foreign_group(name, unit_type="group") -> bool:
    """Əcnəbi qrupudurmu: ``group`` tipli və adında «əcnəbi» (``01-əcnəbilər2026``, ``04-əcnəbilər 2026``)."""
    return unit_type == "group" and UNIT_KEYWORD in fold(name)


__all__ = [
    "DEPARTMENT_ROLE_MAP",
    "EXACT_SCOPE_ROLE_NAMES",
    "FOREIGN_STUDENTS_HEAD_ROLE",
    "FOREIGN_STUDENTS_PERMISSIONS",
    "FOREIGN_STUDENTS_ROLES",
    "FOREIGN_STUDENTS_STAFF_ROLE",
    "fold",
    "is_foreign_group",
    "is_foreign_office_unit",
]
