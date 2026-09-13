"""İmtahan balı köçürməsi — OXU köməkçiləri: dövr → fənn → qrup → tələbə siyahısı.

2026-09-14 (W2 `w2paper`): ``exam_score_entry``-dən (modul-ölçü büdcəsi,
SOFT_CAP=600) buraya köçürülüb; ``exam_score_entry`` eyni adları re-eksport
edir — çağıranlar üçün API dəyişməyib. Əlavə olaraq:

* siyahı sətrində SONUNCU daxiletmənin sual-sual balları (``question_scores``)
  və dəyişiklik işarəsi (``is_changed`` — ``kind != initial`` sətri varmı);
* :func:`filter_roster_rows` — tələbə axtarışı (ad / istifadəçi adı / FİN /
  tələbə №) və vəziyyət çipləri (hamısı · boş · yazılıb · dəyişdirilib) —
  YADDAŞDA süzülür, əlavə sorğu yoxdur (sorğu büdcəsi siyahı ölçüsündən asılı
  deyil);
* :func:`instructors_for_period` — dövrün açılışlarının müəllimləri (müəllim
  seçici üçün, BİR sorğu).

Heç bir ``apps.exams`` / ``apps.accounts`` importu yoxdur (module_deps).
"""

from __future__ import annotations

from django.utils.translation import pgettext

from . import exam_attempt_history, finals, gradebook
from .models import CourseOffering, Enrollment, ExamScoreEntry, ExamScoreEntryKind
from .models.exam_score_entry import ExamScoreSheetKind

_CTX = "registrar.exam_score_entry"

#: Vəziyyət çipləri (``ese_status`` parametri).
STATUS_ALL = "all"
STATUS_EMPTY = "empty"
STATUS_RECORDED = "recorded"
STATUS_CHANGED = "changed"
STATUS_CHOICES = (STATUS_ALL, STATUS_EMPTY, STATUS_RECORDED, STATUS_CHANGED)


def subjects_for_period(*, organization, period):
    """Bu dövrdə açılışı olan fənlər (kod + ad ilə, təkrarsız)."""
    if organization is None or period is None:
        return []
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
    return list(
        CourseOffering.objects.filter(organization=organization, period=period, subject_id=subject_id, is_active=True)
        .select_related("subject", "group", "instructor")
        .order_by("group__name", "subject__code")
    )


def instructors_for_period(*, organization, period, group_ids=None):
    """Dövrün aktiv açılışlarının müəllimləri — müəllim seçicisi üçün (BİR sorğu, təkrarsız).

    ``group_ids`` verilərsə (unit-scoped aktor) yalnız həmin qrupların
    açılışları sayılır — seçici aktorun görmədiyi müəllimi göstərmir.
    """
    if organization is None or period is None:
        return []
    queryset = CourseOffering.objects.filter(
        organization=organization, period=period, is_active=True, instructor__isnull=False
    )
    if group_ids is not None:
        queryset = queryset.filter(group_id__in=list(group_ids))
    rows = (
        queryset.values("instructor_id", "instructor__first_name", "instructor__last_name", "instructor__username")
        .distinct()
        .order_by("instructor__last_name", "instructor__first_name", "instructor__username")
    )
    result = []
    for row in rows:
        name = f"{row['instructor__first_name'] or ''} {row['instructor__last_name'] or ''}".strip()
        result.append({"id": str(row["instructor_id"]), "name": name or row["instructor__username"]})
    return result


def group_ids_for_instructor(*, organization, period, instructor_id) -> set:
    """Bu müəllimin dövrdə açılışı olan qrup id-ləri (str) — qrup seçicisini daraltmaq üçün, BİR sorğu."""
    if organization is None or period is None or not instructor_id:
        return set()
    return {
        str(pk)
        for pk in CourseOffering.objects.filter(
            organization=organization, period=period, is_active=True, instructor_id=instructor_id, group__isnull=False
        )
        .values_list("group_id", flat=True)
        .distinct()
    }


def offering_label(offering) -> str:
    """Açılışın qrup etiketi — qrup yoxdursa «(qrupsuz)»."""
    group = getattr(offering, "group", None)
    if group is not None:
        return group.name
    return pgettext(_CTX, "(qrupsuz açılış)")


def file_url(field) -> str:
    """FileField URL-i — storage yoxdursa səth sınmasın."""
    if not field:
        return ""
    try:
        return field.url
    except ValueError:
        return ""


def entry_row(entry) -> dict:
    """Tarixçə sətri — partiya (vərəq) metadatası ilə (2026-09-12).

    ``sheet`` select_related ilə gəlir; sətrin öz sənədi yoxdursa partiyanın
    skanı göstərilir (düzəliş sübutu partiya səviyyəsində də ola bilər).
    2026-09-14: ``is_change`` (``kind != initial``), ``kind_label`` və
    ``question_scores`` («S1…Sn» bölgüsü) əlavə olundu.
    """
    sheet = entry.sheet if entry.sheet_id else None
    return {
        "id": str(entry.id),
        "date": entry.created_at.strftime("%d.%m.%Y %H:%M"),
        "kind": entry.kind,
        "kind_label": str(entry.get_kind_display()),
        "is_correction": entry.kind == ExamScoreEntryKind.CORRECTION,
        "is_appeal": entry.kind == ExamScoreEntryKind.APPEAL,
        "is_change": entry.kind != ExamScoreEntryKind.INITIAL,
        "old": entry.old_score if entry.old_score is not None else "—",
        "new": entry.new_score if entry.new_score is not None else "—",
        "question_scores": list(entry.question_scores) if entry.question_scores else [],
        "reason": entry.get_reason_display() if entry.reason else "",
        "note": entry.note,
        "by": entry.entered_by_name,
        "evidence_url": file_url(entry.evidence),
        "sheet_id": str(sheet.id) if sheet is not None else "",
        "sheet_exam_date": sheet.exam_date.strftime("%d.%m.%Y") if sheet is not None and sheet.exam_date else "",
        "sheet_protocol": sheet.protocol_number if sheet is not None else "",
        "sheet_examiner": sheet.examiner_name if sheet is not None else "",
        "sheet_source": sheet.source if sheet is not None else "",
        "sheet_exam_kind": sheet.exam_kind if sheet is not None else ExamScoreSheetKind.WRITTEN,
        "sheet_exam_kind_label": str(sheet.get_exam_kind_display()) if sheet is not None else "",
        "sheet_evidence_url": file_url(sheet.evidence) if sheet is not None else "",
    }


def roster_for_offering(*, offering):
    """Açılışın tələbə siyahısı — bal sahəsi, tarixçə və cəhd güzgüsü ilə.

    Hər sətir::

        {"enrollment", "student", "exam_score", "exam_score_max", "entry_score",
         "total", "letter", "has_score", "is_changed", "question_scores",
         "entries": [...], "attempts": [...]}
    """
    scheme = gradebook.ensure_assessment_scheme(offering=offering)
    enrollments = list(
        offering.enrollments.filter(status=Enrollment.Status.ENROLLED)
        .select_related("student", "student__profile", "offering", "offering__subject")
        .order_by("student__last_name", "student__first_name", "student__username")
    )
    entries_by_enrollment: dict[str, list] = {}
    # Model ``ordering = ["-created_at"]`` → hər tələbənin siyahısı ən yenidən köhnəyə.
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
        latest = history[0] if history else None
        rows.append(
            {
                "enrollment": enrollment,
                "student": enrollment.student,
                "exam_score": result["exam_score"],
                "has_score": result["exam_score"] is not None,
                "is_changed": any(entry.kind != ExamScoreEntryKind.INITIAL for entry in history),
                "question_scores": (
                    list(latest.question_scores) if latest is not None and latest.question_scores else []
                ),
                "exam_score_max": result["exam_score_max"],
                "entry_score": result["entry_score"],
                "total": result["total"],
                "letter": result["letter"],
                "graded": result["graded"],
                "entries": [entry_row(entry) for entry in history],
                "attempts": attempts_by_student.get(enrollment.student_id, []),
            }
        )
    return {"offering": offering, "scheme": scheme, "rows": rows, "exam_score_max": finals.exam_score_max(scheme)}


def _row_matches_search(row, needle: str) -> bool:
    student = row["student"]
    profile = getattr(student, "profile", None)
    haystack = [
        student.get_full_name() or "",
        student.username or "",
        getattr(profile, "fin", "") or "",
        getattr(profile, "institutional_identifier", "") or "",
    ]
    return any(needle in str(value).lower() for value in haystack)


def _row_matches_status(row, status: str) -> bool:
    if status == STATUS_EMPTY:
        return not row["has_score"]
    if status == STATUS_RECORDED:
        return bool(row["has_score"])
    if status == STATUS_CHANGED:
        return bool(row["is_changed"])
    return True


def filter_roster_rows(rows, *, search="", status=STATUS_ALL) -> list:
    """Siyahı sətirlərini axtarış + vəziyyət çipi ilə YADDAŞDA süz (sorğusuz).

    ``search`` — ad / istifadəçi adı / FİN / tələbə № (kiçik hərf, alt-sətir);
    ``status`` — :data:`STATUS_CHOICES`; naməlum → hamısı.
    """
    needle = (search or "").strip().lower()
    status = status if status in STATUS_CHOICES else STATUS_ALL
    return [
        row for row in rows if (not needle or _row_matches_search(row, needle)) and _row_matches_status(row, status)
    ]


def status_counts(rows) -> dict:
    """Çiplərin sayğacları — süzülməmiş siyahı üzərindən."""
    return {
        STATUS_ALL: len(rows),
        STATUS_EMPTY: sum(1 for row in rows if not row["has_score"]),
        STATUS_RECORDED: sum(1 for row in rows if row["has_score"]),
        STATUS_CHANGED: sum(1 for row in rows if row["is_changed"]),
    }


def entries_for_offering(*, offering):
    """Açılış üzrə bütün daxiletmə tarixçəsi (ən yenidən köhnəyə)."""
    return list(
        ExamScoreEntry.objects.filter(enrollment__offering=offering)
        .select_related("enrollment", "enrollment__student", "entered_by", "sheet")
        .order_by("-created_at")
    )


__all__ = [
    "STATUS_ALL",
    "STATUS_CHANGED",
    "STATUS_CHOICES",
    "STATUS_EMPTY",
    "STATUS_RECORDED",
    "entries_for_offering",
    "entry_row",
    "file_url",
    "filter_roster_rows",
    "group_ids_for_instructor",
    "instructors_for_period",
    "offering_label",
    "offerings_for_subject",
    "roster_for_offering",
    "status_counts",
    "subjects_for_period",
]
