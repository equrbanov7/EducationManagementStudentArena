"""Sahib 2026-11-10: qovluq müəllimin həmin fənn + semestrdə dərs dediyi BÜTÜN qruplara avtomatik təyin olunur.

* yaradılanda — iki qrup → hər iki qrupun tələbəsi materialı görür (əl ilə seçim yoxdur);
* başqa müəllimin / fənnin / semestrin qrupu, passiv (məs. Kollec) açılış — DAXİL DEYİL;
* mövcud qovluq — əmr (dry-run → apply → undo) və beat tapşırığı ilə; əl ilə ləğv edilmiş qrup geri gəlmir;
* siyahı kartında «Yaradan» görünür.
"""

from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.test import Client
from django.urls import reverse

import pytest

from apps.registrar.models import CourseOffering
from apps.subject_folder import public
from apps.subject_folder.models import FolderAssignment
from apps.subject_folder.services import auto_assign
from apps.subject_folder.tasks import auto_assign_groups

from . import factories as f

pytestmark = pytest.mark.django_db


@pytest.fixture
def two_groups(world):
    """Müəllimin eyni fənn + semestrdə İKİNCİ qrupu (dərs müəllimi kimi — bölünmüş fənn) + kənar qruplar."""
    colleague = f.make_teacher(world.org)
    second = f.make_offering(world.org, subject=world.subject, period=world.period, instructor=colleague)
    f.add_lesson(second, world.teacher)
    second_students = [f.make_student(world.org) for _ in range(2)]
    for student in second_students:
        f.enroll(second, student)
    foreign = f.make_offering(world.org, subject=world.subject, period=world.period, instructor=colleague)
    other_subject = f.make_offering(
        world.org, subject=f.make_subject(world.org), period=world.period, instructor=world.teacher
    )
    other_period = f.make_offering(
        world.org, subject=world.subject, period=f.make_period(world.org, current=False), instructor=world.teacher
    )
    outsiders = []
    for offering in (foreign, other_subject, other_period):
        student = f.make_student(world.org)
        f.enroll(offering, student)
        outsiders.append(student)
    world.second, world.second_students, world.outsiders = second, second_students, outsiders
    world.foreign, world.other_subject, world.other_period = foreign, other_subject, other_period
    return world


def _create(world, **kwargs):
    folder, created, _summary = public.create_folder(
        organization=world.org,
        subject=world.subject,
        owner=world.teacher,
        by_user=world.teacher,
        period=world.period,
        **kwargs,
    )
    assert created
    return folder


def _publish_material(folder, teacher):
    return public.create_material(
        folder, by_user=teacher, kind="link", title="Mühazirə slaydları", url="https://example.org/s", is_published=True
    )


def _visible(world, student, folder):
    rows = public.student_folders(organization=world.org, student=student)
    return folder.pk in {row["folder"].pk for row in rows} and public.can_view_folder(student, folder)


def test_create_assigns_every_taught_group_and_both_groups_see_materials(two_groups):
    world = two_groups
    folder = _create(world)
    folder.refresh_from_db()
    assert folder.status == "active" and folder.created_by_id == world.teacher.pk
    rows = FolderAssignment.objects.filter(folder=folder, is_active=True)
    assert {row.offering_id for row in rows} == {world.offering.pk, world.second.pk}
    assert all(row.auto_assigned and row.auto_batch for row in rows)
    material = _publish_material(folder, world.teacher)
    for student in world.students + world.second_students:
        assert _visible(world, student, folder)
        assert public.can_view_material(student, material)
    for student in world.outsiders:
        assert not _visible(world, student, folder)
        assert not public.can_view_material(student, material)


def test_inactive_offering_is_skipped(two_groups):
    """Passiv açılış (``hide_college_journals_20261110`` Kollec jurnallarını belə gizlədir) avtomatik təyin olunmur."""
    world = two_groups
    CourseOffering.objects.filter(pk=world.second.pk).update(is_active=False)
    folder = _create(world)
    assert set(folder.assignments.values_list("offering_id", flat=True)) == {world.offering.pk}


def test_existing_folder_backfill_command_dry_run_apply_undo(two_groups):
    world = two_groups
    folder = _create(world, auto_assign=False)  # köhnə qovluq — əvvəlki qayda ilə heç bir qrupa təyin olunmayıb
    material = _publish_material(folder, world.teacher)
    assert folder.status == "draft" and not folder.assignments.exists()
    assert not public.can_view_material(world.second_students[0], material)

    out = StringIO()
    call_command("subject_folder_auto_assign", "--org", world.org.slug, stdout=out)
    assert "mode=dry_run" in out.getvalue() and "assignments=2" in out.getvalue()
    assert not folder.assignments.exists()

    out = StringIO()
    call_command(
        "subject_folder_auto_assign", "--org", world.org.slug, "--apply", "--batch", "sfauto-test-1", stdout=out
    )
    assert "assignments=2" in out.getvalue() and "folders_activated=1" in out.getvalue()
    folder.refresh_from_db()
    assert folder.status == "active"
    for student in world.students + world.second_students:
        assert public.can_view_material(student, material)
    assert not any(public.can_view_material(student, material) for student in world.outsiders)

    out = StringIO()
    call_command("subject_folder_auto_assign", "--org", world.org.slug, "--apply", stdout=out)
    assert "noop" in out.getvalue()  # idempotent

    call_command("subject_folder_auto_assign", "--org", world.org.slug, "--apply", "--undo", "--batch", "sfauto-test-1")
    folder.refresh_from_db()
    assert folder.status == "draft" and not folder.assignments.filter(is_active=True).exists()
    auto_assign_groups()  # undo edilmiş (passiv) sətir avtomatik geri açılmır
    assert not folder.assignments.filter(is_active=True).exists()


def test_beat_picks_up_new_offering_but_respects_manual_unassign(world):
    folder = _create(world)
    (first,) = folder.assignments.all()
    public.unassign(first, by_user=world.teacher)
    later = f.make_offering(world.org, subject=world.subject, period=world.period, instructor=world.teacher)
    student = f.make_student(world.org)
    f.enroll(later, student)
    summary = auto_assign_groups()
    assert summary["counts"]["assignments"] == 1
    active = set(folder.assignments.filter(is_active=True).values_list("offering_id", flat=True))
    assert active == {later.pk}  # əl ilə ləğv edilmiş qrup geri gəlmədi
    assert _visible(world, student, folder)


def test_manual_assignment_still_works_as_addition(world):
    folder = _create(world, auto_assign=False)
    result = public.assign_folder(folder, [world.offering], by_user=world.teacher)
    assert result[0]["created"] and not result[0]["assignment"].auto_assigned
    assert auto_assign.plan([folder]) == []


def test_archived_and_periodless_folders_are_not_planned(world):
    folder = _create(world, auto_assign=False)
    public.set_folder_status(folder, by_user=world.teacher, status="archived")
    folder.refresh_from_db()
    assert auto_assign.plan([folder]) == []
    periodless, _created, _summary = public.create_folder(
        organization=world.org, subject=world.subject, owner=world.teacher, by_user=world.teacher, period=None
    )
    assert not periodless.assignments.exists()


def test_teacher_list_card_shows_creator(world, settings):
    settings.UNIVERSITY_MODE = True
    folder = _create(world)
    client = Client()
    client.force_login(world.teacher)
    session = client.session
    session["active_organization"] = world.org.slug
    session.save()
    response = client.get(f"{reverse('accounts:profile')}?section=subject-folders")
    assert response.status_code == 200
    html = response.content.decode()
    assert "Yaradan" in html and world.teacher.get_full_name() in html
    assert folder.title in html and "sfc-fcard--active" in html
