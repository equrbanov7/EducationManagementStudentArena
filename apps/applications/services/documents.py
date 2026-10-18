"""«Arayış sorğusu» müraciətinə arayışın HAZIRLANIB ƏLAVƏ EDİLMƏSİ (sahib 2026-10-19).

Əvvəl emalçı arayışı əl ilə hazırlayıb fayl kimi yükləyirdi. İndi «Arayış sorğusu» (``kind.code ==
"arayis"``) açıq olanda, CARİ şöbənin emalçısı (``access.can_act``) və eyni zamanda tələbəyə sənəd verə
bilən aktor (``registrar.public.can_issue_documents`` — ``transcript.issue`` əhatəsi) bir düymə ilə
«Təhsil aldığı yer haqqında arayış» PDF-ini (QR + yoxlama kodu) qurur; fayl müraciətə **açıq qeyd** kimi
əlavə olunur (``workflow.add_comment``) — sahib bildiriş alır və sənədi müraciətdən endirir.

Qaydalar registrar-dadır: əhatədən kənar tələbə üçün düymə yoxdur (sorğu → 404), aktiv olmayan tələbə →
409 mətni, view-as rejimində sənəd verilmir (403). Status DƏYİŞMİR — emalçı sonra adi «Həll et» edir.
"""

from __future__ import annotations

import re

from django.core.files.base import ContentFile
from django.db import transaction
from django.urls import reverse
from django.utils.translation import pgettext

from apps.registrar.public import (
    ENROLLMENT_CERTIFICATE_PLACE_MAX,
    CertificateRefused,
    can_issue_documents,
    certificate_filename,
    documents_blocked_by_view_as,
    enrollment_certificate_places,
    enrollment_certificate_refusal,
    issuable_record_for_student,
    issue_enrollment_certificate,
)

from ..models import Application, ApplicationAttachment
from ..state_machine import Action, TransitionDenied, available_actions
from . import access, workflow

ARAYIS_KIND_CODE = "arayis"
_CTX = "applications.arayis"


class ArayisUnavailable(Exception):
    """Arayış bu müraciətə verilə bilmir — ``status`` HTTP kodu, ``message`` istifadəçi mətni."""

    def __init__(self, status: int, message: str):
        super().__init__(status, message)
        self.status = status
        self.message = message


def _record_for(application, *, user, request):
    """Emalçının sənəd verə bildiyi, müraciət sahibinə aid akademik qeyd — şərtlərdən biri tutmursa ``None``."""
    if getattr(application.kind, "code", "") != ARAYIS_KIND_CODE or not application.is_open:
        return None
    if not access.can_act(user, application):
        return None
    allowed = available_actions(status=application.status, is_handler=True, is_sender=False)
    if Action.ADD_COMMENT not in allowed:
        return None
    organization = application.organization
    if not can_issue_documents(user, organization, request=request):
        return None
    return issuable_record_for_student(user, organization, application.created_by, request=request)


#: Müraciətə əlavə olunmuş arayışın fayl adı: «Arayış_<ad>_<YYYY-MM-DD>_<yoxlama kodu>.pdf»
#: (``registrar.public.certificate_filename(record, code)``) — kod möhürə bir mənalı bağlayır.
_ATTACHED_NAME = re.compile(r"^Arayış_.+_\d{4}-\d{2}-\d{2}_(?P<code>[A-Z0-9]{2,6}(?:-[0-9A-Z]{4}){4})\.pdf$")


def _arayis_attachments(application):
    """Bu müraciətə sistemin əlavə etdiyi arayışlar (açıq qeydə bağlı, emalçının yüklədiyi, adı kodlu)."""
    rows = (
        ApplicationAttachment.objects.filter(application=application, original_name__startswith="Arayış_")
        .exclude(event__is_internal=True)
        .exclude(uploaded_by_id=application.created_by_id)
        .select_related("event")
        .order_by("-created_at")
    )
    return [row for row in rows if _ATTACHED_NAME.match(row.original_name or "")]


def _attached_rows(application) -> list[dict]:
    """Əlavə olunmuş BÜTÜN arayışlar (ən yenisi əvvəl): kod + təqdim yeri (möhürdən) + açma linki."""
    attachments = _arayis_attachments(application)
    if not attachments:
        return []
    codes = [_ATTACHED_NAME.match(row.original_name)["code"] for row in attachments]
    places = enrollment_certificate_places(application.organization, codes)
    default_place = pgettext(_CTX, "tələb olunan yerə")
    return [
        {
            "code": code,
            "place": places.get(code) or default_place,
            "name": row.original_name,
            "download_url": reverse(
                "applications:attachment_download",
                kwargs={"application_id": row.application_id, "attachment_id": row.pk},
            ),
        }
        for code, row in zip(codes, attachments)
    ]


def arayis_tool(application, *, user, request) -> dict | None:
    """Detal panelinin «Arayış hazırla» bloku (``None`` → blok göstərilmir). Mətnlər SERVERDƏN gəlir.

    ``attached`` — əlavə olunmuş arayışların siyahısı. Doludursa UI «Arayış əlavə olunub» siyahısını və
    «Yeni arayış hazırla (başqa yer üçün)» düyməsini göstərir; forma həmin düymə ilə açılır. Başqa yer → yeni
    möhür + yeni fayl; eyni yer → mövcud fayl qaytarılır (``issue_arayis``)."""
    if documents_blocked_by_view_as(request):
        return None
    record = _record_for(application, user=user, request=request)
    if record is None:
        return None
    refusal = enrollment_certificate_refusal(record)
    return {
        "url": reverse("applications:issue_arayis", args=[application.pk]),
        "place_max": ENROLLMENT_CERTIFICATE_PLACE_MAX,
        "blocked": refusal.message if refusal is not None else "",
        "attached": _attached_rows(application),
        "title": pgettext(_CTX, "Təhsil aldığı yer haqqında arayış"),
        "hint": pgettext(
            _CTX,
            "Arayış QR və yoxlama kodu ilə möhürlənir və müraciətə açıq qeyd kimi əlavə olunur — sahib onu "
            "müraciətdən endirir. «Təqdim ediləcəyi yer» istəyə bağlıdır (yönlük halda: «… bankına»).",
        ),
        "place_label": pgettext(_CTX, "Təqdim ediləcəyi yer"),
        "place_placeholder": pgettext(_CTX, "məs.: Səbail rayon hərbi komissarlığına"),
        "button": pgettext(_CTX, "Arayışı hazırla və əlavə et"),
        "attached_label": pgettext(_CTX, "Arayış əlavə olunub"),
        "code_label": pgettext(_CTX, "Kod"),
        "open_label": pgettext(_CTX, "Arayışı aç"),
        "again_label": pgettext(_CTX, "Yeni arayış hazırla (başqa yer üçün)"),
        "same_place_hint": pgettext(
            _CTX, "Eyni yer üçün yenidən hazırlasanız, artıq əlavə olunmuş arayış qaytarılır — ikinci fayl yaranmır."
        ),
    }


def issue_arayis(*, application, user, place: str = "", request=None):
    """Arayışı qurur və müraciətə açıq qeyd kimi əlavə edir → ``(event, seal, created)``.

    TƏKRAR ƏLAVƏ YOXDUR: müraciət sətri ``select_for_update`` ilə kilidlənir (iki tab / təkrar klik növbəyə
    düzülür); eyni gün eyni məzmun (təqdim yeri daxil) möhür servisində EYNİ möhürü verir, həmin kodlu fayl
    müraciətdə artıq varsa yeni qeyd yazılmır — mövcud qeyd qaytarılır (``created=False``)."""
    if documents_blocked_by_view_as(request):
        raise ArayisUnavailable(
            403,
            pgettext(_CTX, "«Başqasının adından» rejimində rəsmi sənəd verilmir — öz hesabınıza qayıdın."),
        )
    try:
        # Möhür + qeyd BİR tranzaksiyada: qeyd yazılmasa möhür sətri də geri qaytarılır (yetim sənəd qalmır).
        with transaction.atomic():
            locked = (
                Application.objects.select_for_update(of=("self",))
                .select_related("kind", "current_unit", "current_scope_unit", "created_by", "organization")
                .get(pk=application.pk)
            )
            record = _record_for(locked, user=user, request=request)
            if record is None:
                raise ArayisUnavailable(404, pgettext(_CTX, "Bu müraciətə arayış hazırlamaq mümkün deyil."))
            payload, seal = issue_enrollment_certificate(
                organization=locked.organization,
                record=record,
                issued_by=getattr(request, "real_user", None) or user,
                place=place,
                request=request,
            )
            existing = next(
                (
                    row
                    for row in _arayis_attachments(locked)
                    if _ATTACHED_NAME.match(row.original_name)["code"] == seal.code
                ),
                None,
            )
            if existing is not None:
                return existing.event, seal, False
            text = pgettext(
                _CTX, "Təhsil aldığı yer haqqında arayış hazırlandı və əlavə olundu. Yoxlama kodu: %(code)s."
            ) % {"code": seal.code}
            event = workflow.add_comment(
                application=locked,
                user=user,
                text=text,
                is_internal=False,
                files=[ContentFile(payload, name=certificate_filename(record, seal.code))],
                request=request,
            )
    except CertificateRefused as refusal:
        raise ArayisUnavailable(409, refusal.message) from refusal
    except TransitionDenied as exc:
        raise ArayisUnavailable(400, str(exc)) from exc
    return event, seal, True


__all__ = ["ARAYIS_KIND_CODE", "ArayisUnavailable", "arayis_tool", "issue_arayis"]
