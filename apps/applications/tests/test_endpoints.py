"""JSON səthi — müqavilə formaları, filtrlər və yükləmə qapısı."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from django.utils import timezone

import pytest

from apps.applications.constants import OPEN_STATUSES, ApplicationStatus, EventKind
from apps.applications.models import Application, ApplicationAttachment, ApplicationEvent
from apps.applications.services import submit, workflow
from apps.applications.tests.factories import kind_of, make_world, unit_of

pytestmark = pytest.mark.django_db

PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<</Root 1 0 R>>\n%%EOF\n"


def _zip_bytes(*members) -> bytes:
    """Yaddaşda kiçik ZIP arxivi qurur (``(ad, məzmun)`` cütləri)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members:
            archive.writestr(name, payload)
    return buffer.getvalue()


ZIP_BYTES = _zip_bytes(("arayis.pdf", PDF_BYTES))


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
    # Qaydalar UI müqaviləsidir: uzunluq hədləri + YÜKLƏMƏ hədləri (fayl seçicisi
    # `accept`/ölçü/say siyahısını buradan qurur, özündən yazmır).
    assert payload["rules"] == {
        "min_subject_length": 5,
        "min_body_length": 20,
        "min_note_length": 10,
        "max_files": 5,
        "max_file_mb": 10,
        "allowed_extensions": [".docx", ".jpeg", ".jpg", ".pdf", ".png", ".webp", ".zip"],
    }


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


def test_detail_mark_seen_is_idempotent_across_repeated_gets(world, application):
    # QA 2026-09-05 (P3-19): the "opened → seen" transition lives inside a GET
    # endpoint (design §3.4 wants it automatic). Repeated opens by the same
    # handler must not re-fire the transition or write a second SEEN event —
    # the view now checks status+`can_act` explicitly instead of relying on a
    # caught `TransitionDenied`, so this locks the idempotency in either way.
    client = client_for(world["coordinator"], world["organization"])
    first = body(client.get(reverse("applications:detail", kwargs={"application_id": application.pk})))
    assert first["application"]["status"]["key"] == ApplicationStatus.IN_REVIEW
    second = body(client.get(reverse("applications:detail", kwargs={"application_id": application.pk})))
    assert second["application"]["status"]["key"] == ApplicationStatus.IN_REVIEW
    seen_events = ApplicationEvent.objects.filter(application=application, kind=EventKind.SEEN).count()
    assert seen_events == 1


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


def test_zip_reply_attachment_is_accepted_and_bound_to_its_event(world, application):
    """Cavabla ZIP göndərmək: bir neçə sənəd bir arxivdə gedir.

    Sənəd HADİSƏYƏ bağlanmalıdır — modal yazışmasında cavab mətninin ALTINDA
    görünür; bağlanmasa yalnız ümumi «Əlavə olunan sənədlər» siyahısına düşərdi.
    """
    workflow.mark_seen(application=application, user=world["coordinator"])
    archive = SimpleUploadedFile("senedler.zip", ZIP_BYTES, content_type="application/zip")
    client = client_for(world["coordinator"], world["organization"])
    payload = body(
        client.post(
            reverse("applications:action", kwargs={"application_id": application.pk}),
            {"action": "resolve", "text": "Sənədləri arxivdə göndəririk.", "files": archive},
        )
    )
    assert payload["ok"] is True
    resolved = [event for event in payload["application"]["events"] if event["kind"] == EventKind.RESOLVED]
    assert len(resolved) == 1
    assert [item["name"] for item in resolved[0]["attachments"]] == ["senedler.zip"]


def test_a_zip_bomb_reply_is_refused(world, application):
    """Arxivin İÇİ də yoxlanır — uzantı/MIME qapısı zip-bombanı tutmur."""
    workflow.mark_seen(application=application, user=world["coordinator"])
    bomb = SimpleUploadedFile("bomba.zip", _zip_bytes(("bosluq.txt", b"0" * 200_000)), content_type="application/zip")
    client = client_for(world["coordinator"], world["organization"])
    response = client.post(
        reverse("applications:action", kwargs={"application_id": application.pk}),
        {"action": "resolve", "text": "Sənədləri arxivdə göndəririk.", "files": bomb},
    )
    assert response.status_code == 400
    assert not ApplicationAttachment.objects.exists()


def test_events_mark_which_side_wrote_them(world, application):
    """Yazışmada «kim danışır» AD-la deyil, göndərənin id-si ilə ayrılır (adaşlar)."""
    workflow.mark_seen(application=application, user=world["coordinator"])
    workflow.request_info(application=application, user=world["coordinator"], text="Arayışın surətini göndərin.")
    client = client_for(world["student"], world["organization"])
    payload = body(client.get(reverse("applications:detail", kwargs={"application_id": application.pk})))
    sides = {event["kind"]: event["actor_is_sender"] for event in payload["application"]["events"]}
    assert sides[EventKind.SUBMITTED] is True
    assert sides[EventKind.INFO_REQUESTED] is False


def test_sender_can_reopen_a_resolved_application(world, application):
    """«Razı deyiləm» — cavab problemi həll etmirsə müraciət ÖZ nömrəsi ilə qayıdır."""
    workflow.mark_seen(application=application, user=world["coordinator"])
    workflow.resolve(application=application, user=world["coordinator"], text="Məsələ həll olundu, baxın.")
    application.refresh_from_db()
    assert application.status == ApplicationStatus.RESOLVED
    number_before = application.number

    client = client_for(world["student"], world["organization"])
    detail = body(client.get(reverse("applications:detail", kwargs={"application_id": application.pk})))
    assert set(detail["application"]["allowed_actions"]) >= {"close", "reopen"}

    payload = body(
        client.post(
            reverse("applications:action", kwargs={"application_id": application.pk}),
            {"action": "reopen", "text": "Arayışdakı qrup nömrəsi hələ də səhvdir."},
        )
    )
    assert payload["ok"] is True
    assert payload["application"]["status"]["key"] == ApplicationStatus.IN_REVIEW
    assert payload["application"]["number"] == number_before
    reopened = [event for event in payload["application"]["events"] if event["kind"] == EventKind.REOPENED]
    assert len(reopened) == 1 and reopened[0]["actor_is_sender"] is True

    application.refresh_from_db()
    # Həll tarixi TƏMİZLƏNİR (KPI birinci, qəbul olunmamış cavabı ölçməsin) və
    # şöbəyə normativ pəncərə yenidən verilir.
    assert application.resolved_at is None
    assert application.sla_due_on >= timezone.localdate()
    assert application in Application.objects.filter(status__in=OPEN_STATUSES)


def test_reopen_needs_a_reason_and_is_closed_to_the_handler(world, application):
    workflow.mark_seen(application=application, user=world["coordinator"])
    workflow.resolve(application=application, user=world["coordinator"], text="Məsələ həll olundu, baxın.")

    sender = client_for(world["student"], world["organization"])
    short = sender.post(
        reverse("applications:action", kwargs={"application_id": application.pk}),
        {"action": "reopen", "text": "yox"},
    )
    assert short.status_code == 400 and body(short)["errors"]["code"] == ["transition.text_too_short"]

    handler = client_for(world["coordinator"], world["organization"])
    denied = handler.post(
        reverse("applications:action", kwargs={"application_id": application.pk}),
        {"action": "reopen", "text": "Öz cavabımı geri qaytarmaq istəyirəm."},
    )
    assert denied.status_code == 403
    application.refresh_from_db()
    assert application.status == ApplicationStatus.RESOLVED


def test_list_filters_by_the_submission_date_range(world, application):
    """Süzgəc GÖNDƏRİLMƏ tarixinə baxır; uclar daxildir, səhv sıra yer dəyişir."""
    today = timezone.localdate()
    client = client_for(world["student"], world["organization"])

    def numbers(**params):
        return [row["number"] for row in body(client.get(reverse("applications:list"), params))["results"]]

    assert numbers(tab="mine", stat="all") == [application.number]
    # Hər iki uc DAXİLDİR — göndərilmə günü seçiləndə sətir görünür.
    assert numbers(tab="mine", stat="all", **{"from": today.isoformat(), "to": today.isoformat()}) == [
        application.number
    ]
    # Aralıqdan kənar.
    assert numbers(tab="mine", stat="all", **{"from": (today + timedelta(days=1)).isoformat()}) == []
    assert numbers(tab="mine", stat="all", **{"to": (today - timedelta(days=1)).isoformat()}) == []
    # Uclar tərs verilib — boş nəticə əvəzinə nəzərdə tutulan aralıq.
    reversed_range = {"from": (today + timedelta(days=2)).isoformat(), "to": (today - timedelta(days=2)).isoformat()}
    assert numbers(tab="mine", stat="all", **reversed_range) == [application.number]
    # Zibil dəyər sorğunu QIRMIR — süzgəc sadəcə tətbiq olunmur (fail-soft).
    assert numbers(tab="mine", stat="all", **{"from": "2026-13-45", "to": "salam"}) == [application.number]


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


def test_internal_notes_stay_visible_to_the_handler_after_the_case_is_closed(world, application):
    """QA 2026-09-05 APPLICATIONS-08: emalçı öz daxili qeydini müraciət bağlanandan sonra da görməlidir."""
    workflow.mark_seen(application=application, user=world["coordinator"])
    workflow.add_comment(application=application, user=world["coordinator"], text="Daxili qeyd", is_internal=True)
    client = client_for(world["coordinator"], world["organization"])
    url = reverse("applications:action", kwargs={"application_id": application.pk})
    assert client.post(url, {"action": "resolve", "text": "Həll olundu, sənəd verildi."}).status_code == 200
    payload = body(client.get(reverse("applications:detail", kwargs={"application_id": application.pk})))
    assert any(event["is_internal"] for event in payload["application"]["events"])


def test_assign_with_an_invalid_assignee_is_a_json_error_not_a_500(world, application):
    """QA 2026-09-05 APPLICATIONS-06: `assignee=abc` `filter(pk=...)` ValueError ilə 500 verirdi."""
    client = client_for(world["coordinator"], world["organization"])
    url = reverse("applications:action", kwargs={"application_id": application.pk})
    client.post(url, {"action": "mark_seen"})
    for bad in ("abc", "", "1 OR 1=1"):
        response = client.post(url, {"action": "assign", "assignee": bad, "text": "Təyinat sınağı üçün qeyd."})
        assert response.status_code < 500, bad
        assert response["Content-Type"].startswith("application/json"), bad
