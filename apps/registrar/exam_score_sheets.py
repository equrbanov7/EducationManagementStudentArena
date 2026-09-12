"""Yazılı imtahan balı köçürməsi — QRUP-ƏVVƏL seçim və köçürmə vərəqi (partiya).

Sahibin tələbi (2026-09-12): «yazılı imtahan verən tələbələrin imtahan ballarını
sistemə köçürmək üçün panel olsun. Orada qrup seçilsin, müəllim, tarix və s.
lazımlı nə info varsa; tələbələrin balları sistemə yüklənsin.»

Bu modul ``exam_score_entry`` servisinin QARDAŞIDIR (modul-ölçü büdcəsi,
SOFT_CAP=600) və iki şey verir:

1. **Qrup-əvvəl oxu** — dövr → QRUP → həmin qrupun açılışları (fənn + müəllim
   ilə). Köhnə fənn-əvvəl axın (``subjects_for_period`` /
   ``offerings_for_subject``) olduğu kimi qalır; panel hər iki sıranı dəstəkləyir,
   qrup-əvvəl defoltdur.
2. **Köçürmə vərəqi (partiya)** — ``ExamScoreSheet``: imtahan tarixi, yoxlayan
   müəllim, nəzarətçi, protokol №, skan (opsional) və nəticə sayğacları. Bal
   YAZMIR — yazı yolu yalnız ``exam_score_entry.record_exam_score``-dur; burada
   partiya yaradılır/bağlanır və tarixçə üçün oxunur.

Heç bir ``from apps.exams``/``from apps.accounts`` importu yoxdur (module_deps).
"""

from __future__ import annotations

import datetime

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count
from django.utils.translation import pgettext

from core.audit import log_action
from core.constants import AuditAction

from .corrections import correction_author_name
from .models import CourseOffering, ExamScoreSheet, ExamScoreSheetSource

_CTX = "registrar.exam_score_entry"

#: Səthdə göstərilən son partiyaların sayı (tarixçə paneli).
SHEET_HISTORY_LIMIT = 20


# ── Qrup-əvvəl oxu ───────────────────────────────────────────────────────────


def groups_for_period(*, organization, period):
    """Bu dövrdə aktiv açılışı olan QRUPLAR (ad + açılış sayı ilə, təkrarsız).

    Qrupsuz açılışlar (``group IS NULL``) bu siyahıya düşmür — onlar fənn-əvvəl
    sırada «(qrupsuz açılış)» kimi görünür.
    """
    if organization is None or period is None:
        return []
    rows = (
        CourseOffering.objects.filter(organization=organization, period=period, is_active=True, group__isnull=False)
        .values("group_id", "group__name", "group__code")
        .annotate(offering_count=Count("id"))
        .order_by("group__name")
    )
    return [
        {
            "id": str(row["group_id"]),
            "name": row["group__name"],
            "code": row["group__code"] or "",
            "offering_count": row["offering_count"],
        }
        for row in rows
    ]


def offerings_for_group(*, organization, period, group_id):
    """Qrupun bu dövrdəki açılışları — FƏNN seçimi üçün (fənn + müəllim ilə)."""
    if organization is None or period is None or not group_id:
        return []
    return list(
        CourseOffering.objects.filter(organization=organization, period=period, group_id=group_id, is_active=True)
        .select_related("subject", "group", "instructor")
        .order_by("subject__code", "subject__name")
    )


def instructor_label(offering) -> str:
    """Açılışın müəllimi — ad, yoxdursa istifadəçi adı, o da yoxdursa «—»."""
    instructor = getattr(offering, "instructor", None)
    if instructor is None:
        return ""
    return instructor.get_full_name() or instructor.username


def subject_label(offering) -> str:
    """«CS101 — Proqramlaşdırma» etiketi (qrup-əvvəl siyahıda fənn seçimi)."""
    subject = offering.subject
    return f"{subject.code} — {subject.name}" if subject.code else subject.name


# ── Partiya (köçürmə vərəqi) ─────────────────────────────────────────────────


def parse_exam_date(raw):
    """Formadan gələn tarix — ``YYYY-MM-DD`` (``<input type=date>``) və ya ``DD.MM.YYYY``.

    Boş → ``None`` (tarix opsionaldır: sahib «lazımlı nə info varsa» dedi,
    məcburi etmədi). Yanlış format → ``ValidationError``.
    """
    text = (raw or "").strip() if isinstance(raw, str) else raw
    if not text:
        return None
    if isinstance(text, datetime.date):
        return text
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValidationError(pgettext(_CTX, "İmtahan tarixi düzgün formatda deyil."))


def sheet_metadata_from_post(post, files, *, offering):
    """POST/FILES-dən partiya metadatasını çıxar (view-lar üçün ortaq)."""
    examiner_name = (post.get("examiner_name") or "").strip()
    return {
        "exam_date": parse_exam_date(post.get("exam_date")),
        "examiner": getattr(offering, "instructor", None),
        "examiner_name": examiner_name or instructor_label(offering),
        "invigilator_name": (post.get("invigilator_name") or "").strip()[:200],
        "protocol_number": (post.get("protocol_number") or "").strip()[:64],
        "note": (post.get("sheet_note") or "").strip(),
        "evidence": files.get("sheet_evidence") if files is not None else None,
    }


@transaction.atomic
def create_sheet(
    *,
    offering,
    by_user,
    source=ExamScoreSheetSource.MANUAL,
    exam_date=None,
    examiner=None,
    examiner_name="",
    invigilator_name="",
    protocol_number="",
    note="",
    evidence=None,
    original_filename="",
    request=None,
):
    """Yeni köçürmə partiyası yarat (bal yazılmazdan ƏVVƏL — sətirlər ona bağlanır).

    Skan faylının ölçü/tip validatoru burada işləyir: yanlış fayl bütün
    partiyanı DAYANDIRIR (heç bir bal yazılmır) — yarımçıq partiya qalmasın.
    """
    sheet = ExamScoreSheet(
        organization=offering.organization,
        offering=offering,
        source=source,
        exam_date=exam_date,
        examiner=examiner if examiner is not None else getattr(offering, "instructor", None),
        examiner_name=(examiner_name or instructor_label(offering))[:200],
        invigilator_name=(invigilator_name or "")[:200],
        protocol_number=(protocol_number or "")[:64],
        note=note or "",
        evidence=evidence or "",
        original_filename=(original_filename or "")[:255],
        created_by=by_user,
        created_by_name=correction_author_name(by_user, request),
    )
    sheet.full_clean(exclude=["created_by", "examiner"])
    sheet.save()
    return sheet


def finalize_sheet(sheet, result, *, by_user, request=None):
    """Partiya sayğaclarını yaz + BİR audit xülasəsi (sətir auditləri ayrıdır).

    Heç nə yazılmayıb, heç nə rədd olunmayıb və skan da yoxdursa partiya
    BOŞDUR — silinir ki, tarixçə «0 sətirlik» partiyalarla dolmasın
    (sətir onsuz da ona bağlanmayıb).
    """
    written = int(result.get("written") or 0)
    failed = int(result.get("failed") or 0)
    if not written and not failed and not sheet.evidence:
        sheet.delete()
        return None
    sheet.rows_total = int(result.get("total") or 0)
    sheet.rows_written = written
    sheet.rows_skipped = int(result.get("skipped") or 0)
    sheet.rows_failed = failed
    sheet.save(update_fields=["rows_total", "rows_written", "rows_skipped", "rows_failed", "updated_at"])
    log_action(
        action=AuditAction.CREATE,
        user=by_user,
        organization=sheet.organization,
        obj=sheet,
        reason=f"exam score sheet: {sheet.source}",
        request=request,
        resource_type="registrar.exam_score_sheet",
        resource_id=str(sheet.pk),
        new_values={
            "offering": str(sheet.offering_id),
            "exam_date": sheet.exam_date.isoformat() if sheet.exam_date else "",
            "protocol_number": sheet.protocol_number,
            "rows_total": sheet.rows_total,
            "rows_written": sheet.rows_written,
            "rows_skipped": sheet.rows_skipped,
            "rows_failed": sheet.rows_failed,
        },
    )
    return sheet


def _file_url(field) -> str:
    if not field:
        return ""
    try:
        return field.url
    except ValueError:  # storage yoxdursa səth sınmasın
        return ""


def sheet_row(sheet) -> dict:
    """Partiyanın UI sətri (tarixçə paneli + sətir çekmecəsi)."""
    return {
        "id": str(sheet.id),
        "created": sheet.created_at.strftime("%d.%m.%Y %H:%M"),
        "source": sheet.source,
        "source_label": str(sheet.get_source_display()),
        "is_import": sheet.source == ExamScoreSheetSource.IMPORT,
        "exam_date": sheet.exam_date.strftime("%d.%m.%Y") if sheet.exam_date else "",
        "exam_date_iso": sheet.exam_date.isoformat() if sheet.exam_date else "",
        "examiner_name": sheet.examiner_name,
        "invigilator_name": sheet.invigilator_name,
        "protocol_number": sheet.protocol_number,
        "note": sheet.note,
        "original_filename": sheet.original_filename,
        "rows_total": sheet.rows_total,
        "rows_written": sheet.rows_written,
        "rows_skipped": sheet.rows_skipped,
        "rows_failed": sheet.rows_failed,
        "by": sheet.created_by_name,
        "evidence_url": _file_url(sheet.evidence),
    }


def sheets_for_offering(*, offering, limit=SHEET_HISTORY_LIMIT):
    """Açılışın son partiyaları (ən yenidən köhnəyə) — tarixçə paneli, TƏK sorğu."""
    return [
        sheet_row(sheet) for sheet in ExamScoreSheet.objects.filter(offering=offering).order_by("-created_at")[:limit]
    ]


def latest_sheet_defaults(sheets) -> dict:
    """Formanın ilkin dəyərləri — sonuncu partiyadan (tarix/nəzarətçi/protokol).

    İmtahan mərkəzi bir vərəqi bir neçə oturuşda köçürəndə eyni metadatanı
    təkrar yazmasın; ``sheets`` ``sheets_for_offering`` nəticəsidir (əlavə sorğu yox).
    """
    if not sheets:
        return {"exam_date": "", "examiner_name": "", "invigilator_name": "", "protocol_number": ""}
    last = sheets[0]
    return {
        "exam_date": last["exam_date_iso"],
        "examiner_name": last["examiner_name"],
        "invigilator_name": last["invigilator_name"],
        "protocol_number": last["protocol_number"],
    }


__all__ = [
    "SHEET_HISTORY_LIMIT",
    "create_sheet",
    "finalize_sheet",
    "groups_for_period",
    "instructor_label",
    "latest_sheet_defaults",
    "offerings_for_group",
    "parse_exam_date",
    "sheet_metadata_from_post",
    "sheet_row",
    "sheets_for_offering",
    "subject_label",
]
