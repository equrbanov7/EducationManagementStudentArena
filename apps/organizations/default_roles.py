"""
Default role templates for different organization types.
"""

from core.constants import OrganizationType, RoleScopeType

DEFAULT_ROLES = {
    OrganizationType.UNIVERSITY: [
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
                "grade.view",
                "grade.publish",
                "appeal.respond",
                "appeal.decide",
                "qa.*",
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
                "grade.view",
                "grade.publish",
                "appeal.respond",
                "appeal.decide",
                "qa.*",
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
            "display_name": "İKT Rəhbəri",
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
                "grade.approve_chair",
                # org_admin-alias davranış qorunması: "chair_head" →
                # "department_head" normallaşır (ADMIN_EQUIVALENT).
                "group.view",
                "group.manage",
                "exam.*",
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
    ],
    OrganizationType.SCHOOL: [
        {
            "name": "director",
            "display_name": "Director",
            "level": 100,
            "scope_type": RoleScopeType.ORGANIZATION,
            "permissions": ["*"],
            "description": "School director with full administrative access",
        },
        {
            "name": "deputy_director",
            "display_name": "Deputy Director",
            "level": 90,
            "scope_type": RoleScopeType.ORGANIZATION,
            "permissions": [
                "org.view",
                "org.edit",
                "unit.*",
                "member.*",
                "course.*",
                "grade.*",
                # org_admin-alias davranış qorunması (level 90 >= 80).
                "group.view",
                "group.manage",
                "exam.*",
                "analytics.view_all",
            ],
            "description": "Deputy director with broad permissions",
        },
        {
            "name": "section_head",
            "display_name": "Section Head",
            "level": 70,
            "scope_type": RoleScopeType.UNIT,
            "permissions": [
                "unit.view",
                "member.view",
                "course.*",
                "grade.*",
                # org_admin-alias davranış qorunması: "section_head" →
                # "department_head" normallaşır (ADMIN_EQUIVALENT).
                "group.view",
                "group.manage",
                "exam.*",
                "analytics.view_unit",
            ],
            "description": "Section head managing teachers and courses",
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
                "assignment.delete",
                "project.delete",
                "lab.delete",
                "analytics.view_own",
            ],
            "description": "Teacher with course and grading permissions",
        },
        {
            "name": "student",
            "display_name": "Student",
            "level": 10,
            "scope_type": RoleScopeType.UNIT,
            "permissions": [
                "course.view",
                "exam.view",
                "analytics.view_own",
            ],
            "description": "Student with view permissions",
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
            "description": "Default onboarding role before student/teacher assignment",
        },
        {
            "name": "parent",
            "display_name": "Parent",
            "level": 5,
            "scope_type": RoleScopeType.UNIT,
            "permissions": [
                "analytics.view_own",
            ],
            "description": "Parent with view access to student data",
        },
    ],
    OrganizationType.COURSE_CENTER: [
        {
            "name": "manager",
            "display_name": "Center Manager",
            "level": 100,
            "scope_type": RoleScopeType.ORGANIZATION,
            "permissions": ["*"],
            "description": "Course center manager with full access",
        },
        {
            "name": "branch_manager",
            "display_name": "Branch Manager",
            "level": 80,
            "scope_type": RoleScopeType.UNIT,
            "permissions": [
                "unit.view",
                "unit.edit",
                "member.*",
                "course.*",
                "grade.*",
                # org_admin-alias davranış qorunması (level 80 >= 80).
                "group.view",
                "group.manage",
                "exam.*",
                "analytics.view_unit",
            ],
            "description": "Branch manager",
        },
        {
            "name": "instructor",
            "display_name": "Instructor",
            "level": 50,
            "scope_type": RoleScopeType.COURSE,
            "permissions": [
                "course.view",
                "course.edit",
                "grade.view",
                "grade.input",
                "exam.*",
                "assignment.delete",
                "project.delete",
                "lab.delete",
                "analytics.view_own",
            ],
            "description": "Course instructor",
        },
        {
            "name": "student",
            "display_name": "Student",
            "level": 10,
            "scope_type": RoleScopeType.UNIT,
            "permissions": [
                "course.view",
                "exam.view",
                "analytics.view_own",
            ],
            "description": "Student enrolled in courses",
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
            "description": "Default onboarding role",
        },
    ],
    OrganizationType.INDIVIDUAL: [
        {
            "name": "owner",
            "display_name": "Owner",
            "level": 100,
            "scope_type": RoleScopeType.ORGANIZATION,
            "permissions": ["*"],
            "description": "Individual owner with full access",
        },
        {
            "name": "collaborator",
            "display_name": "Collaborator",
            "level": 50,
            "scope_type": RoleScopeType.COURSE,
            "permissions": [
                "course.*",
                "grade.*",
                "exam.*",
                "assignment.delete",
                "project.delete",
                "lab.delete",
                "analytics.view_own",
            ],
            "description": "Collaborator with course permissions",
        },
        {
            "name": "student",
            "display_name": "Student",
            "level": 10,
            "scope_type": RoleScopeType.ORGANIZATION,
            "permissions": [
                "course.view",
                "exam.view",
                "analytics.view_own",
            ],
            "description": "Student with view permissions",
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
            "description": "Default onboarding role",
        },
    ],
}


# ---------------------------------------------------------------------------
# Apellyasiya icazələrinin avtomatik əlavəsi
#
# Tək mənbədən qayda: apellyasiya qərarı mərkəzləşdirilib və yalnız
# "exam_center" roluna verilir; imtahanı görən rollar apellyasiya yarada bilər.
# "*" rolları onsuz da hər şeyi əhatə edir. Bu qayda mövcud rollar üçün
# organizations data migration-da da eyni cür tətbiq olunur.
# ---------------------------------------------------------------------------
_EXAM_MANAGEMENT_PERMS = ("exam.*", "exam.create", "exam.edit", "exam.host", "exam.manage")


def _augment_with_appeal_permissions(roles_by_type):
    for roles in roles_by_type.values():
        for role in roles:
            perms = role["permissions"]
            if "*" in perms:
                continue
            manages_exams = any(perm in perms for perm in _EXAM_MANAGEMENT_PERMS)
            views_exams = "exam.view" in perms or "exam.*" in perms
            to_add = []
            if role.get("name") in ("exam_center", "exam_center_head") and manages_exams:
                to_add = ["appeal.create", "appeal.respond", "appeal.decide"]
            elif views_exams:
                to_add = ["appeal.create"]
            for perm in to_add:
                if perm not in perms:
                    perms.append(perm)


_augment_with_appeal_permissions(DEFAULT_ROLES)


def get_default_roles_for_org_type(org_type: str):
    """
    Get default role templates for a specific organization type.

    Args:
        org_type: Organization type constant

    Returns:
        List of role dictionaries for that organization type
    """
    return DEFAULT_ROLES.get(org_type, [])
