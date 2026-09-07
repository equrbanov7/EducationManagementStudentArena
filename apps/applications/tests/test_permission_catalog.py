"""İcazə kataloqu və rol defoltları — müraciət açarları."""

from __future__ import annotations

from apps.applications.constants import PERM_CREATE, PERM_HANDLE, PERM_MANAGE
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

ALL_APPLICATION_PERMS = [PERM_CREATE, PERM_HANDLE, PERM_MANAGE]


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


def test_archive_and_onboarding_roles_may_not_send():
    for name in ("alumni", "member"):
        assert not has_permission(_role(name)["permissions"], PERM_CREATE), name


def test_handler_roles_hold_the_handle_key():
    for name in (
        "dean",
        "chair_head",
        "program_coordinator",
        "hr",
        "vice_rector",
        "exam_center_head",
        "exam_center_head",
        "exam_center_staff",
        "ikt_rehber",
    ):
        assert has_permission(_role(name)["permissions"], PERM_HANDLE), name


def test_teachers_and_students_never_decide():
    for name in ("student", "lead_student", "teacher", "assistant", "tutor", "lab_assistant"):
        assert not has_permission(_role(name)["permissions"], PERM_HANDLE), name
        assert not has_permission(_role(name)["permissions"], PERM_MANAGE), name


def test_only_rim_and_vice_rector_manage_the_catalog():
    for name in ("ikt_rehber", "vice_rector"):
        assert has_permission(_role(name)["permissions"], PERM_MANAGE), name
    for name in ("dean", "chair_head", "program_coordinator", "hr", "exam_center_head"):
        assert not has_permission(_role(name)["permissions"], PERM_MANAGE), name


def test_rector_wildcard_covers_applications():
    for permission in ALL_APPLICATION_PERMS:
        assert has_permission(_role("rector")["permissions"], permission)


def test_prefix_isolation_from_unrelated_wildcards():
    """`exam.*` / `grade.*` daşıyan rol müraciət qərarını AVTOMATİK ALMIR."""
    assert not has_permission(["exam.*", "grade.*", "course.*", "syllabus.*"], PERM_HANDLE)
