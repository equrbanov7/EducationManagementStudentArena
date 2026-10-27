"""İmtahan nəticəsi jurnala düşəcəkmi — bloklamayan xəbərdarlıq (sahib 2026-10-26).

Sahib: «İmtahan yaradarkən fənn seçirəm — tələbənin imtahan nəticəsi kimi sistemə düşəcəkmi? Bu hissə doğru
olsun. … Qrupa əlavə olunanda ona aid fənn çıxmasa ya da tələbə onunla bağlı xəbərdarlıq ala bilərik.»

Yekun (final) və midterm imtahanının balı körpü ilə tələbənin fənn üzrə JURNAL qeydiyyatına yazılır
(``journal_sync`` / ``midterm_journal_sync``). Qeydiyyat yoxdursa bal heç yerə düşmür, iki jurnal varsa körpü
birini seçir (``exam_bridge.pick_enrollment``: bağlı jurnal → öz qrup → ən son). Bu modul müəllimə həmin
halları ƏVVƏLCƏDƏN göstərir — yaratma təsdiqində (``assigned_student_count``), saxlamada və aktivləşdirmədə
(flash). Heç vaxt bloklamır; xəta olarsa sükutla boş siyahı (loglanır).
"""

from __future__ import annotations

import logging

from django.utils.translation import pgettext

logger = logging.getLogger(__name__)

#: Balı jurnala yazılan kateqoriyalar (``journal_sync`` — final; ``midterm_journal_sync`` — midterm).
JOURNAL_CATEGORIES = frozenset({"final", "midterm"})


def writes_to_journal(category) -> bool:
    return str(category or "").strip() in JOURNAL_CATEGORIES


def coverage_counts(organization, subject_id, student_ids, *, offering_ids=()) -> dict:
    """→ ``{"no_journal": n, "multiple_journals": m}`` (registrar ``enrollment_coverage``, cari dövr).

    ``offering_ids`` — imtahanın bağlı jurnalları (dublikat fənn kartının açılışı da, sahib 2026-10-27)."""
    from apps.registrar.public import exam_journal_link

    coverage = exam_journal_link.enrollment_coverage(
        organization, subject_id, student_ids, offering_ids=list(offering_ids or ())
    )
    return {"no_journal": len(coverage["none"]), "multiple_journals": len(coverage["multiple"])}


def coverage_warnings(counts, *, links_missing=False) -> list:
    """Sayları müəllimə göstəriləcək (tərcümə olunmuş) xəbərdarlıq mətnlərinə çevir."""
    warnings = []
    if links_missing:
        warnings.append(
            pgettext(
                "exams.journal_coverage",
                "Seçilmiş qruplar üçün bu fənnin cari semestr jurnalı tapılmadı — nəticə jurnala düşməyə bilər. "
                "Fənni və qrupları yoxlayın.",
            )
        )
    none = int(counts.get("no_journal") or 0)
    if none:
        warnings.append(
            pgettext(
                "exams.journal_coverage",
                "%(count)s tələbənin bu fənn üzrə cari semestr jurnalı yoxdur — nəticə jurnala düşməyəcək.",
            )
            % {"count": none}
        )
    multiple = int(counts.get("multiple_journals") or 0)
    if multiple:
        warnings.append(
            pgettext(
                "exams.journal_coverage",
                "%(count)s tələbə bu fəndən birdən çox jurnaldadır — nəticə imtahanın qrupunun jurnalına "
                "(yoxdursa tələbənin öz qrupunun jurnalına) yazılacaq.",
            )
            % {"count": multiple}
        )
    return warnings


def confirm_payload(organization, subject_id, student_ids, *, category, unit_ids=()) -> dict:
    """Yaratma təsdiqi (``assigned_student_count``) üçün: ``no_journal``, ``multiple_journals``, ``warnings``."""
    payload = {"no_journal": 0, "multiple_journals": 0, "warnings": []}
    if not subject_id or not writes_to_journal(category):
        return payload
    try:
        links_missing, link_ids = False, []
        if unit_ids:
            from apps.registrar.public import exam_journal_link

            link_ids = exam_journal_link.link_offering_ids(
                organization, subject_id=subject_id, group_ids=list(unit_ids)
            )
            links_missing = not link_ids
        counts = coverage_counts(organization, subject_id, student_ids, offering_ids=link_ids)
    except Exception:  # noqa: BLE001 — xəbərdarlıq köməkçidir, təsdiqi sındırmır
        logger.exception("exam_journal_coverage: confirm coverage failed")
        return payload
    payload.update(counts)
    payload["warnings"] = coverage_warnings(counts, links_missing=links_missing)
    return payload


def _exam_writes_to_journal(exam) -> bool:
    from apps.exams.services import midterm_journal_sync
    from apps.exams.services.journal_sync import final_grade_skip_reason

    return final_grade_skip_reason(exam) is None or midterm_journal_sync.is_auto_midterm_exam(exam)


def exam_student_ids(exam) -> set:
    """İmtahana təyin olunmuş tələbələr: fərdi + köhnə kohort + reyestr qrupları (alt qrup + fənn jurnalı) − xaric."""
    from apps.exams.domain.unit_assignment import unit_assigned_student_ids

    ids = set(exam.allowed_users.values_list("id", flat=True))
    ids.update(sid for sid in exam.allowed_groups.values_list("students__id", flat=True) if sid)
    ids |= unit_assigned_student_ids(exam)
    ids.difference_update(exam.excluded_users.values_list("id", flat=True))
    return ids


def exam_coverage_warnings(exam) -> list:
    """Saxlanmış imtahan üçün xəbərdarlıqlar (flash): bağlantı boşdur / jurnalsız / iki jurnallı tələbələr."""
    if not getattr(exam, "pk", None) or not getattr(exam, "subject_id", None) or exam.organization_id is None:
        return []
    try:
        if not _exam_writes_to_journal(exam):
            return []
        from apps.exams.services.exam_journal_link import exam_group_ids, linked_offering_ids

        link_ids = linked_offering_ids(exam)
        links_missing = bool(exam_group_ids(exam)) and not link_ids
        student_ids = exam_student_ids(exam)
        counts = (
            coverage_counts(exam.organization, exam.subject_id, student_ids, offering_ids=link_ids)
            if student_ids
            else {}
        )
    except Exception:  # noqa: BLE001 — saxlamanı / aktivləşdirməni sındırmır
        logger.exception("exam_journal_coverage: coverage failed for exam %s", getattr(exam, "pk", "?"))
        return []
    return coverage_warnings(counts, links_missing=links_missing)


__all__ = [
    "JOURNAL_CATEGORIES",
    "confirm_payload",
    "coverage_counts",
    "coverage_warnings",
    "exam_coverage_warnings",
    "exam_student_ids",
    "writes_to_journal",
]
