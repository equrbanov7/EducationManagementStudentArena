"""«Fəndən azad et» — tələbə qrupda qalır, yalnız BİR fənnin jurnalından çıxır (sahib 2026-10-15).

Sahib: «tələbə qrupda qalır, amma hansısa fəndən azaddır — onu ancaq jurnalda o fəndən çıxarda bilim».

YENİ MEXANİZM İCAD OLUNMUR — «Jurnal təmizliyi» qərar qatı təkrar işlədilir
(:mod:`apps.registrar.journal_hygiene_actions`):

* **Yazı** — :func:`journal_hygiene_actions.record_decisions`: BU açılışın qeydiyyatı ``enrolled → dropped``,
  ``JournalHygieneDecision`` (kateqoriya ``subject_exempt``, append-only) + ``core.audit``
  (``registrar.journal_hygiene``). Qrup üzvlüyü, ``StudentAcademicRecord`` və digər fənlərin qeydiyyatları
  TOXUNULMUR; bal / davamiyyət tarixçəsi silinmir.
* **«Bərpa et»** — :func:`journal_hygiene_actions.revert_locked`: status əvvəlkinə (``enrolled``), qərarda
  ``reverted_*`` bir dəfə doldurulur; tələbə həmin fənn üzrə başqa jurnalda aktivdirsə bərpa rədd edilir.
* ``dropped`` niyə (``suspended`` yox): jurnal, davamiyyət limiti, imtahan buraxılışı / siyahısı yalnız
  ``enrolled`` süzür, sorğu hədəfləri və kabinet «Fənlərim» isə ``dropped``-u çıxarır (``suspended`` orada
  qalırdı); akademik status sinxronu (``enrollment_suspension``) ``dropped``-a toxunmur — bərpa əmri
  azadlığı səssizcə geri açmır.

SƏLAHİYYƏT («hər rol öz səlahiyyəti qədər» — açarla, rol adı ilə yox):

* «Jurnal təmizliyi» qərar açarı — superadmin və ya təşkilat miqyaslı ``journal.correct`` (RİM rəhbəri,
  rektor ``*``) — bütün jurnallar;
* ``journal.roster`` (jurnal siyahısının idarəsi — dekan, dekan müavini, proqram koordinatoru, tyutor) —
  YALNIZ öz struktur alt-ağacındakı qrupun jurnalı (:func:`guest_roster.can_manage_offering_roster`).

Müəllimdə bu açarların heç biri yoxdur — genişləndirilmir. Siyahı qapısı alt qrup əməli ilə EYNİDİR
(:func:`guest_roster.roster_block_reason`): bağlı jurnalda və keçmiş dövrdə tərkib dəyişmir (transkript).
"""

from __future__ import annotations

import datetime as dt

from django.db import transaction
from django.utils.translation import pgettext

from . import guest_roster
from . import journal_hygiene_actions as actions
from . import journal_hygiene_rows as rows_service
from .models import Enrollment, HygieneCategory, JournalHygieneDecision

_CTX = "registrar.subject_exempt"
EXEMPT = HygieneCategory.SUBJECT_EXEMPT.value
REASON_CODE = "subject_exempt"
DOC_NUMBER_MAX = 64
REASON_MAX = actions.MAX_REASON_LENGTH
HygieneError = actions.HygieneError


# ── Səlahiyyət ───────────────────────────────────────────────────────────────


def has_any_power(user, organization) -> bool:
    """Aktorun ümumiyyətlə «Fəndən azad et» açarı varmı (yoxdursa HTTP 403)."""
    return actions.can_apply(user, organization) or guest_roster.can_manage_roster(user, organization)


def can_exempt(user, offering) -> bool:
    """Aktor MƏHZ bu açılışda azad edə / bərpa edə bilirmi (əhatədən kənar → HTTP 404)."""
    if actions.can_apply(user, offering.organization):
        return True
    return guest_roster.can_manage_offering_roster(user, offering)


def block_reason(offering) -> str:
    """Siyahı dəyişikliyi qadağandırsa səbəb (alt qrup əməli ilə eyni qapı), açıqdırsa boş sətir."""
    return guest_roster.roster_block_reason(offering)


# ── Giriş datası ─────────────────────────────────────────────────────────────


def clean_text(raw, limit=REASON_MAX) -> str:
    return " ".join(str(raw or "").split())[:limit]


def clean_document(number, date) -> dict:
    """Opsional sənəd: nömrə (≤64) + ISO tarix. Yanlış tarix → istifadəçi xətası."""
    number = clean_text(number, DOC_NUMBER_MAX)
    raw_date = str(date or "").strip()
    parsed = None
    if raw_date:
        try:
            parsed = dt.date.fromisoformat(raw_date)
        except ValueError:
            raise HygieneError("invalid_date", pgettext(_CTX, "Sənəd tarixi düzgün deyil."))
    return {"number": number, "date": parsed.isoformat() if parsed else ""}


def decision_reason(reason: str, document: dict) -> str:
    """Qərar sətrinin mətni: istifadəçinin səbəbi (istəyə bağlı) + sənəd; boşdursa standart qeyd."""
    parts = [reason] if reason else [pgettext(_CTX, "Fəndən azad edildi")]
    if document.get("number") or document.get("date"):
        stamp = dt.date.fromisoformat(document["date"]).strftime("%d.%m.%Y") if document.get("date") else ""
        doc = " ".join(part for part in (document.get("number"), stamp) if part)
        parts.append(pgettext(_CTX, "sənəd: %(doc)s") % {"doc": doc})
    return " · ".join(parts)[:REASON_MAX]


# ── Əməllər ──────────────────────────────────────────────────────────────────


def exempt_student(*, offering, enrollment_id, actor, reason="", doc_number="", doc_date="", request=None) -> dict:
    """Tələbəni BU açılışın jurnalından «Fəndən azad» edir (qərar jurnalı + audit, bir tranzaksiya)."""
    document = clean_document(doc_number, doc_date)
    text = decision_reason(clean_text(reason), document)
    with transaction.atomic():
        enrollment = (
            Enrollment.objects.select_for_update(of=("self",))
            .filter(organization=offering.organization, offering=offering, pk=enrollment_id)
            .first()
        )
        if enrollment is None:
            raise HygieneError("not_found", pgettext(_CTX, "Qeydiyyat tapılmadı."), status=404)
        if enrollment.status != Enrollment.Status.ENROLLED:
            raise HygieneError("not_enrolled", pgettext(_CTX, "Bu tələbə artıq jurnalda deyil."), status=409)
        key = str(enrollment.pk)
        row = {
            "id": key,
            "status": enrollment.status,
            "reason": REASON_CODE,
            "tags": [],
            "strong": False,
            "absence_hours": int(enrollment.absence_hours or 0),
        }
        row["evidence"] = actions.row_evidence(row, EXEMPT, rows_service.evidence_counts([key]).get(key))
        row["evidence"].update({"offering": str(offering.pk), "document": document})
        result = actions.record_decisions(
            organization=offering.organization,
            category=EXEMPT,
            rows=[row],
            to_status=Enrollment.Status.DROPPED,
            reason=text,
            actor=actor,
            request=request,
        )
    return {"decision_id": result["decision_ids"][0], "changed": result["changed"]}


def restore_student(*, offering, decision_id, actor, reason="", request=None) -> dict:
    """«Bərpa et»: bu açılışdakı qüvvədə olan azadlıq qərarını geri qaytarır."""
    text = clean_text(reason) or pgettext(_CTX, "Fəndən azadlıq geri alındı")
    with transaction.atomic():
        decision = (
            JournalHygieneDecision.objects.select_for_update(of=("self",))
            .filter(
                organization=offering.organization,
                pk=decision_id,
                category=EXEMPT,
                enrollment__offering=offering,
                reverted_at__isnull=True,
            )
            .first()
        )
        if decision is None:
            raise HygieneError(
                "not_revertable", pgettext(_CTX, "Qərar tapılmadı və ya artıq geri qaytarılıb."), status=404
            )
        enrollment = (
            Enrollment.objects.select_for_update(of=("self",)).select_related("offering").get(pk=decision.enrollment_id)
        )
        if enrollment.status != decision.to_status:
            raise HygieneError(
                "status_changed", pgettext(_CTX, "Qeydiyyatın statusu o vaxtdan dəyişib — bərpa olunmur."), status=409
            )
        if actions.active_elsewhere(offering.organization, [enrollment]):
            raise HygieneError(
                "active_elsewhere",
                pgettext(_CTX, "Tələbə bu fənn üzrə başqa jurnalda aktivdir — əvvəlcə oradan çıxarın."),
                status=409,
            )
        result = actions.revert_locked(
            organization=offering.organization,
            decisions=[decision],
            enrollments={enrollment.pk: enrollment},
            reason=text,
            actor=actor,
            request=request,
        )
    return {"reverted": result["reverted"]}


# ── Oxu ──────────────────────────────────────────────────────────────────────


def exempt_rows(offering) -> list:
    """Bu açılışda qüvvədə olan azadlıqlar (yeni → köhnə) — «Azad edilənlər» siyahısı üçün."""
    decisions = (
        JournalHygieneDecision.objects.filter(
            organization=offering.organization,
            category=EXEMPT,
            enrollment__offering=offering,
            reverted_at__isnull=True,
            enrollment__status=Enrollment.Status.DROPPED,
        )
        .select_related("enrollment__student")
        .order_by("-created_at")
    )
    return [
        {
            "decision_id": str(item.pk),
            "student": item.enrollment.student,
            "reason": item.reason,
            "decided_by": item.decided_by_name,
            "decided_at": item.created_at,
        }
        for item in decisions
    ]


def student_exempt_subjects(record, period) -> list:
    """Tələbə kabineti: bu dövrdə azad edildiyi fənlər (``dropped`` sətirlər «Fənlərim»dən düşür)."""
    if record is None or period is None:
        return []
    rows = (
        JournalHygieneDecision.objects.filter(
            organization_id=record.organization_id,
            category=EXEMPT,
            reverted_at__isnull=True,
            enrollment__student_id=record.student_id,
            enrollment__status=Enrollment.Status.DROPPED,
            enrollment__offering__period=period,
        )
        .order_by("enrollment__offering__subject__name")
        .values("enrollment__offering__subject__code", "enrollment__offering__subject__name")
    )
    return [
        {"code": row["enrollment__offering__subject__code"], "name": row["enrollment__offering__subject__name"]}
        for row in rows
    ]


def is_exempt_from_subject(record, period, subject_id) -> bool:
    """Tələbə bu dövrdə *subject_id* fənnindən azad edilibmi (alt qrupa yerləşdirmə qapısı)."""
    if record is None or period is None or subject_id is None:
        return False
    return JournalHygieneDecision.objects.filter(
        organization_id=record.organization_id,
        category=EXEMPT,
        reverted_at__isnull=True,
        enrollment__student_id=record.student_id,
        enrollment__status=Enrollment.Status.DROPPED,
        enrollment__offering__period=period,
        enrollment__offering__subject_id=subject_id,
    ).exists()


def page_context(user, offering) -> dict:
    """Jurnal səhifəsi: düymə (icazə + açıq siyahı) və «Azad edilənlər» siyahısı.

    Siyahını jurnalı açan HƏR KƏS görür (müəllim də — tələbənin niyə cədvəldə olmadığı aydın olsun);
    «Fəndən azad et» / «Bərpa et» düymələri isə yalnız səlahiyyətliyə və açıq siyahıda.
    """
    return {
        "can_exempt": can_exempt(user, offering) and not block_reason(offering),
        "exempt_rows": exempt_rows(offering),
    }


__all__ = [
    "EXEMPT",
    "HygieneError",
    "REASON_CODE",
    "block_reason",
    "can_exempt",
    "clean_document",
    "exempt_rows",
    "exempt_student",
    "has_any_power",
    "page_context",
    "restore_student",
    "student_exempt_subjects",
]
