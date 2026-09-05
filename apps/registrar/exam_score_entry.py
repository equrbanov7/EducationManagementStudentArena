"""İmtahan balının əl ilə sistemə daxil edilməsi — İmtahan Mərkəzi servisi.

SAHİBİN QƏRARI (2026-08, bağlayıcı): yazılı və praktiki imtahan KAĞIZ üzərində
(praktikidə kodda) keçir — sistemdən getmir. Balları sonradan İmtahan Mərkəzi
köçürür: dövr (tədris ili + semestr) → fənn → QRUP (açılış) → tələbə siyahısı →
hər tələbə üçün bal sahəsi; toplu yadda saxlama.

Qaydalar:

* **Qapı** — ``final_score.entry`` icazəsi (kateqoriya ``exams``); ``exam.*``
  daşıyan imtahan mərkəzi rolları və RİM onsuz da əhatə olunur.
* **Hədəf** — ``registrar.FinalGrade.exam_score``, ``finals.set_exam_score``
  üzərindən; audit izində mənbə «imtahan mərkəzi · əl ilə».
* **Cəhddən asılı deyil** — ENROLLMENT əsaslıdır (kağız imtahanda
  ``ExamAttempt`` yoxdur, spec E8).
* **Kilid** — jurnal kilidi bu yolu BLOKLAMIR: jurnal semestr sonunda bağlanır,
  imtahan ondan sonra keçir (bax ``finals.set_exam_score`` şərhi).
* **İdempotent** — eyni bal təkrar yazılsa nə dublikat sətir, nə audit yaranır.
* **İlk daxiletmə sərbəst, sonrakı dəyişiklik TƏQDİMATLI** — artıq yazılmış bal
  dəyişdirilirsə səbəb + qeyd + SƏNƏD üçü də məcburidir
  (``apps/registrar/corrections.py`` ilə eyni müqavilə).

Sübut sətirləri append-only ``ExamScoreEntry`` jurnalındadır.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils.translation import pgettext

from core.audit import log_action
from core.constants import AuditAction

from . import exam_attempt_history, finals, gradebook
from .corrections import correction_author_name
from .models import (
    CorrectionReason,
    Enrollment,
    ExamScoreEntry,
    ExamScoreEntryKind,
    FinalGrade,
)

#: Bu səthi açan icazə açarı (kataloq: ``organizations.permissions``).
ENTRY_PERMISSION = "final_score.entry"

#: Audit izində bal sətrinin yanına yazılan mənbə qeydi (spec E4).
SOURCE_NOTE = "imtahan mərkəzi · əl ilə"

_CTX = "registrar.exam_score_entry"


# ── İcazə ────────────────────────────────────────────────────────────────────


def _permission_scope(user, organization):
    from django.apps import apps as django_apps

    org_unit_model = django_apps.get_model("organizations", "OrgUnit")
    return org_unit_model.user_permission_scope(user, organization, ENTRY_PERMISSION)


def can_enter_exam_scores(user, organization) -> bool:
    """``final_score.entry`` icazəsi struktur əhatəsi verirmi (org və ya unit)."""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if _is_superadmin(user):
        return True
    if organization is None:
        return False
    return _permission_scope(user, organization).has_structure_access


def _is_superadmin(user) -> bool:
    return bool(getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False))


def offering_in_actor_scope(user, organization, offering) -> bool:
    """Aktorun struktur alt-ağacı bu açılışı əhatə edirmi (fail-closed).

    ``exam.*`` wildcard-ı dekan/kafedra müdiri kimi UNIT-scoped rollara da
    ``final_score.entry`` verir — onlar YALNIZ öz alt-ağaclarının qruplarına bal
    yaza bilməlidir. Org-səviyyə rollar (imtahan mərkəzi, RİM) hər açılışı görür.
    """
    if _is_superadmin(user):
        return True
    if organization is None or offering is None:
        return False
    from . import journal_scope

    return journal_scope.offering_in_actor_scope(user, organization, offering, permission=ENTRY_PERMISSION)


def offerings_in_actor_scope(user, organization, offerings):
    """``offerings`` siyahısını aktorun əhatəsinə görə BİR sorğu ilə süzür.

    Əvvəl seçici hər açılış üçün ``offering_in_actor_scope`` çağırırdı — 62 açılış
    = 62 əhatə + 62 təşkilat sorğusu (QA 2026-09-05 P2-5).
    """
    offerings = list(offerings)
    if not offerings:
        return []
    if _is_superadmin(user):
        return offerings
    if organization is None:
        return []
    from . import journal_scope

    scope = journal_scope.permission_scope_for(user, organization, ENTRY_PERMISSION)
    if not scope.has_structure_access:
        return []
    if scope.is_org_wide:
        return offerings
    from django.apps import apps as django_apps

    group_ids = {getattr(o, "group_id", None) for o in offerings} - {None}
    org_unit_model = django_apps.get_model("organizations", "OrgUnit")
    allowed = set(
        org_unit_model.objects.filter(organization=organization, pk__in=group_ids)
        .filter(scope.unit_subtree_q())
        .values_list("pk", flat=True)
    )
    return [o for o in offerings if getattr(o, "group_id", None) in allowed]


def assert_offering_in_actor_scope(user, organization, offering):
    """Əhatədən kənar açılışda yazını fail-closed dayandır."""
    if not offering_in_actor_scope(user, organization, offering):
        raise PermissionDenied(pgettext(_CTX, "Bu açılış sizin struktur əhatənizdə deyil."))


# ── Oxu: dövr → fənn → qrup (açılış) → tələbə siyahısı ───────────────────────


def subjects_for_period(*, organization, period):
    """Bu dövrdə açılışı olan fənlər (kod + ad ilə, təkrarsız)."""
    if organization is None or period is None:
        return []
    from .models import CourseOffering

    rows = (
        CourseOffering.objects.filter(organization=organization, period=period, is_active=True)
        .select_related("subject")
        .order_by("subject__code", "subject__name")
        .values("subject_id", "subject__code", "subject__name")
        .distinct()
    )
    return [{"id": str(row["subject_id"]), "code": row["subject__code"], "name": row["subject__name"]} for row in rows]


def offerings_for_subject(*, organization, period, subject_id):
    """Fənnin bu dövrdəki açılışları — QRUP seçimi üçün (qrup adı ilə)."""
    if organization is None or period is None or not subject_id:
        return []
    from .models import CourseOffering

    return list(
        CourseOffering.objects.filter(organization=organization, period=period, subject_id=subject_id, is_active=True)
        .select_related("subject", "group", "instructor")
        .order_by("group__name", "subject__code")
    )


def offering_label(offering) -> str:
    """Açılışın qrup etiketi — qrup yoxdursa «(qrupsuz)»."""
    group = getattr(offering, "group", None)
    if group is not None:
        return group.name
    return pgettext(_CTX, "(qrupsuz açılış)")


def _entry_row(entry) -> dict:
    data = {
        "id": str(entry.id),
        "date": entry.created_at.strftime("%d.%m.%Y %H:%M"),
        "kind": entry.kind,
        "is_correction": entry.kind == ExamScoreEntryKind.CORRECTION,
        "old": entry.old_score if entry.old_score is not None else "—",
        "new": entry.new_score if entry.new_score is not None else "—",
        "reason": entry.get_reason_display() if entry.reason else "",
        "note": entry.note,
        "by": entry.entered_by_name,
        "evidence_url": "",
    }
    if entry.evidence:
        try:
            data["evidence_url"] = entry.evidence.url
        except ValueError:  # storage yoxdursa səth sınmasın
            data["evidence_url"] = ""
    return data


def roster_for_offering(*, offering):
    """Açılışın tələbə siyahısı — bal sahəsi, tarixçə və cəhd güzgüsü ilə.

    Hər sətir::

        {"enrollment", "student", "exam_score", "exam_score_max", "entry_score",
         "total", "letter", "has_score", "entries": [...], "attempts": [...]}
    """
    scheme = gradebook.ensure_assessment_scheme(offering=offering)
    enrollments = list(
        offering.enrollments.filter(status=Enrollment.Status.ENROLLED)
        .select_related("student", "offering", "offering__subject")
        .order_by("student__last_name", "student__first_name", "student__username")
    )
    entries_by_enrollment: dict[str, list] = {}
    for entry in ExamScoreEntry.objects.filter(enrollment__in=enrollments).select_related("entered_by"):
        entries_by_enrollment.setdefault(str(entry.enrollment_id), []).append(entry)

    rows = []
    for enrollment in enrollments:
        result = finals.compute_final_result(enrollment=enrollment, scheme=scheme)
        history = entries_by_enrollment.get(str(enrollment.id), [])
        rows.append(
            {
                "enrollment": enrollment,
                "student": enrollment.student,
                "exam_score": result["exam_score"],
                "has_score": result["exam_score"] is not None,
                "exam_score_max": result["exam_score_max"],
                "entry_score": result["entry_score"],
                "total": result["total"],
                "letter": result["letter"],
                "graded": result["graded"],
                "entries": [_entry_row(entry) for entry in history],
                "attempts": exam_attempt_history.attempt_rows_for_enrollment(enrollment),
            }
        )
    return {"offering": offering, "scheme": scheme, "rows": rows, "exam_score_max": finals.exam_score_max(scheme)}


# ── Yazı ─────────────────────────────────────────────────────────────────────


def _clean_score(raw, cap):
    """Bal TAM ədəddir (0..cap). Boş sətir → ``None`` (sətir buraxılır)."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        value = Decimal(text)
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError(pgettext(_CTX, "Bal rəqəm olmalıdır."))
    if value != value.to_integral_value():
        raise ValidationError(pgettext(_CTX, "Bal tam ədəd olmalıdır."))
    value = value.to_integral_value()
    if value < 0 or value > Decimal(int(cap)):
        raise ValidationError(pgettext(_CTX, "Bal 0 ilə %(max)s arasında olmalıdır.") % {"max": int(cap)})
    return value


def _same_score(old, new) -> bool:
    if old is None or new is None:
        return old is None and new is None
    return Decimal(old) == Decimal(new)


def _require_justification(*, reason, note, evidence):
    """Sonrakı dəyişiklik = TƏQDİMAT: səbəb + qeyd + sənəd (üçü də məcburi)."""
    if reason not in CorrectionReason.values:
        raise ValidationError(pgettext(_CTX, "Balı dəyişmək üçün səbəb seçilməlidir."))
    if not (note or "").strip():
        raise ValidationError(pgettext(_CTX, "Balı dəyişmək üçün izahat qeydi məcburidir."))
    if not evidence:
        raise ValidationError(pgettext(_CTX, "Balı dəyişmək üçün təsdiqedici sənəd əlavə olunmalıdır."))


@transaction.atomic
def record_exam_score(*, enrollment, score, by_user, reason="", note="", evidence=None, request=None):
    """Bir tələbənin imtahan balını yaz (ilkin daxiletmə və ya sənədli düzəliş).

    Nəticə: yaradılan :class:`ExamScoreEntry` (bal dəyişibsə) və ya ``None``
    (dəyişiklik yoxdur — İDEMPOTENT təkrar daxiletmə).
    """
    scheme = gradebook.ensure_assessment_scheme(offering=enrollment.offering)
    cap = finals.exam_score_max(scheme)
    new_score = _clean_score(score, cap)
    if new_score is None:
        return None  # boş sahə = toxunma (kütləvi silinmə riskini aradan qaldırır)

    current = FinalGrade.objects.filter(enrollment=enrollment).first()
    old_score = current.exam_score if current is not None else None
    if _same_score(old_score, new_score):
        return None  # eyni bal → nə dublikat sətir, nə audit

    is_correction = old_score is not None
    if is_correction:
        _require_justification(reason=reason, note=note, evidence=evidence)

    entry = ExamScoreEntry(
        organization=enrollment.organization,
        enrollment=enrollment,
        kind=ExamScoreEntryKind.CORRECTION if is_correction else ExamScoreEntryKind.INITIAL,
        old_score=old_score,
        new_score=new_score,
        reason=reason if reason in CorrectionReason.values else "",
        note=(note or "").strip(),
        evidence=evidence or "",
        entered_by=by_user,
        entered_by_name=correction_author_name(by_user, request),
    )
    # Fayl (şəkil/PDF) ölçü + tip validatorları BAL YAZILMAMIŞDAN ƏVVƏL işləsin.
    entry.full_clean(exclude=["entered_by"])

    final_grade = finals.set_exam_score(
        enrollment=enrollment, score=new_score, by_user=by_user, source_note=SOURCE_NOTE
    )
    if final_grade is None:
        # Qeydiyyat artıq aktiv deyil (köçürülüb/ləğv olunub) — sətir yazılmır.
        raise ValidationError(pgettext(_CTX, "Bu qeydiyyat aktiv deyil — bal yazılmadı."))

    entry.save()
    log_action(
        action=AuditAction.UPDATE,
        user=by_user,
        organization=enrollment.organization,
        obj=entry,
        reason=f"exam score entry: {entry.kind}",
        request=request,
        resource_type="registrar.exam_score_entry",
        resource_id=str(entry.pk),
        changes=[
            {
                "field": "exam_score",
                "old": str(old_score) if old_score is not None else "—",
                "new": str(new_score),
            }
        ],
    )
    return entry


def save_roster_scores(*, offering, rows, by_user, request=None):
    """Formadan gələn sətirləri toplu yaz.

    ``rows`` — ``{"enrollment_id", "score", "reason", "note", "evidence"}``
    lüğətləri. Hər sətir öz savepoint-ində yazılır: birinin rədd olunması
    (məs. sənədsiz dəyişiklik) digərlərinin yazılmasını dayandırmır; xətalar
    toplanıb geri qaytarılır.

    Nəticə: ``{"written": int, "skipped": int, "errors": [(ad, mesaj), …]}``
    """
    enrollments = {
        str(enrollment.id): enrollment
        for enrollment in offering.enrollments.filter(status=Enrollment.Status.ENROLLED).select_related(
            "student", "offering"
        )
    }
    written, skipped, errors = 0, 0, []
    for row in rows:
        enrollment = enrollments.get(str(row.get("enrollment_id") or ""))
        if enrollment is None:
            continue
        try:
            with transaction.atomic():
                entry = record_exam_score(
                    enrollment=enrollment,
                    score=row.get("score"),
                    by_user=by_user,
                    reason=row.get("reason") or "",
                    note=row.get("note") or "",
                    evidence=row.get("evidence"),
                    request=request,
                )
        except ValidationError as exc:
            errors.append((_student_label(enrollment), " ".join(exc.messages)))
            continue
        if entry is None:
            skipped += 1
        else:
            written += 1
    return {"written": written, "skipped": skipped, "errors": errors}


def _student_label(enrollment) -> str:
    student = enrollment.student
    return student.get_full_name() or student.username


def entries_for_offering(*, offering):
    """Açılış üzrə bütün daxiletmə tarixçəsi (ən yenidən köhnəyə)."""
    return list(
        ExamScoreEntry.objects.filter(enrollment__offering=offering)
        .select_related("enrollment", "enrollment__student", "entered_by")
        .order_by("-created_at")
    )
