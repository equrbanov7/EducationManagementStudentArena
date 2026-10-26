"""Müraciətə rəsmi sənədin HAZIRLANIB ƏLAVƏ EDİLMƏSİ — «Arayış sorğusu» (sahib 2026-10-19) və
«Transkript sorğusu» (sahib 2026-10-26).

Əvvəl emalçı sənədi əl ilə hazırlayıb fayl kimi yükləyirdi. İndi bu növlərdən biri (``document_kinds.KINDS``)
açıq olanda, CARİ şöbənin emalçısı (``access.can_act``) və eyni zamanda tələbəyə sənəd verə bilən aktor
(``registrar.public.can_issue_documents`` — ``transcript.issue`` əhatəsi) bir düymə ilə möhürlü PDF-i (QR +
yoxlama kodu) qurur; fayl müraciətə **açıq qeyd** kimi əlavə olunur (``workflow.add_comment``) — sahib
bildiriş alır və sənədi müraciətdən endirir.

Qaydalar registrar-dadır: əhatədən kənar tələbə üçün düymə yoxdur (sorğu → 404), sənəd verilə bilməyən
tələbə (arayış: aktiv deyil; transkript: nəticə yoxdur) → 409 mətni, view-as rejimində sənəd verilmir (403).
Status DƏYİŞMİR — emalçı sonra adi «Həll et» edir.
"""

from __future__ import annotations

from django.core.files.base import ContentFile
from django.db import transaction
from django.urls import reverse
from django.utils.translation import pgettext

from apps.registrar.public import (
    CertificateRefused,
    can_issue_documents,
    documents_blocked_by_view_as,
    issuable_record_for_student,
)

from ..models import Application, ApplicationAttachment
from ..state_machine import Action, TransitionDenied, available_actions
from . import access, workflow
from .document_kinds import ARAYIS_KIND_CODE, KINDS, PLACE_MAX, TRANSCRIPT_KIND_CODE, kind_for

_CTX = "applications.arayis"


class DocumentUnavailable(Exception):
    """Sənəd bu müraciətə verilə bilmir — ``status`` HTTP kodu, ``message`` istifadəçi mətni."""

    def __init__(self, status: int, message: str):
        super().__init__(status, message)
        self.status = status
        self.message = message


def _record_for(application, *, user, request):
    """Emalçının sənəd verə bildiyi, müraciət sahibinə aid akademik qeyd — şərtlərdən biri tutmursa ``None``."""
    if kind_for(application) is None or not application.is_open:
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


def _attachments(application, kind):
    """Bu müraciətə sistemin əlavə etdiyi sənədlər (açıq qeydə bağlı, emalçının yüklədiyi, adı kodlu)."""
    pattern = kind.name_pattern
    rows = (
        ApplicationAttachment.objects.filter(application=application, original_name__startswith=f"{kind.prefix}_")
        .exclude(event__is_internal=True)
        .exclude(uploaded_by_id=application.created_by_id)
        .select_related("event")
        .order_by("-created_at")
    )
    return [row for row in rows if pattern.match(row.original_name or "")]


def _code_of(kind, row) -> str:
    return kind.name_pattern.match(row.original_name)["code"]


def _attached_rows(application, kind) -> list[dict]:
    """Əlavə olunmuş BÜTÜN sənədlər (ən yenisi əvvəl): kod + ikinci sətir (arayış: təqdim yeri) + açma linki."""
    attachments = _attachments(application, kind)
    if not attachments:
        return []
    codes = [_code_of(kind, row) for row in attachments]
    notes = kind.notes(application, codes, attachments)
    rows = []
    for code, note, row in zip(codes, notes, attachments):
        item = {
            "code": code,
            "note": note,
            "name": row.original_name,
            "download_url": reverse(
                "applications:attachment_download",
                kwargs={"application_id": row.application_id, "attachment_id": row.pk},
            ),
        }
        if kind.has_place:
            item["place"] = note
        rows.append(item)
    return rows


def document_tool(application, *, user, request) -> dict | None:
    """Detal panelinin «Sənədi hazırla» bloku (``None`` → blok göstərilmir). Mətnlər SERVERDƏN gəlir.

    ``attached`` — əlavə olunmuş sənədlərin siyahısı. Doludursa UI «… əlavə olunub» siyahısını və «Yeni …
    hazırla» düyməsini göstərir; forma həmin düymə ilə açılır. Fərqli məzmun → yeni möhür + yeni fayl; eyni
    məzmun → mövcud fayl qaytarılır (``issue_document``)."""
    if documents_blocked_by_view_as(request):
        return None
    record = _record_for(application, user=user, request=request)
    if record is None:
        return None
    kind = kind_for(application)
    refusal = kind.refusal(record)
    texts = kind.texts()
    texts.pop("unavailable", None)
    return {
        "kind": kind.code,
        "url": reverse(kind.url_name, args=[application.pk]),
        "has_place": kind.has_place,
        "place_max": PLACE_MAX if kind.has_place else 0,
        "blocked": refusal.message if refusal is not None else "",
        "attached": _attached_rows(application, kind),
        "code_label": pgettext(_CTX, "Kod"),
        **texts,
    }


def issue_document(*, application, user, place: str = "", request=None, kind_code: str | None = None):
    """Sənədi qurur və müraciətə açıq qeyd kimi əlavə edir → ``(event, seal, created)``.

    ``kind_code`` verilərsə müraciətin növü ona uyğun olmalıdır (başqa növün URL-i → 404).

    TƏKRAR ƏLAVƏ YOXDUR: müraciət sətri ``select_for_update`` ilə kilidlənir (iki tab / təkrar klik növbəyə
    düzülür); eyni gün eyni məzmun möhür servisində EYNİ möhürü verir, həmin kodlu fayl müraciətdə artıq
    varsa yeni qeyd yazılmır — mövcud qeyd qaytarılır (``created=False``)."""
    if documents_blocked_by_view_as(request):
        raise DocumentUnavailable(
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
            kind = kind_for(locked)
            record = _record_for(locked, user=user, request=request)
            if record is None or (kind_code is not None and kind.code != kind_code):
                spec = KINDS.get(kind_code or "") or kind or KINDS[ARAYIS_KIND_CODE]
                raise DocumentUnavailable(404, spec.texts()["unavailable"])
            issued_by = getattr(request, "real_user", None) or user
            payload, seal = kind.issue(locked.organization, record, issued_by, place, request)
            existing = next((row for row in _attachments(locked, kind) if _code_of(kind, row) == seal.code), None)
            if existing is not None:
                return existing.event, seal, False
            event = workflow.add_comment(
                application=locked,
                user=user,
                text=kind.comment(seal.code),
                is_internal=False,
                files=[ContentFile(payload, name=kind.filename(record, seal.code))],
                request=request,
            )
            if kind.after_issue is not None:
                kind.after_issue(locked, record, user, seal)
    except CertificateRefused as refusal:
        raise DocumentUnavailable(409, refusal.message) from refusal
    except TransitionDenied as exc:
        raise DocumentUnavailable(400, str(exc)) from exc
    return event, seal, True


__all__ = ["ARAYIS_KIND_CODE", "TRANSCRIPT_KIND_CODE", "DocumentUnavailable", "document_tool", "issue_document"]
