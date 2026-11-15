"""Sillabus redaktəsi üçün «jurnalın cari müəllimi» (sahib 2026-11-15: «müəllim sillabusu redaktə edə bilmir»).

``apps.syllabus`` registrar-ı idxal etmir; bu resolver ``AppConfig.ready``-də
``apps.syllabus.public.register_journal_teacher_resolver`` ilə qeyd olunur. Açılışın müəllimi (``instructor``)
sillabus tərəfində onsuz da sayılır; burada jurnalı YAZAN digər müəllimlər əlavə olunur — jurnal qapılarının
özü ilə eyni mənbələr:

* bölünmüş jurnalın aktiv pay sahibi (``journal_shares.has_writable_share`` — canlı ``grade.input`` ilə);
* dərs yükü bölgüsü bu jurnala düşən müəllim (``journal_teaching_heading.current_plan`` — «Vakant» açılışın
  faktiki müəllimi də daxil).
"""

from __future__ import annotations


def is_current_journal_teacher(user, offering) -> bool:
    if not getattr(user, "is_authenticated", False) or offering is None:
        return False
    from .journal_shares import has_writable_share

    if has_writable_share(user, offering):
        return True
    from .journal_teaching_heading import current_plan

    return bool(current_plan(offering, user))


__all__ = ["is_current_journal_teacher"]
