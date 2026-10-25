"""Tələbələrin CARİ reyestr qrupunun adı — kənar modulların süzgəcləri üçün (sahib 2026-10-25).

«Dəyərləndirilmiş nəticələr» / «Yoxlanılacaqlar» qrup süzgəci köhnə ``StudentGroup`` (müəllimin kurs qrupu)
modelindən oxuyurdu — reyestr qrupları ilə işləyən müəllimdə siyahı boş qalır, seçilən qrup isə atılırdı.
"""

from __future__ import annotations


def current_group_names(student_ids) -> dict:
    """``{student_id: qrup adı}`` — aktiv akademik qeyddən (BİR sorğu; ən son qeyd üstündür)."""
    from .models import StudentAcademicRecord

    ids = [value for value in set(student_ids) if value]
    if not ids:
        return {}
    rows = (
        StudentAcademicRecord.objects.filter(student_id__in=ids, is_active=True, group__isnull=False)
        .order_by("student_id", "-created_at")
        .values_list("student_id", "group__name")
    )
    result: dict = {}
    for student_id, name in rows:
        if name:
            result.setdefault(student_id, name)
    return result


__all__ = ["current_group_names"]
