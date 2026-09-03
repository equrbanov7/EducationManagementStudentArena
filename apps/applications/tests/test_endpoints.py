"""JSON səthi — müqavilə formaları, filtrlər və yükləmə qapısı."""

from __future__ import annotations

import json

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

import pytest

from apps.applications.constants import ApplicationStatus
from apps.applications.models import ApplicationAttachment
from apps.applications.services import submit, workflow
from apps.applications.tests.factories import kind_of, make_world, unit_of

pytestmark = pytest.mark.django_db

PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<</Root 1 0 R>>\n%%EOF\n"


@pytest.fixture()
def world():
    return make_world("api")


def client_for(user, organization):
    client = Client()
    client.force_login(user)
    session = client.session
    session["active_organization"] = organization.slug
    session.save()
    return client


def body(response):
    return json.loads(response.content.decode())


@pytest.fixture()
def application(world):
    return submit.submit_application(
        organization=world["organization"],
        user=world["student"],
        kind=kind_of(world, "diger"),
        subject="Seçmə fənn bloku",
        body="İxtisas üzrə seçmə fənn blokunu dəyişmək istəyirəm, izah lazımdır.",
    )


def test_anonymous_access_is_refused(world):
    response = Client().get(reverse("applications:list"))
    assert response.status_code in {302, 403}


def test_catalog_lists_only_the_kinds_open_to_the_sender(world):
    client = client_for(world["student"], world["organization"])
    payload = body(client.get(reverse("applications:catalog")))
    assert payload["ok"] is True
    assert payload["family"] == "student"
    assert payload["can_create"] is True
    codes = {kind["code"] for kind in payload["kinds"]}
    assert "transkript" in codes and "teqdimat" not in codes
    assert payload["rules"] == {"min_subject_length": 5, "min_body_length": 20, "min_note_length": 10}


def test_catalog_resolves_the_destination_for_the_routing_hint(world):
    client = client_for(world["student"], world["organization"])
    payload = body(client.get(reverse("applications:catalog")))
    other = next(kind for kind in payload["kinds"] if kind["code"] == "diger")
    assert other["destination"]["code"] == "koordinator"
    assert "Proqram koordinatoru" in other["routing_hint"]


def test_grade_appeal_kind_points_at_the_appeals_module(world):
    client = client_for(world["student"], world["organization"])
    payload = body(client.get(reverse("applications:catalog")))
    appeal = next(kind for kind in payload["kinds"] if kind["code"] == "qiymet")
    assert appeal["external_link"]["url"].startswith("/appeals/")


def test_create_returns_the_detail_payload(world):
    client = client_for(world["student"], world["organization"])
    response = client.post(
        reverse("applications:create"),
        {
            "kind": "diger",
            "subject": "Seçmə fənn bloku",
            "body": "İxtisas üzrə seçmə fənn blokunu dəyişmək istəyirəm, izah lazımdır.",
        },
    )
    payload = body(response)
    assert response.status_code == 200 and payload["ok"] is True
    assert payload["application"]["number"] == "MR-000001"
    assert payload["application"]["current_unit"]["code"] == "koordinator"
    assert payload["application"]["status"]["key"] == ApplicationStatus.SUBMITTED


def test_create_rejects_short_text_with_field_errors(world):
    client = client_for(world["student"], world["organization"])
    response = client.post(reverse("applications:create"), {"kind": "diger", "subject": "qsa", "body": "qısa"})
    payload = body(response)
    assert response.status_code == 400 and payload["ok"] is False
    assert set(payload["errors"]) == {"subject", "body"}


def test_create_rejects_an_unknown_kind(world):
    client = client_for(world["student"], world["organization"])
    response = client.post(
        reverse("applications:create"),
        {"kind": "yoxdur", "subject": "Mövzu sətri", "body": "Kifayət qədər uzun mətn burada yazılıb."},
    )
    assert response.status_code == 400 and "kind" in body(response)["errors"]


def test_detail_marks_seen_for_the_handler(world, application):
    client = client_for(world["coordinator"], world["organization"])
    payload = body(client.get(reverse("applications:detail", kwargs={"application_id": application.pk})))
    assert payload["application"]["status"]["key"] == ApplicationStatus.IN_REVIEW
    assert payload["application"]["viewer"]["is_handler"] is True
    assert "resolve" in payload["application"]["allowed_actions"]


def test_detail_does_not_mark_seen_for_the_sender(world, application):
    client = client_for(world["student"], world["organization"])
    payload = body(client.get(reverse("applications:detail", kwargs={"application_id": application.pk})))
    assert payload["application"]["status"]["key"] == ApplicationStatus.SUBMITTED
    assert payload["application"]["viewer"]["is_sender"] is True
    assert "cancel" in payload["application"]["allowed_actions"]
    assert "resolve" not in payload["application"]["allowed_actions"]


def test_detail_is_404_for_a_stranger(world, application):
    client = client_for(world["other_coordinator"], world["organization"])
    response = client.get(reverse("applications:detail", kwargs={"application_id": application.pk}))
    assert response.status_code == 404


def test_internal_notes_are_hidden_from_the_sender(world, application):
    workflow.mark_seen(application=application, user=world["coordinator"])
    workflow.add_comment(application=application, user=world["coordinator"], text="Daxili qeyd", is_internal=True)
    sender = client_for(world["student"], world["organization"])
    payload = body(sender.get(reverse("applications:detail", kwargs={"application_id": application.pk})))
    assert all(not event["is_internal"] for event in payload["application"]["events"])

    handler = client_for(world["coordinator"], world["organization"])
    handler_payload = body(handler.get(reverse("applications:detail", kwargs={"application_id": application.pk})))
    assert any(event["is_internal"] for event in handler_payload["application"]["events"])


def test_action_endpoint_drives_the_state_machine(world, application):
    client = client_for(world["coordinator"], world["organization"])
    url = reverse("applications:action", kwargs={"application_id": application.pk})
    assert client.post(url, {"action": "mark_seen"}).status_code == 200
    payload = body(client.post(url, {"action": "resolve", "text": "Blok dəyişdirildi, tamamdır."}))
    assert payload["application"]["status"]["key"] == ApplicationStatus.RESOLVED


def test_action_endpoint_refuses_a_short_reason(world, application):
    client = client_for(world["coordinator"], world["organization"])
    url = reverse("applications:action", kwargs={"application_id": application.pk})
    client.post(url, {"action": "mark_seen"})
    response = client.post(url, {"action": "reject", "reason": "yox"})
    payload = body(response)
    assert response.status_code == 400
    assert payload["errors"]["code"] == ["transition.text_too_short"]


def test_action_endpoint_refuses_a_non_handler(world, application):
    client = client_for(world["dean"], world["organization"])
    response = client.post(
        reverse("applications:action", kwargs={"application_id": application.pk}),
        {"action": "resolve", "text": "Bu mənim işim deyil amma sınayıram."},
    )
    assert response.status_code == 404


def test_forward_action_takes_the_unit_code_from_the_catalog(world, application):
    client = client_for(world["coordinator"], world["organization"])
    url = reverse("applications:action", kwargs={"application_id": application.pk})
    client.post(url, {"action": "mark_seen"})
    payload = body(
        client.post(
            url,
            {
                "action": "forward",
                "target_unit": "rim",
                "text": "Sistem tərəfli nasazlıq görünür, RİM baxsın.",
                "keep_watching": "true",
            },
        )
    )
    assert payload["application"]["current_unit"]["code"] == "rim"


def test_list_filters_by_tab_stat_kind_and_search(world, application):
    student = client_for(world["student"], world["organization"])
    mine = body(student.get(reverse("applications:list"), {"tab": "mine", "stat": "open"}))
    assert mine["total"] == 1 and mine["results"][0]["number"] == application.number

    assert body(student.get(reverse("applications:list"), {"tab": "mine", "kind": "transkript"}))["total"] == 0
    assert body(student.get(reverse("applications:list"), {"tab": "mine", "q": "Seçmə"}))["total"] == 1
    assert body(student.get(reverse("applications:list"), {"tab": "mine", "q": "MR-000001"}))["total"] == 1
    assert body(student.get(reverse("applications:list"), {"tab": "mine", "q": "tapılmayan"}))["total"] == 0
    assert body(student.get(reverse("applications:list"), {"tab": "mine", "stat": "closed"}))["total"] == 0


def test_inbox_and_watching_tabs(world, application):
    coordinator = client_for(world["coordinator"], world["organization"])
    assert body(coordinator.get(reverse("applications:list"), {"tab": "inbox"}))["total"] == 1
    assert body(coordinator.get(reverse("applications:list"), {"tab": "watching"}))["total"] == 0

    workflow.mark_seen(application=application, user=world["coordinator"])
    workflow.forward(
        application=application,
        user=world["coordinator"],
        target_unit=unit_of(world, "rim"),
        note="Sistem tərəfli nasazlıq görünür, RİM baxsın.",
    )
    assert body(coordinator.get(reverse("applications:list"), {"tab": "inbox"}))["total"] == 0
    assert body(coordinator.get(reverse("applications:list"), {"tab": "watching"}))["total"] == 1

    other = client_for(world["other_coordinator"], world["organization"])
    assert body(other.get(reverse("applications:list"), {"tab": "inbox"}))["total"] == 0


def test_kpis_shape(world, application):
    student = client_for(world["student"], world["organization"])
    payload = body(student.get(reverse("applications:kpis")))
    assert payload["sender"] == {"open": 1, "waiting_info": 0, "resolved": 0, "avg_response_days": 0.0}
    assert payload["is_handler"] is False

    coordinator = client_for(world["coordinator"], world["organization"])
    handler_payload = body(coordinator.get(reverse("applications:kpis")))
    assert handler_payload["is_handler"] is True
    assert handler_payload["handler"]["inbox_open"] == 1
    assert handler_payload["handler"]["new_unseen"] == 1


def test_attachment_upload_and_gated_download(world):
    client = client_for(world["student"], world["organization"])
    upload = SimpleUploadedFile("arayis.pdf", PDF_BYTES, content_type="application/pdf")
    payload = body(
        client.post(
            reverse("applications:create"),
            {
                "kind": "diger",
                "subject": "Sənədli müraciət",
                "body": "Sənəd əlavə edilmiş müraciətin kifayət qədər uzun mətni.",
                "files": upload,
            },
        )
    )
    attachments = payload["application"]["attachments"]
    assert len(attachments) == 1 and attachments[0]["name"] == "arayis.pdf"

    download_url = attachments[0]["download_url"]
    owner_response = client.get(download_url)
    assert owner_response.status_code == 200
    assert owner_response["Content-Disposition"].startswith("attachment;")
    assert owner_response["X-Content-Type-Options"] == "nosniff"

    stranger = client_for(world["other_coordinator"], world["organization"])
    assert stranger.get(download_url).status_code == 404


def test_disallowed_extension_is_rejected(world):
    client = client_for(world["student"], world["organization"])
    upload = SimpleUploadedFile("virus.exe", b"MZ binary", content_type="application/octet-stream")
    response = client.post(
        reverse("applications:create"),
        {
            "kind": "diger",
            "subject": "Qadağan olunmuş fayl",
            "body": "Qadağan olunmuş uzantı ilə fayl göndərməyə cəhd edilir.",
            "files": upload,
        },
    )
    assert response.status_code == 400
    assert not ApplicationAttachment.objects.exists()
