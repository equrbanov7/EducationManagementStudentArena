"""Sorğu qurucusunun yeni cədvəlləri (2026-09-30) — DB səviyyəli tenant izolyasiyası (RLS).

Naxış ``test_rls.py`` ilə eynidir: data bypass rejimində yaradılır, sonra ``SET LOCAL ROLE
rls_app_role`` ilə məhdud rola keçilir — yalnız onda siyasətlər tətbiq olunur.
"""

from __future__ import annotations

from django.db import DatabaseError, connection, transaction
from django.utils import timezone

import pytest

from apps.surveys.models import (
    Survey,
    SurveyDraft,
    SurveyGateSkip,
    SurveyPage,
    SurveyParticipation,
    SurveyPendingSubmission,
    SurveySubmission,
    SurveySubmissionAnswer,
)
from apps.surveys.services.answers import validate_answers
from apps.surveys.services.survey_buffer import publish_results
from apps.surveys.services.survey_respond import submit

from .builder_world import answer_payload, make_survey, questions_of
from .factories import build_world

pytestmark = pytest.mark.postgres

_MODELS = (
    Survey,
    SurveyPage,
    SurveyParticipation,
    SurveySubmission,
    SurveySubmissionAnswer,
    SurveyPendingSubmission,
    SurveyDraft,
    SurveyGateSkip,
)


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


def _answer(survey, student):
    cleaned, errors, _values = validate_answers(questions_of(survey), _as_querydict(answer_payload(survey)))
    assert not errors, errors
    submit(survey, student, cleaned)


def _as_querydict(data):
    from django.http import QueryDict

    query = QueryDict(mutable=True)
    for key, value in data.items():
        if isinstance(value, list):
            query.setlist(key, value)
        else:
            query[key] = value
    return query


def _seed(slug):
    world = build_world(slug, students=4)
    anonymous = make_survey(world, k=3, mandatory=True, policy="skip_once")
    for student in world["students"][:3]:
        _answer(anonymous, student)
    publish_results(anonymous.pk)  # bufer → cavablar (partiya ≥ k)
    _answer(anonymous, world["students"][3])  # buferdə qalır
    named = make_survey(world, anonymous=False, title="Adlı")
    _answer(named, world["students"][0])
    SurveyDraft.objects.create(organization=world["org"], survey=named, user=world["students"][1], data={})
    SurveyGateSkip.objects.create(organization=world["org"], survey=anonymous, user=world["students"][3])
    assert timezone.localdate()
    return world


@pytest.fixture()
def two_tenants():
    if connection.vendor != "postgresql":
        pytest.skip("RLS testləri PostgreSQL tələb edir")
    return _seed("svbrlsa"), _seed("svbrlsb")


def test_every_builder_table_is_tenant_isolated(two_tenants):
    world_a, _world_b = two_tenants
    expected = {model: model.objects.filter(organization=world_a["org"]).count() for model in _MODELS}
    assert all(count > 0 for count in expected.values()), expected
    _enter_tenant(world_a["org"].pk)
    for model in _MODELS:
        assert set(model.objects.values_list("organization_id", flat=True)) == {world_a["org"].pk}, model.__name__
        assert model.objects.count() == expected[model], model.__name__


def test_missing_tenant_context_denies_all(two_tenants):
    _enter_tenant("")
    for model in _MODELS:
        assert model.objects.count() == 0, model.__name__


def test_cross_tenant_write_is_rejected(two_tenants):
    world_a, world_b = two_tenants
    survey_b = Survey.objects.filter(organization=world_b["org"]).first()
    _enter_tenant(world_a["org"].pk)
    with pytest.raises(DatabaseError), transaction.atomic():
        SurveySubmission.objects.create(organization=world_b["org"], survey_id=survey_b.pk)
