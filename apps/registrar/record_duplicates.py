"""Akademik qeyddə eyni fənnin eyni semestrdə BOŞ dublikatı (SYS-1 yoxlaması, 2026-11-03).

Köhnə sistemdə tələbə bəzən eyni fənnin iki jurnalının siyahısında olub (qonaq siyahısı, paralel qrupun jurnalı):
biri imtahan balı ilə, digəri bir neçə gündəlik xana ilə, imtahansız. Köçürmə hər ikisini yazılış kimi saxlayıb —
«Nəticələrim», transkript və işçi baxışında eyni fənn eyni semestrdə iki dəfə görünürdü, biri «nəticə yoxdur» ilə
(prod nüsxəsində ~650 tələbə).

Qayda (DATA ilə, nəticə hesablamadan — sayğac və sətir siyahısı eyni çoxluqdan çıxsın):
eyni ``(fənn, semestr)`` cütündə İMTAHAN və ya 25 % BALI olan yazılış varsa, NƏ imtahanı, NƏ 25 % balı olan
yazılış qeyddə göstərilmir. İkisinin də balı varsa ikisi də qalır (həqiqi ziddiyyət gizlədilmir). Heç birinin
balı yoxdursa: BİTMİŞ semestrdə daha çox komponent balı olan BİR yazılış qalır (eyni fənn iki dəfə «köhnə sistemdə
nəticə yoxdur» göstərilməsin), cari / gələcək semestrdə hamısı qalır (müəllim hansında yazırsa görünsün).
Yazılış SİLİNMİR — yalnız akademik qeyd oxusu onu ötürür.
"""

from __future__ import annotations

from collections import defaultdict

from django.db.models import Count

from .models import ComponentScore, FinalGrade, ResitRecord


def empty_duplicate_ids(rows) -> set:
    """``rows`` = ``[(enrollment pk, subject id, period id, semestr bitib)]`` → göstərilməyəcək dublikatların pk-ları.

    Dublikat yoxdursa SORĞU YOXDUR (səhifələrin sorğu büdcəsi dəyişmir); varsa — iki-üç kiçik sorğu.
    """

    groups: dict = defaultdict(list)
    closed: set = set()
    for pk, subject_id, period_id, ended in rows:
        groups[(subject_id, period_id)].append(pk)
        if ended:
            closed.add((subject_id, period_id))
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
    unscored = []
    for key, members in groups.items():
        if any(pk in scored for pk in members):
            hidden.update(pk for pk in members if pk not in scored)
        elif key in closed:
            unscored.append(members)
    if unscored:
        weight = dict(
            ComponentScore.objects.filter(enrollment_id__in=[pk for members in unscored for pk in members])
            .values("enrollment_id")
            .annotate(n=Count("id"))
            .values_list("enrollment_id", "n")
        )
        for members in unscored:
            keep = max(members, key=lambda pk: (weight.get(pk, 0), str(pk)))
            hidden.update(pk for pk in members if pk != keep)
    return hidden


__all__ = ["empty_duplicate_ids"]
