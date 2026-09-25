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

from . import exam_score_period_lock
from . import exam_score_questions as questions
from .corrections import correction_author_name
from .models import CourseOffering, ExamScoreSheet, ExamScoreSheetSource
from .models.exam_score_entry import ExamScoreSheetKind

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


def clean_exam_kind(raw) -> str:
    """İmtahan növü — ``written`` / ``practical``; boş → ``written`` (defolt), yad dəyər → xəta."""
    value = (raw or "").strip() if isinstance(raw, str) else raw
    if not value:
        return ExamScoreSheetKind.WRITTEN
    if value not in ExamScoreSheetKind.values:
        raise ValidationError(pgettext(_CTX, "İmtahan növü yazılı və ya praktiki olmalıdır."))
    return value


def sheet_metadata_from_post(post, files, *, offering):
    """POST/FILES-dən partiya metadatasını çıxar (view-lar üçün ortaq).

    2026-09-14 (W2 `w2paper`): ``question_count`` / ``question_max`` — vərəqin
    sual şəbəkəsi (boş → defolt 5 × 10; yanlış → ``ValidationError``).
    """
    examiner_name = (post.get("examiner_name") or "").strip()
    question_count, question_max = questions.clean_question_grid(post.get("question_count"), post.get("question_max"))
    # 2026-09-14 (sahibin rəyi): yoxlayan / nəzarətçi SEÇİLİR (istifadəçi id-si);
    # boş yoxlayan = açılışın müəllimi; köhnə sərbəst-mətn sahələri fallback kimi oxunur.
    examiner = resolve_staff_user(post.get("examiner"), offering=offering) or getattr(offering, "instructor", None)
    invigilator = resolve_staff_user(post.get("invigilator"), offering=offering)
    return {
        "exam_date": parse_exam_date(post.get("exam_date")),
        "exam_kind": clean_exam_kind(post.get("exam_kind")),
        "question_count": question_count,
        "question_max": question_max,
        "examiner": examiner,
        "examiner_name": _person_label(examiner) or examiner_name or instructor_label(offering),
        "invigilator": invigilator,
        "invigilator_name": _person_label(invigilator) or (post.get("invigilator_name") or "").strip()[:200],
        "protocol_number": (post.get("protocol_number") or "").strip()[:64],
        "note": (post.get("sheet_note") or "").strip(),
        # 2026-09-26: təsdiq dialoqunun öz fayl sahəsi (``justification_evidence``)
        # üstündür; yoxdursa vərəq kartındakı ``sheet_evidence`` (bax period_lock).
        "evidence": exam_score_period_lock.submission_evidence(files),
    }


def _person_label(user) -> str:
    if user is None:
        return ""
    return user.get_full_name() or user.username


def resolve_staff_user(raw_id, *, offering):
    """Formadan gələn istifadəçi id-si → təşkilatın AKTİV üzvü olan istifadəçi; boş → ``None``.

    Yad / naməlum id fail-closed ``ValidationError`` verir (mesaj mövcud kataloq cütüdür).
    """
    from django.contrib.auth import get_user_model

    raw = (raw_id or "").strip() if isinstance(raw_id, str) else raw_id
    if not raw:
        return None
    try:
        user = get_user_model().objects.filter(pk=int(raw)).first()
    except (TypeError, ValueError):
        user = None
    if user is None:
        raise ValidationError(pgettext("accounts.groups", "Seçilmiş şəxs bu təşkilatın aktiv üzvü deyil."))
    _assert_examiner_in_organization(user, offering)
    return user


def _assert_examiner_in_organization(examiner, offering):
    """I2 (Codex audit P2-09, 2026-09-13): açıq verilən yoxlayan müəllim açılışın təşkilatında AKTİV üzv olmalıdır.

    «Aktiv üzv» tərifi ``0041`` ``registrar_member_has_permission``-la eynidir:
    üzvlük aktiv VƏ rolu aktiv. QƏSDƏN DB trigger-i yoxdur — üzvlüklər dəyişir,
    vərəq isə tarixi snapshot-dur (müəllim sonradan təşkilatdan çıxsa köhnə
    vərəq etibarsız olmamalıdır). Açılışın öz müəllimi yoxlanmır: defolt yoldur
    və üzvlüyü təyinat anında DB-də (``registrar_active_member_instructor_guard``)
    təsdiqlənib. Mesaj mövcud kataloq cütüdür (``accounts.groups``) — yeni i18n
    borcu yaranmır.
    """
    if examiner is None or examiner.pk == getattr(offering, "instructor_id", None):
        return
    is_member = examiner.memberships.filter(
        organization_id=offering.organization_id, is_active=True, role__is_active=True
    ).exists()
    if not is_member:
        raise ValidationError(pgettext("accounts.groups", "Seçilmiş şəxs bu təşkilatın aktiv üzvü deyil."))


@transaction.atomic
def create_sheet(
    *,
    offering,
    by_user,
    source=ExamScoreSheetSource.MANUAL,
    exam_date=None,
    examiner=None,
    examiner_name="",
    invigilator=None,
    invigilator_name="",
    protocol_number="",
    note="",
    evidence=None,
    original_filename="",
    request=None,
    question_count=None,
    question_max=None,
    exam_kind=ExamScoreSheetKind.WRITTEN,
):
    """Yeni köçürmə partiyası yarat (bal yazılmazdan ƏVVƏL — sətirlər ona bağlanır).

    Skan faylının ölçü/tip validatoru burada işləyir: yanlış fayl bütün
    partiyanı DAYANDIRIR (heç bir bal yazılmır) — yarımçıq partiya qalmasın.
    Tenant/əlaqə invariantları (P2-09): vərəq ↔ açılış təşkilatı və skanın
    org-prefiksi ``ExamScoreSheet.clean()``-də, yoxlayanın üzvlüyü burada,
    hamısının son səddi ``0073`` trigger-idir.
    """
    examiner = examiner if examiner is not None else getattr(offering, "instructor", None)
    _assert_examiner_in_organization(examiner, offering)
    if invigilator is not None:
        _assert_examiner_in_organization(invigilator, offering)
        invigilator_name = invigilator_name or _person_label(invigilator)
    grid = questions.question_defaults()
    if question_count is not None:
        grid["question_count"] = int(question_count)
    if question_max is not None:
        grid["question_max"] = int(question_max)
    sheet = ExamScoreSheet(
        organization=offering.organization,
        offering=offering,
        source=source,
        exam_kind=clean_exam_kind(exam_kind),
        exam_date=exam_date,
        examiner=examiner,
        examiner_name=(examiner_name or _person_label(examiner) or instructor_label(offering))[:200],
        invigilator=invigilator,
        invigilator_name=(invigilator_name or "")[:200],
        protocol_number=(protocol_number or "")[:64],
        note=note or "",
        evidence=evidence or "",
        original_filename=(original_filename or "")[:255],
        question_count=grid["question_count"],
        question_max=grid["question_max"],
        created_by=by_user,
        created_by_name=correction_author_name(by_user, request),
    )
    sheet.full_clean(exclude=["created_by", "examiner", "invigilator"])
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
        "exam_kind": sheet.exam_kind,
        "exam_kind_label": str(sheet.get_exam_kind_display()),
        "is_practical": sheet.exam_kind == ExamScoreSheetKind.PRACTICAL,
        "exam_date": sheet.exam_date.strftime("%d.%m.%Y") if sheet.exam_date else "",
        "exam_date_iso": sheet.exam_date.isoformat() if sheet.exam_date else "",
        "examiner_id": str(sheet.examiner_id) if sheet.examiner_id else "",
        "examiner_name": sheet.examiner_name,
        "invigilator_id": str(sheet.invigilator_id) if sheet.invigilator_id else "",
        "invigilator_name": sheet.invigilator_name,
        "protocol_number": sheet.protocol_number,
        "note": sheet.note,
        "original_filename": sheet.original_filename,
        "rows_total": sheet.rows_total,
        "rows_written": sheet.rows_written,
        "rows_skipped": sheet.rows_skipped,
        "rows_failed": sheet.rows_failed,
        "question_count": sheet.question_count,
        "question_max": sheet.question_max,
        "by": sheet.created_by_name,
        "evidence_url": _file_url(sheet.evidence),
    }


def sheets_for_offering(*, offering, limit=SHEET_HISTORY_LIMIT, exam_kind=""):
    """Açılışın son partiyaları (ən yenidən köhnəyə) — tarixçə paneli, TƏK sorğu.

    ``exam_kind`` — ``written`` / ``practical`` çipi (boş → hamısı; addendum 2026-09-14).
    """
    queryset = ExamScoreSheet.objects.filter(offering=offering)
    if exam_kind in ExamScoreSheetKind.values:
        queryset = queryset.filter(exam_kind=exam_kind)
    return [sheet_row(sheet) for sheet in queryset.order_by("-created_at")[:limit]]


def latest_sheet_defaults(sheets) -> dict:
    """Formanın ilkin dəyərləri — sonuncu partiyadan (tarix/nəzarətçi/protokol).

    İmtahan mərkəzi bir vərəqi bir neçə oturuşda köçürəndə eyni metadatanı
    təkrar yazmasın; ``sheets`` ``sheets_for_offering`` nəticəsidir (əlavə sorğu yox).
    """
    grid = questions.question_defaults()
    if not sheets:
        return {
            "exam_date": "",
            "exam_kind": ExamScoreSheetKind.WRITTEN,
            "examiner_id": "",
            "examiner_name": "",
            "invigilator_id": "",
            "invigilator_name": "",
            "protocol_number": "",
            **grid,
        }
    last = sheets[0]
    return {
        "exam_date": last["exam_date_iso"],
        "exam_kind": last.get("exam_kind", ExamScoreSheetKind.WRITTEN),
        "examiner_id": last.get("examiner_id", ""),
        "examiner_name": last["examiner_name"],
        "invigilator_id": last.get("invigilator_id", ""),
        "invigilator_name": last["invigilator_name"],
        "protocol_number": last["protocol_number"],
        # Sahib 2026-09-26: «sual sayı default olaraq 5 olmalıdır, balda 10». Sonuncu vərəqin
        # şəbəkəsi yalnız DOLUDURSA miras qalır — «0 — yalnız yekun bal» (köhnə vərəq) və ya
        # boş dəyər növbəti köçürmənin defaultunu sıfırlamasın.
        "question_count": last.get("question_count") or grid["question_count"],
        "question_max": last.get("question_max") or grid["question_max"],
    }


__all__ = [
    "SHEET_HISTORY_LIMIT",
    "clean_exam_kind",
    "create_sheet",
    "finalize_sheet",
    "groups_for_period",
    "instructor_label",
    "latest_sheet_defaults",
    "offerings_for_group",
    "parse_exam_date",
    "resolve_staff_user",
    "sheet_metadata_from_post",
    "sheet_row",
    "sheets_for_offering",
    "subject_label",
]
