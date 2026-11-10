"""Sahib 2026-11-10: təsdiqlənmiş sillabus yoxdursa yeni dərs modalına mövzu yenə gəlsin.

Ehtiyat sırası: öz təsdiqlənməmiş sillabusu → eyni fənnin təsdiqlənmiş sillabusu. Ehtiyat sətirlər jurnala
bağlanmır (``week`` boş), təsdiqlənmiş sillabus varsa davranış dəyişmir.
"""

from __future__ import annotations

import pytest

from apps.registrar.journal_topics import lesson_topic_choices, lesson_topic_meta
from apps.syllabus.tests.reuse_fixtures import actor, approved_syllabus, build_world, draft_for, fill

pytestmark = pytest.mark.django_db


@pytest.fixture()
def world(settings):
    settings.ACADEMIC_SELFWORK_ENABLED = True
    return build_world("jtf-1110")


def _fresh(offering):
    return offering.__class__.objects.get(pk=offering.pk)


def test_approved_syllabus_keeps_week_binding(world):
    approved_syllabus(world, "o1")
    meta = lesson_topic_meta(_fresh(world["offerings"]["o1"]), [])
    assert meta and all(row["week"] for row in meta)
    assert not any(row["fallback"] for row in meta)


def test_own_unapproved_draft_feeds_topics(world):
    _syllabus, version = draft_for(world, "o2")
    fill(version, actor(world))
    meta = lesson_topic_meta(_fresh(world["offerings"]["o2"]), [])
    assert meta and all(row["fallback"] and row["week"] is None for row in meta)
    assert lesson_topic_choices(_fresh(world["offerings"]["o2"])) == [row["title"] for row in meta]


def test_peer_approved_syllabus_of_same_subject_feeds_topics(world):
    _syllabus, version = approved_syllabus(world, "o1")
    meta = lesson_topic_meta(_fresh(world["offerings"]["o5"]), [])  # teacher2, öz sillabusu yoxdur
    assert meta and all(row["fallback"] and row["week"] is None for row in meta)
    own = lesson_topic_meta(_fresh(world["offerings"]["o1"]), [])
    assert [row["title"] for row in meta] == [row["title"] for row in own]


def test_no_source_at_all_keeps_free_text(world):
    assert lesson_topic_meta(_fresh(world["offerings"]["o3"]), []) == []
