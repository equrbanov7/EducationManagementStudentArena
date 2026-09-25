"""Sorğu cədvəllərinin DB səviyyəli tenant izolyasiyası (RLS).

Nümunə: ``apps/syllabus/tests/test_rls.py``. Data bypass rejimində yaradılır, sonra
``SET LOCAL ROLE rls_app_role`` ilə məhdud rola keçilir — yalnız onda siyasətlər
tətbiq olunur (test bağlantısının rolu superuser/BYPASSRLS-dir).
"""

from __future__ import annotations

from django.db import DatabaseError, connection, transaction

import pytest

from apps.surveys.constants import Section
from apps.surveys.forms import validate_answers
from apps.surveys.models import (
    SurveyAnswer,
    SurveyCampaign,
    SurveyQuestion,
    SurveyReceipt,
    SurveyResponse,
    SurveyTemplate,
)
from apps.surveys.services.submit import submit_target
from apps.surveys.services.targets import student_targets
from apps.surveys.services.templates import template_questions

from .factories import build_world, close_all, open_campaign

pytestmark = pytest.mark.postgres

_MODELS = (SurveyTemplate, SurveyQuestion, SurveyCampaign, SurveyReceipt, SurveyResponse, SurveyAnswer)


def _set(name, value):
    with connection.cursor() as cur:
        cur.execute("SELECT set_config(%s, %s, false)", [name, str(value)])


def _enter_tenant(org_id):
    _set("app.bypass_rls", "off")
    _set("app.current_org_id", str(org_id))
    _set("app.current_user_id", "")
    with connection.cursor() as cur:
        cur.execute("SET LOCAL ROLE rls_app_role")


@pytest.fixture(autouse=True)
def _bypass_for_setup(db):
    if connection.vendor != "postgresql":
        yield
        return
    _set("app.bypass_rls", "on")
    _set("app.current_org_id", "")
    try:
        yield
    finally:
        _set("app.bypass_rls", "off")
        _set("app.current_org_id", "")


def _seed(slug):
    world = build_world(slug, students=1)
    close_all(world)
    campaign = open_campaign(world)
    student = world["students"][0]
    for target in student_targets(campaign, student):
        section = Section.GENERAL if target.is_general else Section.TEACHER
        questions = template_questions(campaign.template, section=section)
        data = {f"q_{q.code}": ("8" if q.kind == "scale10" else "4") for q in questions if q.kind != "text"}
        cleaned, errors, _values = validate_answers(questions, data)
        assert not errors
        submit_target(campaign=campaign, student=student, target=target, cleaned_answers=cleaned)
    return world


@pytest.fixture()
def two_tenants():
    if connection.vendor != "postgresql":
        pytest.skip("RLS testləri PostgreSQL tələb edir")
    return _seed("svrlsa"), _seed("svrlsb")


def test_every_survey_table_is_tenant_isolated(two_tenants):
    world_a, world_b = two_tenants
    expected = {model: model.objects.filter(organization=world_a["org"]).count() for model in _MODELS}
    assert all(count > 0 for count in expected.values()), expected
    _enter_tenant(world_a["org"].pk)
    for model in _MODELS:
        rows = set(model.objects.values_list("organization_id", flat=True))
        assert rows == {world_a["org"].pk}, model.__name__
        assert model.objects.count() == expected[model], model.__name__


def test_missing_tenant_context_denies_all(two_tenants):
    _enter_tenant("")
    for model in _MODELS:
        assert model.objects.count() == 0, model.__name__


def test_cross_tenant_write_is_rejected(two_tenants):
    world_a, world_b = two_tenants
    campaign_b = SurveyCampaign.objects.get(organization=world_b["org"])
    _enter_tenant(world_a["org"].pk)
    with pytest.raises(DatabaseError), transaction.atomic():
        SurveyResponse.objects.create(organization=world_b["org"], campaign_id=campaign_b.pk, scope=Section.GENERAL)
