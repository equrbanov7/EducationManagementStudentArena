"""«Yük bölgüsü» — «Bütün kafedralar» axtarışı (sahib 2026-11-04).

Sahib: «yük bölgüsü yerində bütün yüklərə baxmaq olsun, indi ancaq bir kafedra mütləq seçilməlidir. ola bilər
ki hansısa fənni ümumi olaraq axtarım». Kafedra seçicisində ``chair=all`` — aktorun BAXIŞ əhatəsindəki
(``workload.view``) bütün kafedraların həmin il üzrə tapşırıq sətirləri bir siyahıda, fənn / qrup / müəllim
axtarışı ilə və səhifəli (``rows`` endpoint-inin ``limit`` / ``offset`` / ``has_more`` müqaviləsi).

QAYDALAR:

* qapı — bölməyə giriş (``workload.manage`` və ya ``workload.distribute``) + ``workload.view``; kafedralar
  ``scoping.manageable_chairs(permission=PERM_VIEW)``-dən (fail-closed, yeni əhatə məntiqi yoxdur);
* siyahı YALNIZ OXUDUR: sətir redaktəsi / bölgü həmişə sətrin ÖZ kafedrasının səhifəsində gedir. Sətirdə
  ``can_edit`` (kafedra bölmənin idarə/bölgü əhatəsindədir) və ``edit_url`` (həmin kafedra + il + sətir fokusu)
  gəlir; əhatədən kənar kafedranın sətri yalnız baxış üçündür. Yazı endpoint-ləri öz yoxlamalarını dəyişmir;
* sorğu sayı sətir sayından asılı deyil: say + dilim (kafedra/fakültə ``select_related``) + qruplar və
  təyinatlar prefetch + balans BİR GROUP BY + düzəliş hədəfləri BİR sorğu + iki əhatə siyahısı.

Kafedraya bağlı süzgəclər (sağ panelin müəllimi, bölgü vəziyyəti) bu rejimdə tətbiq olunmur — onlar tapşırığın
balansına bağlıdır; semestr, fəaliyyət növü və axtarış işləyir.
"""

from __future__ import annotations

from django.db.models import Q

from core.constants import OrgUnitType

from ..constants import PERM_DISTRIBUTE, PERM_MANAGE, PERM_VIEW, AmendmentTarget, TaskStatus
from ..models import TeachingTask, TeachingTaskRow, WorkloadAmendment
from .queries import MAX_PAGE_LIMIT, _serialize, row_search_q
from .row_edit import distribution_edit_url
from .row_filters import activity_q
from .scoping import WorkloadDenied, manageable_chairs

#: Kafedra seçicisinin «Bütün kafedralar» dəyəri (``rows?chair=all``).
ALL_CHAIRS = "all"


def can_search_all_chairs(actor) -> bool:
    return actor.has(PERM_VIEW) and (actor.has(PERM_MANAGE) or actor.has(PERM_DISTRIBUTE))


def searchable_chairs(actor):
    """Baxış əhatəsindəki kafedralar (yalnız ``chair`` tipi — bölmənin seçicisi ilə eyni)."""
    if not can_search_all_chairs(actor):
        return manageable_chairs(actor, permission=PERM_VIEW).none()
    return manageable_chairs(actor, permission=PERM_VIEW).filter(unit_type=OrgUnitType.CHAIR)


def editable_chair_ids(actor) -> set[str]:
    """Bölmənin kafedra seçicisi ilə EYNİ siyahı (``public.build_distribution_context``: idarə açarı varsa onun,
    yoxsa bölgü açarının əhatəsi) — «Kafedrada redaktə et» keçidi yalnız bunlara."""
    permission = PERM_MANAGE if actor.has(PERM_MANAGE) else PERM_DISTRIBUTE
    return {str(pk) for pk in manageable_chairs(actor, permission=permission).values_list("pk", flat=True)}


def _amend_targets(tasks) -> set:
    """Açıq düzəliş hədəfləri — dilimdəki ``amended`` tapşırıqlar üzrə BİR sorğu (``tasks._amendment_target_row_ids``)."""
    condition = Q()
    for task in {task.pk: task for task in tasks if task.status == TaskStatus.AMENDED}.values():
        part = Q(task_id=task.pk)
        if task.distributed_at:
            part &= Q(created_at__gte=task.distributed_at)
        condition |= part
    if not condition:
        return set()
    return set(
        WorkloadAmendment.objects.filter(condition, target_kind=AmendmentTarget.ROW).values_list("target_id", flat=True)
    )


def all_chairs_queryset(actor, *, academic_year: str = "", season: str = "", search: str = "", activity: str = ""):
    tasks = TeachingTask.objects.filter(
        organization=actor.organization,
        chair__in=searchable_chairs(actor).order_by().values("pk"),
    )
    if academic_year:
        tasks = tasks.filter(academic_year=academic_year)
    queryset = TeachingTaskRow.objects.filter(task__in=tasks.values("pk"))
    if season:
        queryset = queryset.filter(season=season)
    condition = activity_q(activity)
    if condition is not None:
        queryset = queryset.filter(condition)
    search_q = row_search_q(search)
    if search_q is not None:
        queryset = queryset.filter(search_q).distinct()
    return queryset


def all_chairs_rows_page(
    actor,
    *,
    academic_year: str = "",
    season: str = "",
    search: str = "",
    activity: str = "",
    offset: int = 0,
    limit: int = 0,
) -> dict:
    """Bütün (baxış əhatəsindəki) kafedraların sətirləri — ``rows_page`` ilə eyni forma + kafedra sahələri."""
    if not can_search_all_chairs(actor):
        raise WorkloadDenied("workload.view_denied", "Bu tapşırığa baxış səlahiyyətiniz yoxdur.")
    queryset = all_chairs_queryset(actor, academic_year=academic_year, season=season, search=search, activity=activity)
    total = queryset.count()
    offset = max(int(offset or 0), 0)
    limit = min(max(int(limit or 0), 0), MAX_PAGE_LIMIT)
    rows = []
    if limit:
        rows = list(
            queryset.select_related(
                "subject", "specialty", "period", "intensive_offering", "task", "task__chair", "task__chair__parent"
            )
            .prefetch_related("groups", "assignments__teacher")
            .order_by("task__chair__name", "season", "order", "created_at", "pk")[offset : offset + limit]
        )
    payload, _rows, _balance = _serialize(None, rows, amend_targets=_amend_targets(row.task for row in rows))
    editable = editable_chair_ids(actor) if rows else set()
    status_labels = dict(TaskStatus.choices)
    for item, row in zip(payload, rows):
        task = row.task
        chair = task.chair
        chair_id = str(task.chair_id)
        can_edit = chair_id in editable
        item.update(
            {
                "task_id": str(task.pk),
                "task_status": task.status,
                "task_status_label": str(status_labels.get(task.status, task.status)),
                "chair_id": chair_id,
                "chair_name": chair.name,
                "faculty_name": chair.parent.name if chair.parent_id else "",
                "can_edit": can_edit,
                "edit_url": (
                    distribution_edit_url(chair_id=chair_id, academic_year=task.academic_year, row_id=row.pk)
                    if can_edit
                    else ""
                ),
            }
        )
    next_offset = offset + len(rows)
    return {"rows": payload, "total": total, "next_offset": next_offset, "has_more": next_offset < total}


__all__ = [
    "ALL_CHAIRS",
    "all_chairs_queryset",
    "all_chairs_rows_page",
    "can_search_all_chairs",
    "editable_chair_ids",
    "searchable_chairs",
]
