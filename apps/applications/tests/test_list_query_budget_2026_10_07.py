"""Müraciətlər siyahısı (``applications:list``) — sorğu SAYI sətir sayından asılı deyil (2026-10-07).

Ölçülmüş tapıntı: ``row_payload`` hər sətir üçün göndərənin bölməsini
(``sender_scope_unit`` — ``select_related``-də yox idi) və sənəd sayını
(``attachments.count()``) ayrıca sorğu ilə oxuyurdu: 2 → 12 öz müraciəti olan
göndərən üçün 17 → 37, koordinatorun «Gələnlər» tabında 19 → 39 sorğu. İndi JOIN +
səhifə üçün tək prefetch — 14 / 16 sabit; sətir məzmunu (bölmə adı, sənəd sayı) eyni.
"""

from __future__ import annotations

from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

import pytest

from apps.applications.models import Application, ApplicationAttachment
from apps.applications.services import submit
from apps.applications.tests.factories import kind_of, make_world

pytestmark = pytest.mark.django_db


def _submit(world, count):
    created = []
    for index in range(count):
        created.append(
            submit.submit_application(
                organization=world["organization"],
                user=world["student"],
                kind=kind_of(world, "diger"),
                subject=f"Siyahı büdcəsi {index}",
                body=f"Sorğu sayının sətir sayından asılı olmadığını yoxlayan kifayət qədər uzun mətn {index}.",
            )
        )
    # Sənəd sayı fərqli olsun (0, 1, 2 …) — say prefetch-dən gəlməlidir.
    for index, application in enumerate(created):
        for number in range(index % 3):
            ApplicationAttachment.objects.create(
                organization=world["organization"],
                application=application,
                file=f"applications/test/{application.pk}-{number}.pdf",
                original_name=f"sened-{number}.pdf",
                size=10,
                uploaded_by=world["student"],
            )
    return created


def _client(user, organization):
    client = Client()
    client.force_login(user)
    session = client.session
    session["active_organization"] = organization.slug
    session.save()
    return client


def _measure(world, actor, params):
    client = _client(world[actor], world["organization"])
    url = reverse("applications:list")
    client.get(url, params)  # isinmə (sessiya, proses keşləri)
    with CaptureQueriesContext(connection) as ctx:
        response = client.get(url, params)
    assert response.status_code == 200
    return response.json(), len(ctx.captured_queries)


@pytest.mark.parametrize(("actor", "tab"), [("student", "mine"), ("coordinator", "inbox")])
def test_list_query_count_does_not_grow_with_rows(actor, tab):
    small = make_world(f"alq-s-{tab}")
    large = make_world(f"alq-l-{tab}")
    _submit(small, 2)
    _submit(large, 12)
    small_payload, small_count = _measure(small, actor, {"tab": tab})
    large_payload, large_count = _measure(large, actor, {"tab": tab})
    assert len(small_payload["results"]) == 2
    assert len(large_payload["results"]) == 12
    assert small_count == large_count, f"2 sətir: {small_count}, 12 sətir: {large_count}"


def test_row_payload_matches_direct_values():
    world = make_world("alq-rows")
    created = _submit(world, 6)
    payload, _ = _measure(world, "student", {"tab": "mine"})
    rows = {row["id"]: row for row in payload["results"]}
    assert set(rows) == {str(application.pk) for application in created}
    for application in Application.objects.filter(pk__in=[a.pk for a in created]).select_related("sender_scope_unit"):
        row = rows[str(application.pk)]
        assert row["attachment_count"] == ApplicationAttachment.objects.filter(application=application).count()
        expected_scope = application.sender_scope_unit.name if application.sender_scope_unit_id else ""
        assert row["requester_scope"] == expected_scope
    assert sorted(row["attachment_count"] for row in rows.values()) == [0, 0, 1, 1, 2, 2]
    assert all(row["requester_scope"] for row in rows.values())  # bölmə adı həqiqətən yoxlanır
