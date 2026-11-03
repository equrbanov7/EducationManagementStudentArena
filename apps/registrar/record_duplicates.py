"""Akademik qeyddə eyni fənnin eyni semestrdə BOŞ dublikatı (SYS-1 yoxlaması, 2026-11-03).

Köhnə sistemdə tələbə bəzən eyni fənnin iki jurnalının siyahısında olub (qonaq siyahısı, paralel qrupun jurnalı):
biri imtahan balı ilə, digəri bir neçə gündəlik xana ilə, imtahansız. Köçürmə hər ikisini yazılış kimi saxlayıb —
«Nəticələrim», transkript və işçi baxışında eyni fənn eyni semestrdə iki dəfə görünürdü, biri «nəticə yoxdur» ilə
(prod nüsxəsində ~650 tələbə).

Qayda (DATA ilə, nəticə hesablamadan — sayğac və sətir siyahısı eyni çoxluqdan çıxsın):
eyni ``(fənn, semestr)`` cütündə İMTAHAN və ya 25 % BALI olan yazılış varsa, NƏ imtahanı, NƏ 25 % balı olan
yazılış qeyddə göstərilmir. İkisinin də balı varsa ikisi də qalır (həqiqi ziddiyyət gizlədilmir); heç birinin
yoxdursa hamısı qalır. Yazılış SİLİNMİR — yalnız akademik qeyd oxusu onu ötürür.
"""

from __future__ import annotations

from collections import defaultdict

from .models import FinalGrade, ResitRecord


def empty_duplicate_ids(rows) -> set:
    """``rows`` = ``[(enrollment pk, subject id, period id)]`` → qeyddə göstərilməyəcək boş dublikatların pk-ları.

    Dublikat yoxdursa SORĞU YOXDUR (səhifələrin sorğu büdcəsi dəyişmir); varsa — iki kiçik sorğu.
    """

    groups: dict = defaultdict(list)
    for pk, subject_id, period_id in rows:
        groups[(subject_id, period_id)].append(pk)
    groups = {key: members for key, members in groups.items() if len(members) > 1}
    if not groups:
        return set()
    ids = [pk for members in groups.values() for pk in members]
    scored = set(
        FinalGrade.objects.filter(enrollment_id__in=ids, exam_score__isnull=False).values_list(
            "enrollment_id", flat=True
        )
    )
    scored |= set(
        ResitRecord.objects.filter(enrollment_id__in=ids, resit_score__isnull=False).values_list(
            "enrollment_id", flat=True
        )
    )
    hidden = set()
    for members in groups.values():
        if any(pk in scored for pk in members):
            hidden.update(pk for pk in members if pk not in scored)
    return hidden


__all__ = ["empty_duplicate_ids"]
