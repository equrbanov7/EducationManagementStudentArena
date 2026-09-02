"""Universitet tipli təşkilatların default rol şablonları.

``default_roles`` modulundan modul ölçü budcəsinə (SOFT_CAP=600) görə
ayrılıb — MƏZMUN DƏYİŞMƏYİB, yalnız yer dəyişib.
"""

from core.constants import RoleScopeType

from .default_roles_shared import (
    PEOPLE_DIRECTORY_FULL,
    PEOPLE_DIRECTORY_READ,
    RIM_ACCOUNT_PERMISSIONS,
)

UNIVERSITY_ROLES = [
    {
        "name": "rector",
        "display_name": "Rector",
        "level": 100,
        "scope_type": RoleScopeType.ORGANIZATION,
        "permissions": ["*"],
        "description": "University rector with full administrative access",
    },
    {
        "name": "vice_rector",
        "display_name": "Vice Rector",
        "level": 90,
        "scope_type": RoleScopeType.ORGANIZATION,
        "permissions": [
            "org.view",
            "org.edit",
            "unit.*",
            "member.*",
            "course.*",
            "grade.*",
            # Qrup açarları — DAVRANIŞ QORUNMASI: rol əvvəl org_admin-alias
            # (ADMIN_EQUIVALENT ad / level>=80, core/roles.py) ilə qrup yaradırdı.
            "group.view",
            "group.manage",
            "exam.*",
            # Sillabus: prorektor bütün axını görür və qərar verə bilir.
            "syllabus.*",
            # Dərs yükü: yekun təsdiq + ümumi dashboard (spec §6.5).
            "workload.*",
            *RIM_ACCOUNT_PERMISSIONS,
            # Kataloq: prorektor bütün təşkilatı görür və hesab dayandıra bilir
            # (org-scope rol → `get_permission_scope` org-wide qaytarır).
            *PEOPLE_DIRECTORY_READ,
            "people.manage_status",
            "people.manage_teacher_role",
            # Tələbə idarəetməsi (qrup köçürməsi + akademik status) — prorektor
            # org-scope-ludur, yəni bütün fakültələr üzrə səlahiyyətlidir.
            "people.manage_academic",
            # Fənnin başqa müəllimə TƏHVİLİ (`journal.reassign`) — «müəllim işdən
            # çıxdı, jurnal artıq başqasının olsun». Əhatə struktur scope-una
            # tabedir; müəllimin özündə bu açar YOXDUR (öz jurnalını ata bilməz).
            "journal.reassign",
            "analytics.view_all",
            "audit.view",
        ],
        "description": "Vice rector with broad administrative permissions",
    },
    {
        # İmtahan mərkəzi — imtahan həyat dövrünü (yaratma, təyinat,
        # monitorinq, nəticə, apellyasiya) idarə edir; üzv/struktur
        # idarəetməsinə girişi YOXDUR (admin-alias exempt).
        "name": "exam_center",
        "display_name": "Exam Center",
        "level": 85,
        "scope_type": RoleScopeType.ORGANIZATION,
        "permissions": [
            "org.view",
            "unit.view",
            "member.view",
            "course.view",
            "exam.*",
            # final_score.entry `exam.*`-a DAXİL DEYİL (ayrıca prefiks) — açıq verilir.
            "final_score.entry",
            "grade.view",
            "grade.publish",
            "appeal.respond",
            "appeal.decide",
            "qa.*",
            # Kataloq: imtahan mərkəzi iştirakçıları tapmaq üçün org-wide OXU alır;
            # hesab dayandırma / müəllim statusu QƏSDƏN yoxdur (kadr işi deyil).
            "people.view_teachers",
            "people.view_students",
            "analytics.view_all",
            "audit.view",
        ],
        "description": "Exam center managing exam lifecycle, monitoring, results and appeals",
    },
    {
        # İmtahan mərkəzi RƏHBƏRİ — imtahan mərkəzinin başçısı; zala nəzarətçi
        # təyin edə bilir (yeganə fərq). Digər imtahan səlahiyyətləri exam_center
        # ilə eynidir. is_exam_center → final mərkəzinə giriş.
        "name": "exam_center_head",
        "display_name": "Exam Center Head",
        "level": 85,
        "scope_type": RoleScopeType.ORGANIZATION,
        "permissions": [
            "org.view",
            "unit.view",
            "member.view",
            "course.view",
            "exam.*",
            # final_score.entry `exam.*`-a DAXİL DEYİL (ayrıca prefiks) — açıq verilir.
            "final_score.entry",
            "grade.view",
            "grade.publish",
            "appeal.respond",
            "appeal.decide",
            "qa.*",
            "people.view_teachers",
            "people.view_students",
            "people.view_contacts",
            "analytics.view_all",
            "audit.view",
        ],
        "description": "Exam center head — assigns invigilators and manages the exam centre",
    },
    {
        # İKT Rəhbəri — texniki/akademik super-operator. Jurnal limitlərini
        # (2 saat pəncərəsi, bitmiş semestr) sənədli DÜZƏLİŞ (journal.correct →
        # PDF + audit) ilə keçir; kollokvium keçmiş-kilidini keçir; imtahan
        # mərkəzinin tam səlahiyyəti + üzv/struktur idarəsi. Bütün əməllər audit.
        "name": "ikt_rehber",
        # Slug QƏSDƏN `ikt_rehber` qalır (kodda 20+ hardcoded istinad var);
        # yalnız görünən ad RİM-ə dəyişib.
        "display_name": "Rəqəmsal İnkişaf Mərkəzi (RİM) rəhbəri",
        "level": 88,
        "scope_type": RoleScopeType.ORGANIZATION,
        "permissions": [
            "org.view",
            "org.edit",
            "unit.*",
            "member.*",
            "course.*",
            "exam.*",
            "grade.*",
            # org_admin-alias davranış qorunması (level 88 >= 80).
            "group.view",
            "group.manage",
            "journal.correct",
            # Semestr sonu jurnal bağlama/açma (sahibin qərarı, 2026-08) —
            # təsdiq zəncirini əvəz edən yeganə açar. Başqa rola lazım olsa
            # permission-editordan verilir.
            "journal.close",
            # Jurnal siyahısının idarəsi (alt qrupdan əlavə/geri götürmə) —
            # RİM org-wide operatordur, əməl audit olunur.
            "journal.roster",
            # Fənnin başqa müəllimə TƏHVİLİ (`journal.reassign`) — «müəllim işdən
            # çıxdı, jurnal artıq başqasının olsun». Əhatə struktur scope-una
            # tabedir; müəllimin özündə bu açar YOXDUR (öz jurnalını ata bilməz).
            "journal.reassign",
            # Dərs cədvəli (U4): RİM org-wide cədvəl operatorudur — slot əlavə/sil.
            "schedule.view",
            "schedule.manage",
            # Sillabus axınının tam səlahiyyəti (idarə + qərar) — RİM sistemin
            # akademik operatorudur; hər əməl audit olunur.
            "syllabus.*",
            # Dərs yükü də RİM-in operator səthidir (bütün kafedralar).
            "workload.*",
            # Əsasnamə 4.2 — «rol və səlahiyyət idarəetməsi» RİM-dədir.
            "role.*",
            # `user.grant_privileged` YOXDUR: yeni admin yaratmaq ayrıca açardır.
            *RIM_ACCOUNT_PERMISSIONS,
            # Tələbə idxalı (2026-09) — RİM cutover operatorudur: qəbul siyahısını
            # yükləyib hesab + üzvlük + akademik qeyd yaradır (hər sətir audit olunur).
            "user.import",
            # Sahibin qərarı: «RİM mərkəzinin hər şeyə səlahiyyəti olsun» —
            # kataloqun tam dəsti (oxu + hesab dayandırma + müəllim statusu).
            *PEOPLE_DIRECTORY_FULL,
            # RİM akademik operatordur: köçürmə/status əməllərini o da apara bilir
            # (hər əməl audit olunur, rəsmi sübut zənciri dəyişmir).
            "people.manage_academic",
            "appeal.respond",
            "appeal.decide",
            "qa.*",
            "analytics.view_all",
            "audit.view",
        ],
        "description": "ICT manager — documented journal-correction override (bypasses edit-window & closed semesters), full exam-centre + structure access; every action audited",
    },
    {
        # İmtahan mərkəzi İŞÇİSİ — monitor / PIN axtarışı / hesabat; zala
        # nəzarətçi TƏYİN ETMİR (yalnız rəhbər). is_exam_center → giriş var.
        "name": "exam_center_staff",
        "display_name": "Exam Center Staff",
        "level": 60,
        "scope_type": RoleScopeType.ORGANIZATION,
        "permissions": [
            "org.view",
            "unit.view",
            "member.view",
            "course.view",
            "exam.*",
            "grade.view",
            "qa.*",
            "analytics.view_all",
            "audit.view",
        ],
        "description": "Exam center staff — live monitoring, PIN lookup and reports (no invigilator assignment)",
    },
    {
        # HR — müəllim/əməkdaş idarəetməsi, vəzifə və fakültə/kafedra
        # təyinatları. İmtahan/kurs idarəetməsinə girişi yoxdur.
        "name": "hr",
        "display_name": "HR",
        "level": 65,
        "scope_type": RoleScopeType.ORGANIZATION,
        "permissions": [
            "org.view",
            "unit.view",
            "member.view",
            "member.invite",
            "member.edit",
            "member.remove",
            "role.view",
            "role.assign",
            # RİM-in yalnız QEYRİ-DAĞIDICI hissəsi (tap + düzəlt).
            "user.search",
            "user.edit",
            # Tələbə idxalı — qəbul siyahısının yüklənməsi kadr/qeydiyyat işidir.
            # Dağıdıcı açar DEYİL: mövcud hesabı dəyişmir, yalnız yeni sətir yaradır
            # (mövcud FİN/username ötürülür).
            "user.import",
            # Kadr kataloqu: HR tam OXU + müəllim statusu təyinatı alır.
            # `people.manage_status` QƏSDƏN YOXDUR — HR-da `user.block` da yoxdur,
            # yəni hesab dayandırma səlahiyyəti bu rolda ümumiyyətlə mövcud deyil.
            *PEOPLE_DIRECTORY_READ,
            "people.manage_teacher_role",
            "analytics.view_unit",
            "audit.view",
        ],
        "description": "HR managing staff, positions and faculty/department assignments",
    },
    {
        "name": "dean",
        "display_name": "Dean",
        "level": 80,
        "scope_type": RoleScopeType.UNIT,
        "permissions": [
            "unit.view",
            "unit.edit",
            "member.view",
            "member.invite",
            "member.edit",
            "course.*",
            "grade.*",
            # org_admin-alias davranış qorunması ("dean" ADMIN_EQUIVALENT-də).
            "group.view",
            "group.manage",
            "exam.*",
            # Sillabus: dekan fakültə üzrə baxır və qərar verir, amma müəllimin
            # qaralamasını REDAKTƏ ETMİR (`syllabus.edit` QƏSDƏN yoxdur).
            "syllabus.view",
            "syllabus.review",
            "syllabus.approve",
            "syllabus.revise",
            "syllabus.reject",
            # Kataloq: dekan YALNIZ öz fakültəsinin alt-ağacını görür və orada
            # hesab dayandıra bilir (UNIT scope → `get_permission_scope`;
            # `scope_unit` təyin edilməyibsə siyahı BOŞ qalır, fail-closed).
            *PEOPLE_DIRECTORY_READ,
            "people.manage_status",
            # Dekanlığın əsas tələbə əməli: öz fakültəsi daxilində qrup
            # köçürməsi və akademik status (məzuniyyət/xaric/məzun).
            "people.manage_academic",
            # Jurnal siyahısı: dekanlıq öz fakültəsinin jurnalına başqa (alt)
            # qrupdan tələbə əlavə edə/geri götürə bilər (audited, scope-lu).
            "journal.roster",
            # Dərs yükü: dekan öz fakültəsinin yükünü GÖRÜR və hesabat çıxarır;
            # bölgü açarı (`workload.distribute`) QƏSDƏN yoxdur — o, kafedranındır.
            "workload.view",
            "workload.report",
            # Fənnin başqa müəllimə TƏHVİLİ (`journal.reassign`) — «müəllim işdən
            # çıxdı, jurnal artıq başqasının olsun». Əhatə struktur scope-una
            # tabedir; müəllimin özündə bu açar YOXDUR (öz jurnalını ata bilməz).
            "journal.reassign",
            # Dərs cədvəli: dekanlıq öz fakültəsinin cədvəlini qura bilər
            # (əhatə `Membership.scope_unit` alt-ağacı ilə məhduddur).
            "schedule.view",
            "schedule.manage",
            "analytics.view_unit",
        ],
        "description": "Faculty dean managing a specific faculty",
    },
    {
        "name": "chair_head",
        "display_name": "Department Chair",
        "level": 70,
        "scope_type": RoleScopeType.UNIT,
        "permissions": [
            "unit.view",
            "member.view",
            "course.*",
            "grade.view",
            "grade.input",
            # org_admin-alias davranış qorunması (chair_head → department_head).
            "group.view",
            "group.manage",
            "exam.*",
            # Sillabus təsdiqinin ƏSAS sahibi — YALNIZ öz kafedrası
            # (Membership.scope_unit → apps.syllabus.services.scoping, fail-closed).
            # `syllabus.edit` QƏSDƏN yoxdur: müdir müəllimin mətnini özü yazmır,
            # düzəliş tələbi ilə geri qaytarır.
            "syllabus.view",
            "syllabus.review",
            "syllabus.approve",
            "syllabus.revise",
            "syllabus.reject",
            # Fənn təhvili: kafedra müdiri ÖZ KAFEDRASININ fənnini başqa müəllimə
            # verə bilər (UNIT scope → yalnız öz alt-ağacı; `scope_unit` təyin
            # edilməyibsə siyahı BOŞ qalır, fail-closed).
            "journal.reassign",
            # Dərs yükü: kafedra müdiri modulun ƏSAS aktorudur — tapşırığı
            # yaradır/redaktə edir və müəllimlərə bölür (yalnız öz kafedrası).
            # `workload.approve` QƏSDƏN yoxdur: dekanlıq təsdiqi ayrı fazadır.
            "workload.view",
            "workload.manage",
            "workload.distribute",
            "workload.report",
            # Kataloq: kafedra müdiri öz kafedrasının müəllim/tələbəsini GÖRÜR.
            # Əməl açarları QƏSDƏN yoxdur — lazım olsa icazə redaktorundan verilir.
            "people.view_teachers",
            "people.view_students",
            "people.view_contacts",
            # Dərs cədvəli: kafedra müdiri öz kafedrasının cədvəlini qura bilər
            # (dekanlığın müavini kimi — əhatə `scope_unit` alt-ağacıdır).
            "schedule.view",
            "schedule.manage",
            "analytics.view_unit",
        ],
        "description": "Department chair managing courses and faculty",
    },
    {
        "name": "teacher",
        "display_name": "Teacher",
        "level": 50,
        "scope_type": RoleScopeType.COURSE,
        "permissions": [
            "course.view",
            "course.create",
            "course.edit",
            "grade.view",
            "grade.input",
            "exam.view",
            "exam.create",
            "exam.edit",
            "exam.host",
            "exam.delete",
            # Sillabus: müəllim YAZIR və GÖNDƏRİR; təsdiq/rədd açarları YOXDUR.
            "syllabus.view",
            "syllabus.edit",
            "syllabus.submit",
            # Dərs yükü: müəllim YALNIZ ÖZ bölgü sətirlərini görür («Dərs yüküm»);
            # sorğu qatı `teacher=request.user` ilə daraldılıb (fail-closed).
            "workload.view",
            "assignment.delete",
            "project.delete",
            "lab.delete",
            "analytics.view_own",
        ],
        "description": "Teacher with course management and grading permissions",
    },
    {
        "name": "assistant",
        "display_name": "Teaching Assistant",
        "level": 40,
        "scope_type": RoleScopeType.COURSE,
        "permissions": [
            "course.view",
            "grade.view",
            "exam.view",
            "analytics.view_own",
        ],
        "description": "Teaching assistant with limited permissions",
    },
    {
        # Laborant — laboratoriya işlərinə dəstək. Öz kursunun/labının
        # tapşırıqlarını görür və qiymətləndirməyə kömək edir; imtahan
        # yaratmır, üzv idarə etmir. RBAC-də ASSISTANT_TEACHER-ə map olunur
        # (bax core/roles.py MEMBERSHIP_ROLE_ALIASES / map_org_role_to_profile_role).
        "name": "lab_assistant",
        "display_name": "Lab Assistant",
        "level": 40,
        "scope_type": RoleScopeType.COURSE,
        "permissions": [
            "course.view",
            "grade.view",
            "grade.input",
            "exam.view",
            "analytics.view_own",
        ],
        "description": "Laboratory assistant supporting lab work and grading within their course",
    },
    {
        # Tyutor — tələbə qruplarına akademik dəstək/kurasiya rolu.
        # Öz scope_unit alt-ağacındakı tələbələri, kursları, imtahan
        # cədvəlini və qrup statistikasını görür; imtahan yaratmır,
        # qiymət vermir, üzv idarə etmir.
        "name": "tutor",
        "display_name": "Tutor",
        "level": 40,
        "scope_type": RoleScopeType.UNIT,
        "permissions": [
            "member.view",
            "course.view",
            "exam.view",
            # Kataloq: tyutor öz alt-ağacındakı TƏLƏBƏLƏRİ görür (müəllimləri yox).
            "people.view_students",
            "analytics.view_unit",
        ],
        "description": "Tutor providing academic guidance to student groups within their unit",
    },
    {
        # Proqram koordinatoru — ixtisas/proqram üzrə akademik kurasiya.
        # İşi əsasən tyutorla eynidir (öz alt-ağacındakı tələbə/kurs/imtahan
        # cədvəli və qrup statistikasını görür); imtahan yaratmır, qiymət
        # vermir, üzv idarə etmir. RBAC-də tyutorla eyni səviyyədə davranır.
        "name": "program_coordinator",
        "display_name": "Program Coordinator",
        "level": 45,
        "scope_type": RoleScopeType.UNIT,
        "permissions": [
            "member.view",
            "course.view",
            "exam.view",
            "people.view_students",
            # Koordinator öz ixtisasının qrupları arasında tələbə köçürür və
            # akademik statusu qeyd edir (əhatə ixtisas alt-ağacı ilə məhduddur).
            "people.manage_academic",
            # Proqram koordinatorunun ƏSAS əməli: öz ixtisasının jurnallarına
            # alt qrupdan tələbə əlavə etmək / geri götürmək (audited, scope-lu).
            "journal.roster",
            # Dərs cədvəlinin ƏSAS sahibi (sahibin qərarı, 2026-09): koordinator
            # öz ixtisasının qruplarına slot yazır/silir. Adi MÜƏLLİMDƏ bu açar
            # QƏSDƏN YOXDUR — müəllim öz cədvəlini yalnız GÖRÜR.
            "schedule.view",
            "schedule.manage",
            "analytics.view_unit",
        ],
        "description": "Program coordinator curating a specialty/program (tutor-equivalent scope)",
    },
    {
        # Baş tələbə — adi tələbə + öz qrupuna aid məhdud üzv siyahısı
        # və qrup səviyyəli statistika.
        "name": "lead_student",
        "display_name": "Lead Student",
        "level": 30,
        "scope_type": RoleScopeType.UNIT,
        "permissions": [
            "course.view",
            "exam.view",
            "appeal.create",
            "member.view",
            "analytics.view_own",
        ],
        "description": "Lead student with limited group-level visibility",
    },
    {
        "name": "student",
        "display_name": "Student",
        "level": 10,
        "scope_type": RoleScopeType.UNIT,
        "permissions": [
            "course.view",
            "exam.view",
            "appeal.create",
            "analytics.view_own",
        ],
        "description": "Student with view and self-service permissions",
    },
    {
        # ARXİV ROLU — məzun/xaric (legacy ``students.azadedildi=1``) hesablar.
        # İcazə dəsti QƏSDƏN BOŞDUR: rol heç bir hüquq VERMİR, yalnız
        # ``registrar_guard_active_member`` trigger-inin tələb etdiyi AKTİV
        # üzvlüyü təmin edir ki, tarixi jurnal/qiymət sətirləri köçə bilsin.
        # Giriş isə ``UserProfile.access_state='archived'`` ilə bağlanır
        # (bax apps/accounts/services/identity_archive.py).
        "name": "alumni",
        "display_name": "Məzun / arxiv",
        "level": 5,
        "scope_type": RoleScopeType.UNIT,
        "permissions": [],
        "description": "Archived alumni/released student — no access, historical records only",
    },
    {
        "name": "member",
        "display_name": "Member",
        "level": 20,
        "scope_type": RoleScopeType.ORGANIZATION,
        "permissions": [
            "course.view",
            "exam.view",
            "analytics.view_own",
        ],
        "description": "Default onboarding role before specialized assignment",
    },
]


# ────────────────────────────────────────────────────────────────────────────
# Müraciətlər (apps.applications) — default icazə paylanması.
#
# Niyə DÖVRƏ ilə, yuxarıdakı literal siyahılara əl ilə yazmaqla deyil? Üç açar
# 15+ rola paylanır və qayda MƏTNLƏ ifadə oluna bilir («məzun və onboarding
# rolundan başqa hamı müraciət göndərə bilər»). Dövrə həmin qaydanı KOD kimi
# saxlayır — yeni rol əlavə olunanda avtomatik doğru davranır, 15 yerə əl ilə
# açar yazmaq unudulmur.
# ────────────────────────────────────────────────────────────────────────────

#: Müraciət GÖNDƏRƏ bilməyən rollar: `alumni` (arxiv — heç bir hüququ yoxdur),
#: `member` (təyinatdan əvvəlki onboarding rolu), `rector` (`*` ilə onsuz da
#: əhatə olunur — açarı təkrar yazmaq kataloqu şişirdir).
_APPLICATION_CREATE_EXEMPT = {"alumni", "member", "rector"}

#: GƏLƏN müraciətə qərar verən rollar (şöbə emalçıları). Açar səthi açır;
#: konkret müraciətə əməl həm də şöbənin `handler_role_names`-inə düşməkdən
#: asılıdır (apps/applications/services/access.py).
_APPLICATION_HANDLER_ROLES = {
    "dean",
    "chair_head",
    "program_coordinator",
    "hr",
    "vice_rector",
    "exam_center",
    "exam_center_head",
    "exam_center_staff",
    "ikt_rehber",
}

#: Kataloq konfiqurasiyası + bütün müraciətlərə oxu (rektor `*` ilə əhatəlidir).
_APPLICATION_MANAGER_ROLES = {"ikt_rehber", "vice_rector"}


def _grant_application_permissions(roles):
    for role in roles:
        name = role.get("name")
        permissions = role.setdefault("permissions", [])
        if "*" in permissions:
            continue
        wanted = []
        if name not in _APPLICATION_CREATE_EXEMPT:
            wanted.append("application.create")
        if name in _APPLICATION_HANDLER_ROLES:
            wanted.append("application.handle")
        if name in _APPLICATION_MANAGER_ROLES:
            wanted.append("application.manage")
        for permission in wanted:
            if permission not in permissions:
                permissions.append(permission)
    return roles


_grant_application_permissions(UNIVERSITY_ROLES)
