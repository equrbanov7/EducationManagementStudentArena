"""İcazə kataloqu və rol defoltları — müraciət açarları."""

from __future__ import annotations

from apps.applications.constants import PERM_CREATE, PERM_HANDLE, PERM_MANAGE, PERM_VIEW_ALL
from apps.organizations.default_roles_university import UNIVERSITY_ROLES
from apps.organizations.permissions import (
    PERMISSION_CATEGORIES,
    PERMISSION_CATEGORY_LABELS,
    PERMISSION_LABELS,
    expand_wildcard_permissions,
    get_all_permissions,
    validate_permissions,
)
from core.permissions import has_permission

ALL_APPLICATION_PERMS = [PERM_CREATE, PERM_HANDLE, PERM_MANAGE, PERM_VIEW_ALL]


def _role(name):
    return next(role for role in UNIVERSITY_ROLES if role["name"] == name)


def test_constants_match_the_catalog():
    assert PERMISSION_CATEGORIES["applications"] == ALL_APPLICATION_PERMS
    assert set(ALL_APPLICATION_PERMS) <= set(get_all_permissions())
    assert PERMISSION_CATEGORY_LABELS["applications"] == "Müraciətlər"


def test_every_application_permission_has_a_label():
    for permission in ALL_APPLICATION_PERMS:
        assert str(PERMISSION_LABELS[permission]).strip()


def test_wildcard_validates_and_expands():
    assert validate_permissions(ALL_APPLICATION_PERMS)
    assert validate_permissions(["application.*"])
    assert expand_wildcard_permissions(["application.*"]) == set(ALL_APPLICATION_PERMS)


def test_almost_every_role_may_send_an_application():
    for name in ("student", "lead_student", "teacher", "assistant", "tutor", "dean", "hr", "exam_center_head"):
        assert has_permission(_role(name)["permissions"], PERM_CREATE), name


def test_archive_role_may_not_send():
    assert not has_permission(_role("alumni")["permissions"], PERM_CREATE)


def test_member_office_staff_may_send():
    """2026-10-13 (rol auditi B7): `member` = vəzifəsi xəritələnməmiş ofis işçisi, onboarding deyil."""
    assert has_permission(_role("member")["permissions"], PERM_CREATE)


def test_handler_roles_hold_the_handle_key():
    for name in (
        "dean",
        "chair_head",
        "program_coordinator",
        # 2026-10-14 (sahib): tyutor = proqram koordinatoru — eyni şöbənin emalçısı.
        "tutor",
        "hr",
        "vice_rector",
        "exam_center_head",
        "exam_center_head",
        "exam_center_staff",
        "ikt_rehber",
    ):
        assert has_permission(_role(name)["permissions"], PERM_HANDLE), name


def test_teachers_and_students_never_decide():
    for name in ("student", "lead_student", "teacher", "assistant", "lab_assistant"):
        assert not has_permission(_role(name)["permissions"], PERM_HANDLE), name
        assert not has_permission(_role(name)["permissions"], PERM_MANAGE), name
        assert not has_permission(_role(name)["permissions"], PERM_VIEW_ALL), name


def test_only_rim_and_vice_rector_manage_the_catalog():
    for name in ("ikt_rehber", "vice_rector"):
        assert has_permission(_role(name)["permissions"], PERM_MANAGE), name
    for name in ("dean", "chair_head", "program_coordinator", "hr", "exam_center_head"):
        assert not has_permission(_role(name)["permissions"], PERM_MANAGE), name
        assert not has_permission(_role(name)["permissions"], PERM_VIEW_ALL), name


def test_rector_wildcard_covers_applications():
    for permission in ALL_APPLICATION_PERMS:
        assert has_permission(_role("rector")["permissions"], permission)


def test_prefix_isolation_from_unrelated_wildcards():
    """`exam.*` / `grade.*` daşıyan rol müraciət qərarını AVTOMATİK ALMIR."""
    assert not has_permission(["exam.*", "grade.*", "course.*", "syllabus.*"], PERM_HANDLE)


def test_rim_staff_reads_and_answers_every_application_but_never_manages():
    """2026-10-24: RİM əməkdaşı «Bütün müraciətlər»i görür; 2026-10-26 (sahib): RİM şöbəsinin
    emalçısıdır və hər müraciətə cavab verir — `handle` var, kataloq açarı (`manage`) yox."""
    permissions = _role("rim_staff")["permissions"]
    assert has_permission(permissions, PERM_VIEW_ALL)
    assert has_permission(permissions, PERM_HANDLE)
    assert not has_permission(permissions, PERM_MANAGE)


def test_trustee_reads_every_application_read_only():
    """Qəyyum «hər oxu açarını» daşıyır (sahib 2026-10-17) — `view_all` da; qərar açarı yox."""
    permissions = _role("trustee")["permissions"]
    assert has_permission(permissions, PERM_VIEW_ALL)
    assert not has_permission(permissions, PERM_HANDLE)
    assert not has_permission(permissions, PERM_MANAGE)


def test_department_roles_do_not_read_the_whole_organization():
    for name in ("dean", "chair_head", "program_coordinator", "hr", "exam_center_head", "student_services"):
        assert not has_permission(_role(name)["permissions"], PERM_VIEW_ALL), name
