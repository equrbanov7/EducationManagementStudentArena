"""Bölünmüş saatın «döşəməsi» — cəm azaldılanda HANSI bölgünün necə dəyişəcəyini adı ilə deyir (sahib 2026-11-11).

Sahib: «Tədqiqat analitikası 45 saatlıq fəndir — 30 saat mühazirə, 15 saat seminar. Bunu fixləyə bilmir». Kafedra
sətrin mühazirəsini 45 → 30 endirəndə server yalnız «Əvvəlcə bölgünü azaldın» deyirdi — hansı bölgünü, neçəyə,
harada — deyilmirdi. Bu modul:

* :func:`shrink_plan` — ``row_edit._shrink_activity`` ilə EYNİ sıra (ən son təyinatdan başlayaraq): hər bölgü
  üçün ``(müəllim, köhnə saat, yeni saat)``; 0 — bölgü silinəcək;
* :func:`below_assigned_message` — 409 ``workload.total_below_assigned`` mesajı: fəaliyyət, yeni cəm, bölünmüş
  saat, bölgülər və avtomatik azaltmanın nəticəsi; başqa bölgünü azaltmaq istəyənə yol göstərir.

Saf oxu köməkçisidir — yazı yoxdur.
"""

from __future__ import annotations

from django.utils.translation import pgettext

from ..constants import Activity
from ..models import TeacherAssignment

_LABELS = {str(value): label for value, label in Activity.choices}


def _name(assignment) -> str:
    teacher = assignment.teacher
    if teacher is None:
        return pgettext("workload", "Vakant")
    return teacher.get_full_name() or teacher.username


def shrink_plan(row_id, activity: str, total: int) -> list[tuple[str, int, int]]:
    """``[(müəllim, köhnə saat, yeni saat)]`` — cəmə sığmaq üçün ən son bölgüdən başlayaraq azaldılanlar."""
    assignments = list(
        TeacherAssignment.objects.filter(row_id=row_id, activity=activity)
        .select_related("teacher")
        .order_by("-created_at")
    )
    excess = sum(int(item.hours or 0) for item in assignments) - int(total)
    plan = []
    for assignment in assignments:
        if excess <= 0:
            break
        hours = int(assignment.hours or 0)
        cut = min(hours, excess)
        plan.append((_name(assignment), hours, hours - cut))
        excess -= cut
    return plan


def below_assigned_message(row_id, activity: str, *, assigned: int, total: int) -> str:
    """409 mesajı: nə bölünüb, nəyə dəyişəcək, başqa yol nədir."""
    current = TeacherAssignment.objects.filter(row_id=row_id, activity=activity).select_related("teacher")
    listed = ", ".join(f"{_name(item)} {int(item.hours or 0)} s" for item in current.order_by("created_at"))
    changes = ", ".join(
        (
            pgettext("workload", "%(teacher)s %(old)s → %(new)s s") % {"teacher": name, "old": old, "new": new}
            if new
            else pgettext("workload", "%(teacher)s %(old)s s silinəcək") % {"teacher": name, "old": old}
        )
        for name, old, new in shrink_plan(row_id, activity, total)
    )
    label = _LABELS.get(str(activity))
    return pgettext(
        "workload",
        "«%(activity)s» cəmi %(total)s saata endirilir, amma bu fəaliyyətdə artıq %(assigned)s saat bölünüb "
        "(%(listed)s). Bölgü avtomatik azaldılsa: %(changes)s. Başqa bölgünü azaltmaq istəyirsinizsə, əvvəlcə kartda "
        "onun ✎ düyməsi ilə saatını dəyişin, sonra sətri yenidən saxlayın.",
    ) % {
        "activity": str(label) if label is not None else activity,
        "total": total,
        "assigned": assigned,
        "listed": listed,
        "changes": changes,
    }


__all__ = ["below_assigned_message", "shrink_plan"]
