"""«Yük bölgüsü» sətir siyahısının SERVER tərəfi süzgəcləri: bölgü vəziyyəti + fəaliyyət növü (2026-10-25).

Süzgəc səhifələmədən ƏVVƏL tətbiq olunur (``total`` / ``has_more`` süzgəcə uyğundur). Vəziyyət sətrin balansından
(``assignments.balance_for_rows``) çıxarılır — tapşırığın sətirləri BİR sorğu, bölünmüş saatlar BİR GROUP BY ilə
oxunur (sətir sayı ilə sorğu sayı böyümür); nəticə ``pk__in`` ilə əsas sorğuya qoşulur.

Vəziyyətlər (``status``):

* ``vacant``     — müəllimi təyin olunmayan saat var: ya «Vakant» təyinat, ya da hələ heç kimə bölünməyən qalıq;
* ``full``       — bütün saatlar real müəllimlərə bölünüb (vakant təyinat da yoxdur);
* ``partial``    — qismən bölünüb: bölünmüş saat da var, qalıq da;
* ``unassigned`` — heç nə bölünməyib;
* ``hourly``     — saathesabı fondundan bölgüsü olan;
* ``intensive``  — «İntensiv kurs» sətri.

``activity`` (mühazirə / seminar / lab …) verilsə, balans vəziyyətləri YALNIZ həmin fəaliyyət üzrə hesablanır
(«mühazirəsi vakant qalanlar»); vəziyyətsiz isə sətirdə həmin fəaliyyətin saatı olması kifayətdir.
Naməlum dəyər (köhnəlmiş URL) süzgəc sayılmır.
"""

from __future__ import annotations

from django.db.models import Q

from ..constants import ACTIVITY_TOTAL_FIELD, TEACHING_ACTIVITIES, RowKind
from ..models import TeacherAssignment, TeachingTaskRow
from .assignments import balance_for_rows

STATUS_VACANT = "vacant"
STATUS_FULL = "full"
STATUS_PARTIAL = "partial"
STATUS_UNASSIGNED = "unassigned"
STATUS_HOURLY = "hourly"
STATUS_INTENSIVE = "intensive"

ROW_STATUSES = (STATUS_VACANT, STATUS_FULL, STATUS_PARTIAL, STATUS_UNASSIGNED, STATUS_HOURLY, STATUS_INTENSIVE)


def _activity_key(activity: str) -> str:
    return activity if activity in {str(key) for key in ACTIVITY_TOTAL_FIELD} else ""


def _assignments(task, activity: str):
    queryset = TeacherAssignment.objects.filter(row__task=task)
    return queryset.filter(activity=activity) if activity else queryset


def _balance_ids(task, status: str, activity: str) -> set:
    """``vacant`` / ``full`` / ``partial`` / ``unassigned`` — sətir balansından."""
    rows = list(TeachingTaskRow.objects.filter(task=task))
    balance = balance_for_rows(rows)
    vacant_assigned = set(_assignments(task, activity).filter(teacher__isnull=True).values_list("row_id", flat=True))
    teaching = {str(key) for key in TEACHING_ACTIVITIES}
    ids = set()
    for row in rows:
        info = (balance.get(str(row.pk)) or {}).get("activities") or {}
        # Fəaliyyət seçilməyibsə kartın yaşıl çərçivəsi ilə eyni qayda: yalnız dərs növləri (mühazirə/seminar/lab).
        acts = [v for k, v in info.items() if (k == activity if activity else k in teaching)]
        has_vacant = row.pk in vacant_assigned
        remaining = any(item["remaining"] > 0 for item in acts)
        assigned = any(item["assigned"] > 0 for item in acts)
        complete = bool(acts) and all(item["is_complete"] for item in acts)
        if status == STATUS_VACANT:
            hit = remaining or has_vacant
        elif not acts:
            hit = False
        elif status == STATUS_FULL:
            hit = complete and not has_vacant
        elif status == STATUS_PARTIAL:
            hit = remaining and assigned
        else:  # STATUS_UNASSIGNED
            hit = not assigned
        if hit:
            ids.add(row.pk)
    return ids


def status_q(task, status: str, activity: str = "") -> Q | None:
    """``status`` üçün sətir ``Q``-su; naməlum/boş → ``None`` (süzgəc yoxdur)."""
    activity = _activity_key(activity)
    if status == STATUS_INTENSIVE:
        return Q(row_kind=RowKind.INTENSIVE)
    if status == STATUS_HOURLY:
        return Q(pk__in=_assignments(task, activity).filter(is_hourly_paid=True).values("row_id"))
    if status in (STATUS_VACANT, STATUS_FULL, STATUS_PARTIAL, STATUS_UNASSIGNED):
        return Q(pk__in=_balance_ids(task, status, activity))
    return None


def activity_q(activity: str) -> Q | None:
    """Sətirdə həmin fəaliyyətin saatı var."""
    activity = _activity_key(activity)
    if not activity:
        return None
    field = next(field for key, field in ACTIVITY_TOTAL_FIELD.items() if str(key) == activity)
    return Q(**{f"{field}__gt": 0})


def apply_row_filters(queryset, task, *, status: str = "", activity: str = ""):
    """``status`` / ``activity`` süzgəclərini sətir sorğusuna qoşur (hər ikisi boşdursa — dəyişməz)."""
    for condition in (status_q(task, status, activity) if status else None, activity_q(activity)):
        if condition is not None:
            queryset = queryset.filter(condition)
    return queryset


__all__ = ["ROW_STATUSES", "activity_q", "apply_row_filters", "status_q"]
