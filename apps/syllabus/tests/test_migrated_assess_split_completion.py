"""MR-000143 (Minayə Əzimova, 2026-11-02): «40 bal tam paylanmayıb» — köçürülmüş sillabusda yalançı xəbərdarlıq.

Redaktorun sağ paneli «Qiymətləndirmə cəmi: 100 bal» (yaşıl) göstərir, sənəd də standart düsturu
(10 + 30 + 10 + 50 = 100) çap edir, amma «Çatışmayan tələblər» siyahısı «Sərbəst bölünən 40 bal tam
paylanmayıb (hazırda 0)» deyirdi. Səbəb: köçürmə (``rehearsal_syllabus_targets``) ``assess`` bölməsinə
``{"midterm": 0, "project": 0}`` yazır, tamamlanma isə bu SAXLANAN cütü yoxlayırdı. Bal bölgüsü sahib
2026-09-20 qərarı ilə SİSTEMİNDİR (müəllim seçmir, ``save_section`` gələn dəyəri hər halda standartla
əvəzləyir) və redaktorda onu «düzəltməyə» heç bir input yoxdur — xəbərdarlıq aradan qalxa bilmirdi.

Tamamlanma indi bölgünü versiyanın CARİ qaydasından götürür (yaddaşdakı data toxunulmur).
"""

from __future__ import annotations

import copy

from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.utils import timezone

import pytest

from apps.syllabus import public, services
from apps.syllabus.constants import SectionKey
from apps.syllabus.models import SyllabusSection
from apps.syllabus.tests.factories import (
    PLAN_HOURS,
    activate_member,
    complete_section_data,
    make_academic_stack,
    make_org,
)

User = get_user_model()

pytestmark = pytest.mark.django_db

TEACHER_PERMS = ["syllabus.view", "syllabus.edit", "syllabus.submit", "grade.input"]

#: Köçürmənin ``assess`` forması (``rehearsal_syllabus_targets.build_section_data``): bölgü 0/0.
MIGRATED_ASSESS = {"midterm": 0, "project": 0, "note": "Mənbə qiymətləndirmə mətni", "exam_questions": []}


def _migrated_version():
    org = make_org("mr143-org")
    teacher = User.objects.create_user("mr143_teacher", "mr143_teacher@x.test", "pw")
    stack = make_academic_stack(org)
    activate_member(org, teacher, "teacher", permissions=TEACHER_PERMS)
    data = complete_section_data()
    data[SectionKey.ASSESS.value] = copy.deepcopy(MIGRATED_ASSESS)
    _syllabus, version = services.import_migrated_version(
        organization=org,
        subject=stack["subject"],
        approved_at=timezone.now(),
        author=teacher,
        chair_unit=stack["chair"],
        plan_hours=dict(PLAN_HOURS),
        section_data=data,
    )
    return org, teacher, version


def _stored_assess(version) -> dict:
    return SyllabusSection.objects.get(version=version, section_id=SectionKey.ASSESS.value).data


@pytest.mark.parametrize("selfwork", [False, True])
def test_migrated_zero_split_does_not_block_completion(settings, selfwork):
    settings.ACADEMIC_SELFWORK_ENABLED = selfwork
    _org, _teacher, version = _migrated_version()

    report = services.recompute_completion(version)

    codes = {issue.code for issue in report.issues}
    assert "assess.split_mismatch" not in codes, report.as_dict()["issues"]
    assert report.sections[SectionKey.ASSESS.value] is True
    assert report.percent == 100, report.as_dict()["issues"]
    # Yaddaşdakı data DƏYİŞMİR — yalnız tamamlanma hesabı cari qaydanı oxuyur.
    assert _stored_assess(version) == MIGRATED_ASSESS


def test_editor_missing_requirements_agree_with_the_100_point_summary(settings):
    settings.ACADEMIC_SELFWORK_ENABLED = False  # prod defoltu: sərbəst işsiz qayda (midterm 30 + 10)
    org, teacher, version = _migrated_version()
    request = RequestFactory().get("/profile/")
    request.user = teacher

    context = public.build_syllabus_editor_context(request, organization=org, version=version)

    codes = {issue["code"] for issue in context["completion"]["issues"]}
    assert "assess.split_mismatch" not in codes
    assert context["completion"]["sections"][SectionKey.ASSESS.value] is True
    assert _stored_assess(version) == MIGRATED_ASSESS
