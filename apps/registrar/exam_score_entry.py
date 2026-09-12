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

2026-09-12 (sahibin tələbi — «qrup seçilsin, müəllim, tarix… balları sistemə
yüklənsin»): hər toplu yazı bir KÖÇÜRMƏ VƏRƏQİNƏ (``ExamScoreSheet`` partiyası:
imtahan tarixi, yoxlayan müəllim, nəzarətçi, protokol №, skan) bağlanır —
``sheet`` parametri. Partiyanın skanı düzəliş üçün SƏNƏD sayılır: sətir-səviyyə
fayl olmasa da ``sheet.evidence`` təqdimat tələbini ödəyir. Qrup-əvvəl seçim və
partiya köməkçiləri ``exam_score_sheets``-də, fayl idxalı ``exam_score_import``-da
— hər ikisi YALNIZ buradakı ``record_exam_score`` ilə yazır (tək yazı yolu).
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


def _file_url(field) -> str:
    """FileField URL-i — storage yoxdursa səth sınmasın."""
    if not field:
        return ""
    try:
        return field.url
    except ValueError:
        return ""


def _entry_row(entry) -> dict:
    """Tarixçə sətri — partiya (vərəq) metadatası ilə (2026-09-12).

    ``sheet`` select_related ilə gəlir; sətrin öz sənədi yoxdursa partiyanın
    skanı göstərilir (düzəliş sübutu partiya səviyyəsində də ola bilər).
    """
    sheet = entry.sheet if entry.sheet_id else None
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
        "evidence_url": _file_url(entry.evidence),
        "sheet_id": str(sheet.id) if sheet is not None else "",
        "sheet_exam_date": sheet.exam_date.strftime("%d.%m.%Y") if sheet is not None and sheet.exam_date else "",
        "sheet_protocol": sheet.protocol_number if sheet is not None else "",
        "sheet_examiner": sheet.examiner_name if sheet is not None else "",
        "sheet_source": sheet.source if sheet is not None else "",
        "sheet_evidence_url": _file_url(sheet.evidence) if sheet is not None else "",
    }
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
        .select_related("student", "student__profile", "offering", "offering__subject")
        .order_by("student__last_name", "student__first_name", "student__username")
    )
    entries_by_enrollment: dict[str, list] = {}
    for entry in ExamScoreEntry.objects.filter(enrollment__in=enrollments).select_related("entered_by", "sheet"):
        entries_by_enrollment.setdefault(str(entry.enrollment_id), []).append(entry)

    # Komponent/bal/FinalGrade/ResitRecord oxumaları BİR dəfə toplu (əvvəl hər
    # tələbə üçün ayrıca — 58 tələbə ≈ 170 sorğu; QA 2026-09-05 P2-5).
    from . import finals_batch

    batch = finals_batch.build(enrollments)

    # Cəhd tarixçəsi də TOPLU oxunur: əvvəl hər sətir üçün ayrıca
    # `attempt_rows_for_enrollment` çağırılırdı (29 tələbəli açılışda ≈ 70 əlavə
    # sorğu — 2026-09-10 ölçməsi 120 → 63). Toplu güzgü onsuz da mövcud idi.
    attempts_by_student = exam_attempt_history.attempt_rows_by_student(
        student_ids=[enrollment.student_id for enrollment in enrollments],
        subject_id=offering.subject_id,
        organization=offering.organization,
    )

    rows = []
    for enrollment in enrollments:
        result = finals.compute_final_result(enrollment=enrollment, scheme=scheme, batch=batch)
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
                "attempts": attempts_by_student.get(enrollment.student_id, []),
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
    if not value.is_finite() or value != value.to_integral_value():
        raise ValidationError(pgettext(_CTX, "Bal tam ədəd olmalıdır."))
    value = value.to_integral_value()
    if value < 0 or value > Decimal(int(cap)):
        raise ValidationError(pgettext(_CTX, "Bal 0 ilə %(max)s arasında olmalıdır.") % {"max": int(cap)})
    return value


def _same_score(old, new) -> bool:
    if old is None or new is None:
        return old is None and new is None
    return Decimal(old) == Decimal(new)


def _require_justification(*, reason, note, evidence, sheet=None):
    """Sonrakı dəyişiklik = TƏQDİMAT: səbəb + qeyd + sənəd (üçü də məcburi).

    2026-09-12: sənəd sətrin öz faylı VƏ YA partiyanın (vərəqin) skanı ola
    bilər — toplu köçürmədə bir protokol bütün dəyişiklikləri əsaslandırır,
    hər sətir üçün eyni faylı təkrar saxlamağa ehtiyac yoxdur.
    """
    if reason not in CorrectionReason.values:
        raise ValidationError(pgettext(_CTX, "Balı dəyişmək üçün səbəb seçilməlidir."))
    if not (note or "").strip():
        raise ValidationError(pgettext(_CTX, "Balı dəyişmək üçün izahat qeydi məcburidir."))
    if not evidence and not (sheet is not None and sheet.evidence):
        raise ValidationError(pgettext(_CTX, "Balı dəyişmək üçün təsdiqedici sənəd əlavə olunmalıdır."))


@transaction.atomic
def record_exam_score(*, enrollment, score, by_user, reason="", note="", evidence=None, request=None, sheet=None):
    """Bir tələbənin imtahan balını yaz (ilkin daxiletmə və ya sənədli düzəliş).

    Nəticə: yaradılan :class:`ExamScoreEntry` (bal dəyişibsə) və ya ``None``
    (dəyişiklik yoxdur — İDEMPOTENT təkrar daxiletmə).

    ``sheet`` — sətrin aid olduğu köçürmə partiyası (``ExamScoreSheet``);
    verilərsə sətir ona bağlanır və partiyanın skanı düzəliş sübutu sayılır.
    """
    # Lock the durable parent even when no FinalGrade exists yet. Concurrent
    # first writes must re-read the score and require correction evidence.
    enrollment = (
        Enrollment.objects.select_for_update(of=("self",))
        .select_related("offering", "organization")
        .get(pk=enrollment.pk, organization_id=enrollment.organization_id)
    )
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
        _require_justification(reason=reason, note=note, evidence=evidence, sheet=sheet)
    if sheet is not None and (
        sheet.offering_id != enrollment.offering_id or sheet.organization_id != enrollment.organization_id
    ):
        # Partiya başqa açılışa aiddirsə sətir ona bağlana bilməz (fail-closed).
        raise ValidationError(pgettext(_CTX, "Köçürmə vərəqi bu açılışa aid deyil."))

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
        sheet=sheet,
    )
    # Fayl (şəkil/PDF) ölçü + tip validatorları BAL YAZILMAMIŞDAN ƏVVƏL işləsin.
    entry.full_clean(exclude=["entered_by", "sheet"])

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


def save_roster_scores(*, offering, rows, by_user, request=None, sheet=None):
    """Formadan gələn sətirləri toplu yaz.

    ``rows`` — ``{"enrollment_id", "score", "reason", "note", "evidence"}``
    lüğətləri. Hər sətir öz savepoint-ində yazılır: birinin rədd olunması
    (məs. sənədsiz dəyişiklik) digərlərinin yazılmasını dayandırmır; xətalar
    toplanıb geri qaytarılır.

    ``sheet`` — bütün sətirlərin bağlandığı köçürmə partiyası (2026-09-12);
    sayğacları çağıran tərəf ``exam_score_sheets.finalize_sheet`` ilə yazır.

    Nəticə: ``{"written", "skipped", "failed", "total", "errors": [(ad, mesaj), …],
    "failed_by_enrollment": {enrollment_id: mesaj}}`` (sonuncu — eyni adlı iki
    tələbənin xətası qarışmasın deyə, fayl idxalı üçün).
    """
    enrollments = {
        str(enrollment.id): enrollment
        for enrollment in offering.enrollments.filter(status=Enrollment.Status.ENROLLED).select_related(
            "student", "offering"
        )
    }
    written, skipped, total, errors, failed_by_enrollment = 0, 0, 0, [], {}
    written_ids = []
    for row in rows:
        enrollment_id = str(row.get("enrollment_id") or "")
        enrollment = enrollments.get(enrollment_id)
        total += 1
        if enrollment is None:
            message = pgettext(_CTX, "Bu qeydiyyat aktiv deyil — bal yazılmadı.")
            errors.append((enrollment_id, message))
            failed_by_enrollment[enrollment_id] = message
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
                    sheet=sheet,
                )
        except ValidationError as exc:
            message = " ".join(exc.messages)
            errors.append((_student_label(enrollment), message))
            failed_by_enrollment[str(enrollment.id)] = message
            continue
        if entry is None:
            skipped += 1
        else:
            written += 1
            written_ids.append(str(enrollment.id))
    return {
        "written": written,
        "skipped": skipped,
        "failed": len(errors),
        "total": total,
        "errors": errors,
        "failed_by_enrollment": failed_by_enrollment,
        "written_ids": written_ids,
    }


def _student_label(enrollment) -> str:
    student = enrollment.student
    return student.get_full_name() or student.username


def entries_for_offering(*, offering):
    """Açılış üzrə bütün daxiletmə tarixçəsi (ən yenidən köhnəyə)."""
    return list(
        ExamScoreEntry.objects.filter(enrollment__offering=offering)
        .select_related("enrollment", "enrollment__student", "entered_by", "sheet")
        .order_by("-created_at")
    )
