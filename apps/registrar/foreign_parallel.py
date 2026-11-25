"""Əcnəbi qrupları — müəllim EYNİ saatda bir neçə əcnəbi qrupunda dərs keçə bilir (sahib 2026-11-25).

Sahib: «01–06 və digər əcnəbi qrupu olanlarda müəllim eyni saatda 2 ya da daha çox qrupa eyni vaxtda dərs saatını
aktivləşdirə bilsin». Əcnəbi tələbələr bir sinifdə birlikdə oturur — axın (patok) kimi, amma fənn eyni olmaya da bilər.

Qayda cədvəl toqquşmasındadır (``schedule.find_conflict``, ``schedule_conflicts.detect``): hər iki slotun QRUPU
əcnəbi qrupudursa (``organizations.group_kind``: açıq «Qrup növü» və ya ad qaydası) və qruplar FƏRQLİDİRSƏ, müəllim
və otaq toqquşması sayılmır. Eyni qrupun iki dərsi yenə toqquşmadır; adi qrupla əcnəbi qrupu yenə toqquşur.
Cədvəldə slot dayananda dərs «Aktivləşdir» / «Yeni dərs» ilə hər qrupun jurnalında ayrıca açılır.
"""

from __future__ import annotations


def foreign_parallel(organization, group_id, slot) -> bool:
    """``group_id`` ilə ``slot``-un qrupu fərqli əcnəbi qruplarıdırmı (qrup id-ləri təşkilat obyektində yaddaşda)."""
    other = getattr(getattr(slot, "offering", None), "group_id", None)
    if not group_id or not other or str(group_id) == str(other) or organization is None:
        return False
    from apps.organizations.public import foreign_group_ids

    ids = foreign_group_ids(organization)
    return str(group_id) in ids and str(other) in ids


__all__ = ["foreign_parallel"]
