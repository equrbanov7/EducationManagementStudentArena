"""Ödənişdən SONRA müraciətin bağlanması — yalnız heyət, RƏSMİ QƏRARLA (sahib 2026-10-19).

Sahib: «Yox (qaytarılma yoxdur), ancaq qərar olmalıdır — dəqiqləşdirəcəm.» Ödəniş təsdiqləndikdən sonra
müraciəti bağlayan HƏR əməl (``reject`` rədd, ``no_show`` «İmtahana gəlmədi», ``withdraw`` tələbənin xahişi ilə
geri götürmə) dekanlıq / tədris şöbəsi (``retake.manage``) tərəfindən və qərarla olur: əmr № + tarix VƏ YA
qərar sənədi (qəbzlə eyni yoxlama — PDF/JPG/PNG, 10 MB). Hadisəyə «Qaytarılma yoxdur» qeydi yazılır.

``no_show`` 25% cəhdini İSTİFADƏ OLUNMUŞ sayır (``CONSUMED_STATUSES``); ``reject`` / ``withdraw`` saymır. Sonradan
«Ödənişin qaytarılması qərarı» verilib və «Cəhd istifadə olunmuş sayılmasın» (``refund_restores_attempt``, defolt
açıq) seçilibsə cəhd YENİDƏN sayılmır (``models.retake.consumes_attempt``).

İMTAHAN CƏHDİ AÇILIBSA (``exam_granted``, review 2026-10-19 HIGH-1): bağlanışla birlikdə verilmiş əlavə cəhd və
fərdi PIN exams modulunun ``second_chance_provider``-i ilə GERİ ALINIR. Tələbənin həmin imtahanda davam edən və ya
yoxlanmamış cəhdi varsa bağlanış RƏDD olunur (əvvəlcə cəhd bitməli / yoxlanmalıdır). Geri almaq mümkün deyilsə
(provayder yoxdur) ``exam_granted``-dən bağlanış ümumiyyətlə qəbul olunmur.

QAYTARILMA QAYDASI (sahib 2026-10-19, tövsiyə olunan variant): DEFOLT QAYTARILMA YOXDUR — bağlanış hadisəsi
«Qaytarılma yoxdur» qeydi və ``metadata["refund"] = "none"`` ilə yazılır (bağlanış anının vəziyyəti). Qaytarılma
YALNIZ ayrıca rəsmi qərarla verilir: «Ödənişin qaytarılması qərarı» (:mod:`apps.registrar.retake_refund`) —
təşkilat əhatəli ``retake.manage`` (Tədris şöbəsi / RİM; dekan UNIT əhatəlidir, verə bilməz), əmr № + tarix və ya
qərar sənədi (bu modulun ``clean_decision`` yoxlaması) və ≥ 20 simvol səbəb. Mühasibatlıq (``retake.payment_verify``)
icranı «Qaytarıldı» (tarix + arayış №) ilə qeyd edir. Sistem pul köçürmür — yalnız qeyd; hər addım append-only
``RetakeApplicationEvent`` (``refund_decided`` / ``refunded``) və audit jurnalındadır.
"""

from __future__ import annotations

import datetime

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import pgettext

from core import superadmin_waiver

from . import retake_files, retake_rules
from .models import ExamChanceGrant, ExamChanceReason, RetakeActorRole, RetakeEventAction, RetakeKind, RetakeStatus
from .retake_services import clean_upload, lock, transition

_CTX = "registrar.retake"

#: Ödəniş təsdiqləndikdən sonrakı statuslar — bağlanış qərar tələb edir.
AFTER_PAYMENT = frozenset({RetakeStatus.PAYMENT_VERIFIED, RetakeStatus.ADMITTED, RetakeStatus.EXAM_GRANTED})

ACTIONS = {
    "reject": (RetakeStatus.REJECTED, RetakeEventAction.REJECTED, AFTER_PAYMENT),
    "no_show": (
        RetakeStatus.NO_SHOW,
        RetakeEventAction.NO_SHOW,
        frozenset({RetakeStatus.ADMITTED, RetakeStatus.EXAM_GRANTED}),
    ),
    "withdraw": (RetakeStatus.WITHDRAWN, RetakeEventAction.WITHDRAWN, AFTER_PAYMENT),
}

NO_REFUND_NOTE = "Qaytarılma yoxdur."


def _exam_provider():
    """exams modulunun «yenidən cəhd» provayderi (app registry) və ya ``None`` — statik import yoxdur."""
    from django.apps import apps as django_apps

    try:
        config = django_apps.get_app_config("exams")
    except LookupError:
        return None
    factory = getattr(config, "second_chance_provider", None)
    return factory() if callable(factory) else None


def _revoke_exam_access(application, *, actor, action, request=None) -> list:
    """``exam_granted`` müraciətinin açdığı əlavə cəhdləri və PIN-ləri geri al (imtahan üzrə xülasə siyahısı)."""
    per_exam: dict = {}
    for grant in ExamChanceGrant.objects.filter(application=application, reason=ExamChanceReason.RETAKE_25):
        per_exam[grant.exam_id] = per_exam.get(grant.exam_id, 0) + int(grant.extra_attempts or 0)
    if not per_exam:
        return []
    provider = _exam_provider()
    if provider is None:
        if action == "no_show":
            return []  # exams modulu yoxdur → cəhd də ola bilməz; «gəlmədi» qeyd oluna bilər
        raise ValidationError(
            pgettext(_CTX, "İmtahan cəhdi geri alına bilmir — imtahan cəhdi açılmış müraciət hələ bağlanmır.")
        )
    results = []
    for exam_id, extra in sorted(per_exam.items()):
        try:
            summary = provider.revoke_second_chance(
                exam_id=exam_id,
                student=application.student,
                extra=extra,
                revoked_by=actor,
                request=request,
                reason=f"retake_{action}:{application.pk}",
            )
        except provider.RevokeBlocked as exc:
            raise ValidationError(str(exc)) from None
        results.append({"exam_id": exam_id, **summary})
    return results


def _clean_date(raw):
    if isinstance(raw, datetime.date):
        return raw
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return datetime.date.fromisoformat(text)
    except ValueError:
        raise ValidationError(pgettext(_CTX, "Əmr tarixi düzgün deyil.")) from None


def clean_decision(*, order_number="", order_date=None, document=None, missing_message=None, actor=None) -> dict:
    """Əmr № + tarix VƏ YA sənəd. ``actor`` superadmindirsə (2026-10-27) boşluq avtomatik «SA-…» əmri ilə dolur."""
    number = str(order_number or "").strip()[:80]
    date = _clean_date(order_date)
    if document is not None:
        clean_upload(document)
    elif superadmin_waiver.waives(actor) and not (number and date):
        number = number or superadmin_waiver.order_number()
        date = date or superadmin_waiver.order_date()
    if not ((number and date) or document is not None):
        raise ValidationError(
            missing_message
            or pgettext(
                _CTX,
                "Ödənişdən sonra bağlanış rəsmi qərarla olur: əmr nömrəsi və tarixi və ya qərar sənədi əlavə edin.",
            )
        )
    return {"number": number, "date": date, "document": document}


@transaction.atomic
def close(
    *,
    actor,
    organization,
    application_id,
    action,
    reason,
    order_number="",
    order_date=None,
    document=None,
    request=None,
):
    """Ödənişdən sonra bağlanış (qərarla). ``action``: ``reject`` | ``no_show`` | ``withdraw``."""
    if action not in ACTIONS:
        raise ValidationError(pgettext(_CTX, "Naməlum əməl."))
    target, event_action, allowed = ACTIONS[action]
    with retake_files.discard_on_error():
        application = lock(application_id, organization)
        if application.kind != RetakeKind.RETAKE_25 or application.status not in allowed:
            raise ValidationError(pgettext(_CTX, "Bu mərhələdə bu bağlanış mümkün deyil."))
        if document is None and not (str(order_number or "").strip() and order_date):
            reason = superadmin_waiver.stamp(reason, actor)  # superadmin: sənədsiz / əmrsiz (2026-10-27)
        elif superadmin_waiver.waives(actor):
            reason = superadmin_waiver.fill_text(reason, actor, min_length=retake_rules.REASON_MIN)
        text = retake_rules.clean_reason(reason)
        decision = clean_decision(order_number=order_number, order_date=order_date, document=document, actor=actor)
        revoked = (
            _revoke_exam_access(application, actor=actor, action=action, request=request)
            if application.status == RetakeStatus.EXAM_GRANTED
            else []
        )
        if decision["document"] is not None:
            application.closure_document.save(
                getattr(decision["document"], "name", "") or "decision", decision["document"], save=False
            )
            retake_files.track(application.closure_document)
        application.closure_order_number = decision["number"]
        application.closure_order_date = decision["date"]
        application.decided_by = actor
        application.decided_at = timezone.now()
        application.decision_note = text
        note = f"{text} {pgettext(_CTX, 'Qaytarılma yoxdur.')}"
        transition(
            application,
            target,
            action=event_action,
            actor=actor,
            role=RetakeActorRole.DEANERY,
            note=note,
            metadata={
                "order_number": decision["number"],
                "order_date": decision["date"].isoformat() if decision["date"] else None,
                "document": application.closure_document.name or None,
                # Bağlanış anında qaytarılma YOXDUR; qaytarılma yalnız ayrıca qərarla (``retake_refund``, docstring).
                "refund": "none",
                "paid_amount": str(application.paid_amount) if application.paid_amount is not None else None,
                "consumes_attempt": target == RetakeStatus.NO_SHOW,
                "revoked_exam_access": revoked,
            },
            fields=(
                "closure_order_number",
                "closure_order_date",
                "closure_document",
                "decided_by",
                "decided_at",
                "decision_note",
            ),
            request=request,
        )
    return application


__all__ = ["ACTIONS", "AFTER_PAYMENT", "NO_REFUND_NOTE", "clean_decision", "close"]
