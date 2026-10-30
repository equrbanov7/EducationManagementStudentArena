"""Official-hour correction keeps teacher content and refuses stale baselines."""

import copy
from unittest.mock import patch

from django.contrib.auth import get_user_model

import pytest

from apps.syllabus import services
from apps.syllabus.services import mr112_hours as repair
from apps.syllabus.tests.factories import (
    activate_member,
    complete_section_data,
    make_academic_stack,
    make_offering,
    make_org,
)

pytestmark = pytest.mark.django_db


@patch("core.academic_rules.selfwork_enabled", return_value=False)
@patch("core.runtime_settings_syllabus.approval_required", return_value=False)
def test_exact_normalization_preserves_content_and_is_idempotent(_approval, _selfwork):
    org = make_org("mr112")
    user = get_user_model().objects.create_superuser("mr112-admin", password="test")
    teacher = get_user_model().objects.create_user(repair.AUTHOR)
    activate_member(org, teacher, "teacher", permissions=["grade.input", "syllabus.edit", "syllabus.submit"])
    stack = make_academic_stack(org, code="QKU-1150")
    offering = make_offering(org, stack, teacher)
    actor = services.resolve_actor(teacher, org)
    syllabus, version = services.create_draft(
        organization=org,
        subject=stack["subject"],
        period=stack["period"],
        offering=offering,
        actor=actor,
        plan_hours={"lecture": 30, "seminar": 15},
    )
    data = complete_section_data({"lecture": 30, "seminar": 15})
    for row in data["week"]["rows"]:
        if row.get("topic"):
            row["seminar"] = 2
    for key, value in data.items():
        if key not in ("prev", "send", "self"):
            services.save_section(version=version, section_id=key, data=value, actor=actor)
    before = services.section_data_map(version)
    with patch.object(repair, "VERSION", str(version.pk)), patch.object(repair, "SYLLABUS", str(syllabus.pk)):
        plan = repair.run(organization=org, user=user)
        assert services.section_data_map(version) == before
        with pytest.raises(repair.RepairError, match="baseline_changed"):
            repair.run(organization=org, user=user, apply=True, expected_baseline="stale")
        result = repair.run(organization=org, user=user, apply=True, expected_baseline=plan["baseline"])
        assert result["applied"] == 1
        assert repair.run(organization=org, user=user, apply=True) == {"already_present": 1}
    expected = copy.deepcopy(before)
    for row in expected["week"]["rows"]:
        if row.get("topic"):
            row["seminar"] = 1
    assert services.section_data_map(version) == expected


def test_unexpected_hour_shape_is_not_silently_rewritten():
    with pytest.raises(repair.RepairError):
        repair.corrected_week({"rows": [{"topic": "Preserve this", "lecture": 2, "seminar": 3}] * 15})
