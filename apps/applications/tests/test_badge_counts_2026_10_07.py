"""Müraciət sayğacları — TƏK aqreqat sorğu, köhnə ``COUNT(DISTINCT <bütün sütunlar>)`` ilə EYNİ rəqəm.

Tutum 2026-10-07: kabinet badge-i (``pending_badge_count``) göndərən üçün 3 ayrı
``SELECT COUNT(*) FROM (SELECT DISTINCT <~20 sütun> …)`` + həll müddəti sətirlərinin
oxusunu, emalçı üçün 4 sayı (izləmə JOIN-i daxil) hesablayıb yalnız birini işlədirdi.
Burada köhnə formul (``base_queryset(...).filter(...).distinct().count()``) etalondur.
"""

from __future__ import annotations

from datetime import timedelta

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

import pytest

from apps.applications.constants import CLOSED_STATUSES, OPEN_STATUSES, ApplicationStatus
from apps.applications.models import Application, ApplicationWatch
from apps.applications.public import pending_badge_count
from apps.applications.services import access, queries, submit
from apps.applications.tests.factories import kind_of, make_world, unit_of

pytestmark = pytest.mark.django_db


def _old_count(queryset) -> int:
    return queryset.distinct().count()


@pytest.fixture()
def world():
    world = make_world("bdg")
    org, student = world["organization"], world["student"]
    created = [
        submit.submit_application(
            organization=org,
            user=student,
            kind=kind_of(world, "diger"),
            subject=f"Sayğac müraciəti {index}",
            body="Sayğacların eyni qaldığını yoxlamaq üçün kifayət qədər uzun müraciət mətni.",
        )
        for index in range(6)
    ]
    statuses = [
        ApplicationStatus.SUBMITTED,
        ApplicationStatus.WAITING_INFO,
        ApplicationStatus.WAITING_INFO,
        ApplicationStatus.RESOLVED,
        ApplicationStatus.CLOSED,
        ApplicationStatus.REJECTED,
    ]
    now = timezone.now()
    for application, status in zip(created, statuses):
        Application.objects.filter(pk=application.pk).update(
            status=status,
            resolved_at=now if status in CLOSED_STATUSES else None,
            sla_due_on=timezone.localdate() - timedelta(days=3),
        )
    # İzləmə (çox-qiymətli JOIN): iki müraciət RİM-dədir, əvvəlki şöbələr izləyir —
    # ikincisini BÜTÜN digər şöbələr izləyir (bir neçə şöbənin emalçısı üçün JOIN sətri təkrarlanır).
    rim = unit_of(world, "rim")
    for application, watchers in (
        (created[0], [created[0].current_unit]),
        (created[1], [unit for unit in world["units"].values() if unit.pk != rim.pk]),
    ):
        Application.objects.filter(pk=application.pk).update(current_unit=rim)
        for unit in watchers:
            ApplicationWatch.objects.create(
                organization=org, application=application, unit=unit, scope_unit=application.current_scope_unit
            )
    world["applications"] = created
    return world


def test_sender_counts_match_old_distinct_formula(world):
    org, student = world["organization"], world["student"]
    mine = queries.base_queryset(org).filter(created_by=student)
    expected = {
        "open": _old_count(mine.filter(status__in=OPEN_STATUSES)),
        "waiting_info": _old_count(mine.filter(status=ApplicationStatus.WAITING_INFO)),
        "resolved": _old_count(mine.filter(status__in=[ApplicationStatus.RESOLVED, ApplicationStatus.CLOSED])),
    }
    assert expected == {"open": 3, "waiting_info": 2, "resolved": 2}
    with CaptureQueriesContext(connection) as ctx:
        assert queries.sender_counts(organization=org, user=student) == expected
    assert len(ctx.captured_queries) == 1
    kpis = queries.sender_kpis(organization=org, user=student)
    assert {key: kpis[key] for key in expected} == expected


def test_handler_counts_match_old_distinct_formula(world):
    org = world["organization"]
    for handler in (world["coordinator"], world["staff"], world["rim"], world["outsider"]):
        inbox = queries.base_queryset(org).filter(access.inbox_q(handler, org))
        watching = queries.base_queryset(org).filter(access.watching_q(handler, org))
        expected = {
            "inbox_open": _old_count(inbox.filter(status__in=OPEN_STATUSES)),
            "new_unseen": _old_count(inbox.filter(status=ApplicationStatus.SUBMITTED)),
            "overdue": _old_count(inbox.filter(status__in=OPEN_STATUSES, sla_due_on__lt=timezone.localdate())),
            "watching": _old_count(watching.filter(status__in=OPEN_STATUSES)),
        }
        assert queries.handler_kpis(organization=org, user=handler) == expected, handler.username
        old_tabs = {
            tab: _old_count(
                queries.base_queryset(org).filter(queries._tab_q(handler, org, tab)).filter(status__in=OPEN_STATUSES)
            )
            for tab in ("mine", "inbox", "watching")
        }
        old_tabs["archive"] = _old_count(queries.base_queryset(org).filter(queries._tab_q(handler, org, "archive")))
        assert queries.tab_counts(organization=org, user=handler) == old_tabs, handler.username
    coordinator_kpis = queries.handler_kpis(organization=org, user=world["coordinator"])
    assert coordinator_kpis["watching"] == 2  # hər iki RİM müraciətini izləyir


def test_pending_badge_is_one_aggregate_without_distinct(world):
    org = world["organization"]
    for user, expected in ((world["student"], 2), (world["coordinator"], None)):
        if expected is None:
            inbox = queries.base_queryset(org).filter(access.inbox_q(user, org))
            expected = _old_count(inbox.filter(status__in=OPEN_STATUSES))
        access.active_units(org)  # şöbə kataloqu keşi (ayrı ölçülür)
        access.active_memberships(user, org)
        with CaptureQueriesContext(connection) as ctx:
            assert pending_badge_count(user, org) == expected
        sqls = [query["sql"] for query in ctx.captured_queries]
        assert len(sqls) == 1, sqls
        assert "DISTINCT" not in sqls[0]
