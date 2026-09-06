"""İcazə kataloqu və rol defoltları — sillabus açarları."""

from __future__ import annotations

from apps.organizations.default_roles_university import UNIVERSITY_ROLES
from apps.organizations.permissions import (
    PERMISSION_CATEGORIES,
    PERMISSION_LABELS,
    expand_wildcard_permissions,
    get_all_permissions,
    validate_permissions,
)
from apps.syllabus.constants import (
    PERM_APPROVE,
    PERM_EDIT,
    PERM_MANAGE,
    PERM_REJECT,
    PERM_REVIEW,
    PERM_REVISE,
    PERM_SUBMIT,
    PERM_VIEW,
)
from core.permissions import has_permission

ALL_SYLLABUS_PERMS = [
    PERM_VIEW,
    PERM_EDIT,
    PERM_SUBMIT,
    PERM_REVIEW,
    PERM_APPROVE,
    PERM_REVISE,
    PERM_REJECT,
    PERM_MANAGE,
]


def _role(name):
    return next(role for role in UNIVERSITY_ROLES if role["name"] == name)


def test_constants_match_the_catalog():
    assert PERMISSION_CATEGORIES["syllabus"] == ALL_SYLLABUS_PERMS
    catalog = set(get_all_permissions())
    assert set(ALL_SYLLABUS_PERMS) <= catalog


def test_every_syllabus_permission_has_a_label():
    for permission in ALL_SYLLABUS_PERMS:
        assert str(PERMISSION_LABELS[permission]).strip()


def test_wildcard_validates_and_expands():
    assert validate_permissions(ALL_SYLLABUS_PERMS)
    assert validate_permissions(["syllabus.*"])
    assert expand_wildcard_permissions(["syllabus.*"]) == set(ALL_SYLLABUS_PERMS)


def test_teacher_writes_and_submits_but_never_decides():
    permissions = _role("teacher")["permissions"]
    assert has_permission(permissions, PERM_EDIT)
    assert has_permission(permissions, PERM_SUBMIT)
    for decision in (PERM_APPROVE, PERM_REVISE, PERM_REJECT, PERM_REVIEW, PERM_MANAGE):
        assert not has_permission(permissions, decision), decision


def test_chair_head_decides_but_does_not_edit_the_draft():
    permissions = _role("chair_head")["permissions"]
    for decision in (PERM_VIEW, PERM_REVIEW, PERM_APPROVE, PERM_REVISE, PERM_REJECT):
        assert has_permission(permissions, decision), decision
    assert not has_permission(permissions, PERM_EDIT)
    assert not has_permission(permissions, PERM_SUBMIT)


def test_dean_reads_and_reviews_but_never_decides():
    """SAHİBİN QƏRARI (2026-09-03): təsdiq YALNIZ kafedra müdirinindir.

    Əvvəl dekan kafedra müdirinin dəstini GÜZGÜLƏYİRDİ və fakültə scope-u
    alt-ağacdakı bütün kafedraları örtdüyü üçün de-fakto təsdiqçi o idi.
    İndi dekan növbəni açır, oxuyur və şərh yazır — qərar açarı yoxdur.
    """
    permissions = _role("dean")["permissions"]
    assert has_permission(permissions, PERM_VIEW)
    assert has_permission(permissions, PERM_REVIEW)
    for decision in (PERM_APPROVE, PERM_REVISE, PERM_REJECT, PERM_EDIT):
        assert not has_permission(permissions, decision), decision


def test_rim_and_vice_rector_hold_the_whole_family():
    for name in ("ikt_rehber", "vice_rector"):
        permissions = _role(name)["permissions"]
        for permission in ALL_SYLLABUS_PERMS:
            assert has_permission(permissions, permission), f"{name} → {permission}"


def test_rector_wildcard_covers_syllabus():
    assert has_permission(_role("rector")["permissions"], PERM_APPROVE)


def test_unrelated_roles_get_nothing_by_default():
    for name in ("student", "assistant", "tutor", "hr", "exam_center_head"):
        permissions = _role(name)["permissions"]
        for permission in ALL_SYLLABUS_PERMS:
            assert not has_permission(permissions, permission), f"{name} → {permission}"


def test_final_score_style_prefix_isolation():
    """`exam.*` daşıyan rol sillabus qərarını AVTOMATİK ALMIR."""
    assert not has_permission(["exam.*", "grade.*", "course.*"], PERM_APPROVE)
