"""Fənn qovluğu cədvəllərinin DB səviyyəli tenant izolyasiyası (RLS + FORCE).

Nümunə: ``apps/syllabus/tests/test_rls.py``. Data bypass rejimində yaradılır, sonra
tranzaksiya daxilində ``SET LOCAL ROLE rls_app_role`` ilə məhdud rola keçilir
(``emsarena_agent`` superuser + BYPASSRLS olduğu üçün mənfi assert-lər onunla yalançı keçərdi).
"""

from __future__ import annotations

from django.db import DatabaseError, connection, transaction

import pytest

from apps.subject_folder import public
from apps.subject_folder.models import (
    FolderAssignment,
    FolderMaterial,
    FolderTask,
    FolderTopic,
    SubjectFolder,
    Submission,
    SubmissionEvent,
)

from . import factories as f

pytestmark = pytest.mark.postgres

TABLES = [
    "subject_folder_subjectfolder",
    "subject_folder_foldertopic",
    "subject_folder_foldermaterial",
    "subject_folder_foldertask",
    "subject_folder_taskattachment",
    "subject_folder_folderassignment",
    "subject_folder_taskdeadline",
    "subject_folder_submission",
    "subject_folder_submissionfile",
    "subject_folder_submissionevent",
    "subject_folder_submissionfingerprint",
    "subject_folder_similaritymatch",
]


def _set(name, value):
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config(%s, %s, false)", [name, str(value)])


def _as_tenant(org_id):
    _set("app.bypass_rls", "off")
    _set("app.current_org_id", str(org_id))
    _set("app.current_user_id", "")
    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL ROLE rls_app_role")


@pytest.fixture(autouse=True)
def _bypass_while_building(db):
    if connection.vendor != "postgresql":
        pytest.skip("RLS testləri PostgreSQL tələb edir")
    _set("app.bypass_rls", "on")
    try:
        yield
    finally:
        _set("app.bypass_rls", "off")
        _set("app.current_org_id", "")


def _tenant():
    org = f.make_org()
    teacher = f.make_teacher(org)
    offering = f.make_offering(org, subject=f.make_subject(org), period=f.make_period(org), instructor=teacher)
    student = f.make_student(org)
    f.enroll(offering, student)
    f.approve_syllabus(offering, teacher)
    folder, _c, _s = public.create_folder(
        organization=org, subject=offering.subject, owner=teacher, by_user=teacher, period=offering.period
    )
    assignment = public.assign_folder(folder, [offering], by_user=teacher)[0]["assignment"]
    homework = public.create_homework(folder, by_user=teacher, title="Ev", is_published=True)
    public.create_material(folder, by_user=teacher, kind="note", title="Qeyd", description="x", is_published=True)
    public.submit(task=homework, assignment=assignment, student=student, text="cavab")
    return org


def test_every_table_has_forced_policy():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = ANY(%s)", [TABLES]
        )
        rows = {name: (rls, forced) for name, rls, forced in cursor.fetchall()}
    assert set(rows) == set(TABLES)
    assert all(rls and forced for rls, forced in rows.values()), rows


def test_rows_are_tenant_isolated():
    org_a = _tenant()
    org_b = _tenant()
    _as_tenant(org_a.pk)
    for model in (
        SubjectFolder,
        FolderTopic,
        FolderMaterial,
        FolderTask,
        FolderAssignment,
        Submission,
        SubmissionEvent,
    ):
        assert set(model.objects.values_list("organization_id", flat=True)) == {org_a.pk}, model
    assert not SubjectFolder.objects.filter(organization=org_b).exists()


def test_missing_tenant_context_denies_all():
    _tenant()
    _as_tenant("")
    assert SubjectFolder.objects.count() == 0
    assert Submission.objects.count() == 0


def test_cross_tenant_write_is_rejected():
    org_a = _tenant()
    org_b = _tenant()
    folder_b_id = SubjectFolder.objects.filter(organization=org_b).values_list("pk", flat=True).get()
    _as_tenant(org_a.pk)
    assert SubjectFolder.objects.filter(pk=folder_b_id).update(title="sındırıldı") == 0
    with pytest.raises(DatabaseError, match="row-level security"):
        with transaction.atomic(), connection.cursor() as cursor:  # savepoint: xəta tranzaksiyanı pozmasın
            cursor.execute(
                "UPDATE subject_folder_subjectfolder SET organization_id = %s WHERE organization_id = %s",
                [str(org_b.pk), str(org_a.pk)],
            )
