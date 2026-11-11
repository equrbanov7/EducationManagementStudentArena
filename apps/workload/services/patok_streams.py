"""Mühazirə axınları (patok) — «bir fənn = bir kart» seçicisinin YAZI yolu (sahib 2026-11-09).

Sahib: «mühazirə → hansı qruplar birlikdə oxuyur … çox rahat, sadə seçmək olsun» + «necə patok ayırır onu da başa
düşmədim». Qayda dəyişmir, yalnız AÇIQ seçilir (:mod:`.patok`): bir axının mühazirəsi yükə BİR dəfə düşür —
axının APARICI sətrində (``lecture_total > 0``, mühazirə bölgüsü), qalan TƏRƏFDAŞ sətirlərdə ``lecture_total = 0``
və ``patok_lead`` → aparıcı; hər qrupun jurnalında mühazirə ``lecture_plan`` saatı ilə görünür.

:func:`apply_streams` ailənin (eyni fənn + mövsüm + semestr) sətirlərini axınlara bölür:

* hər axında aparıcı seçilir — cari aparıcı / mühazirəçisi olan sətir, yoxsa ilk sətir; aparıcı olan sətrin
  ``lecture_total``-ı planına (``lecture_plan × birləşmə sayı``) qaytarılır, bağı açılır;
* tərəfdaşlar: ``lecture_total = 0`` (mühazirə bölgüsü yeni cəmə sığdırılır — :func:`.row_edit.save_row_amended`
  ``shrink``), ``patok_lead`` = aparıcı; ``lecture_plan`` boşdursa əvvəl qrupun saatı (``total ÷ birləşmə``) yazılır;
* axının mühazirəçisi (``teacher_id``) verilibsə aparıcının mühazirə bölgüsü ONA yazılır (tam saat); ``"vacant"`` —
  bölgü silinir (saat vakant qalır); açar yoxdursa toxunulmur;
* bir sətir = bir vahiddir: çox qruplu sətrin («536 İ / 536 ML / 536 MU») qrupları ayrılmır — kart bunu izah edir,
  bölmək üçün sətir redaktə olunur (növbəti PR: «Qruplara böl»).

Hər yazı mövcud servislərlə gedir (icazə, düzəliş axını, audit, DB trigger-i); açılış sinxronu sonda BİR dəfə
(ailənin sətirləri eyni fənn — ``sync_row_offerings`` qardaş sətirləri birlikdə yazır). Müəllim yükü yalnız axın
dəyişəndə dəyişir — məhz sahibin istədiyi «bir dəfə sayılma».
"""

from __future__ import annotations

from django.db import transaction
from django.utils.translation import pgettext

from core.audit import log_action
from core.constants import AuditAction
from core.http_ids import parse_uuid

from ..constants import Activity, RowKind
from ..models import TeacherAssignment, TeachingTaskRow
from .offering_rules import plan_reached_chair
from .offering_sync import compact, run_safely, sync_row_offerings
from .row_edit import assign_amended, save_row_amended, unassign_amended
from .scoping import WorkloadDenied, ensure_can_distribute

#: Rədd kodları (HTTP 400 — giriş xətası).
STREAM_ERRORS = {
    "workload.stream_rows_foreign": "Axın sətirləri bu tapşırığa aid deyil.",
    "workload.stream_row_repeated": "Bir sətir yalnız bir axında ola bilər.",
    "workload.stream_rows_mismatch": "Axın sətirləri eyni fənn, mövsüm və semestrdə olmalıdır.",
    "workload.stream_no_lecture": "Mühazirə saatı olmayan sətir axına salına bilmir.",
    "workload.stream_teacher_invalid": "Axının mühazirəçisi düzgün göstərilməyib.",
    "workload.stream_plan_mismatch": "Bir axındakı qrupların mühazirə saatı eyni olmalıdır.",
}
VACANT = "vacant"


def _deny(code: str) -> WorkloadDenied:
    return WorkloadDenied(code, STREAM_ERRORS[code])


def _family(row) -> tuple:
    subject = str(row.subject_id) if row.subject_id else (row.subject_text or "").strip().casefold()
    return (row.task_id, subject, row.season, row.period_id)


def _parse_streams(task, streams) -> list[dict]:
    """``[{"row_ids": [...], "teacher_id": ...}]`` → ``[{"rows": [TeachingTaskRow …], "teacher": …}]``."""
    if not isinstance(streams, list) or not streams:
        raise _deny("workload.stream_rows_foreign")
    wanted: list[list] = []
    seen: set = set()
    for item in streams:
        ids = [parse_uuid(value) for value in ((item or {}).get("row_ids") or []) if value]
        if not ids or any(pk is None for pk in ids):
            raise _deny("workload.stream_rows_foreign")
        for pk in ids:
            if pk in seen:
                raise _deny("workload.stream_row_repeated")
            seen.add(pk)
        wanted.append(ids)
    rows = {
        row.pk: row
        for row in TeachingTaskRow.objects.filter(task=task, pk__in=seen, row_kind=RowKind.TEACHING)
        .select_related("task", "subject")
        .prefetch_related("groups", "assignments")
    }
    if len(rows) != len(seen):
        raise _deny("workload.stream_rows_foreign")
    families = {_family(row) for row in rows.values()}
    if len(families) != 1:
        raise _deny("workload.stream_rows_mismatch")
    result = []
    for item, ids in zip(streams, wanted):
        stream_rows = [rows[pk] for pk in ids]
        for row in stream_rows:
            if int(row.lecture_plan or 0) <= 0 and int(row.lecture_total or 0) <= 0:
                raise _deny("workload.stream_no_lecture")
        teacher = (item or {}).get("teacher_id")
        if teacher not in (None, "", VACANT):
            teacher = parse_uuid(teacher) if not str(teacher).isdigit() else int(teacher)
            if teacher is None:
                raise _deny("workload.stream_teacher_invalid")
        result.append({"rows": stream_rows, "teacher": teacher if teacher not in ("",) else None})
    return result


def _lecturers(row) -> list:
    return [a for a in row.assignments.all() if a.activity == Activity.LECTURE and a.hours > 0]


def _pick_lead(rows, teacher):
    """Aparıcı: mühazirəçisi ``teacher`` olan → cari aparıcı (``lecture_total > 0`` + mühazirəçi) → saatı olan → ilk."""
    if teacher not in (None, VACANT):
        for row in rows:
            if any(a.teacher_id == teacher for a in _lecturers(row)):
                return row
    for row in rows:
        if int(row.lecture_total or 0) > 0 and any(a.teacher_id for a in _lecturers(row)):
            return row
    for row in rows:
        if int(row.lecture_total or 0) > 0:
            return row
    return rows[0]


def _per_group_plan(row) -> int:
    plan = int(row.lecture_plan or 0)
    if plan:
        return plan
    return int(row.lecture_total or 0) // max(int(row.union_count or 1), 1)


def _row_label(row) -> str:
    return " · ".join(group.name for group in row.groups.all()) or row.groups_text or row.subject_label


def _ensure_same_plan(stream) -> None:
    """Sahib 2026-11-11 («Tədqiqat analitikası»): YENİ birləşən axında qrupların mühazirə saatı eyni olmalıdır.

    Əks halda aparıcının saatı (məs. 45) yükə düşür, tərəfdaşın jurnalında isə öz planı (30) görünür — axın
    «birləşir», amma saatlar uyğunsuz qalır. Artıq mövcud (dəyişməyən) axın yenidən saxlananda yoxlanmır.
    """
    lead, rows = stream["lead"], stream["rows"]
    joining = [row for row in rows if row.pk != lead.pk and row.patok_lead_id != lead.pk]
    if lead.patok_lead_id or int(lead.lecture_total or 0) <= 0:
        joining.append(lead)
    if not joining or len({_per_group_plan(row) for row in rows}) <= 1:
        return
    hours = ", ".join(f"{_row_label(row)} — {_per_group_plan(row)} s" for row in rows)
    raise WorkloadDenied(
        "workload.stream_plan_mismatch",
        pgettext(
            "workload",
            "Bir axında qrupların mühazirə saatı eyni olmalıdır, burada fərqlidir: %(hours)s. Əvvəlcə «Tapşırıq "
            "sətirləri»ndə hər sətri «Redaktə» ilə düzəldin (məs. 45 saatlıq fənn: «Mühazirə» 30, «Seminar» 15), "
            "sonra axınları birləşdirin.",
        )
        % {"hours": hours},
    )


def _save(task, actor, row, data, amend, request, *, shrink=False):
    return save_row_amended(
        task=task, actor=actor, data=data, row=row, amend=amend, shrink=shrink, request=request, sync_offerings=False
    )


def _set_lecturer(task, actor, lead, teacher, amend, request) -> str:
    """Aparıcının mühazirə bölgüsü: ``vacant`` → silinir; müəllim → tam saat ona (fərqlidirsə yenidən yazılır)."""
    lead.refresh_from_db(fields=["lecture_total"])
    current = list(TeacherAssignment.objects.filter(row=lead, activity=Activity.LECTURE).order_by("created_at"))
    total = int(lead.lecture_total or 0)
    if teacher == VACANT:
        for item in current:
            unassign_amended(assignment=item, actor=actor, amend=amend, request=request, sync_offerings=False)
        return "cleared" if current else "kept"
    if len(current) == 1 and current[0].teacher_id == teacher and int(current[0].hours) == total:
        return "kept"
    for item in current:
        unassign_amended(assignment=item, actor=actor, amend=amend, request=request, sync_offerings=False)
    if total <= 0:
        return "cleared"
    assign_amended(
        row=lead,
        actor=actor,
        amend=amend,
        activity=str(Activity.LECTURE),
        teacher_id=teacher,
        hours=total,
        request=request,
        sync_offerings=False,
    )
    return "set"


@transaction.atomic
def apply_streams(*, task, actor, streams, amend=None, request=None) -> dict:
    """Ailənin sətirlərini mühazirə axınlarına böl (bax modul başlığı). Qaytarır: yazı xülasəsi (saylar + id-lər)."""
    ensure_can_distribute(actor, task.chair_id)
    parsed = _parse_streams(task, streams)
    leads: dict = {}
    for stream in parsed:
        stream["lead"] = _pick_lead(stream["rows"], stream["teacher"])
        _ensure_same_plan(stream)
        leads[stream["lead"].pk] = stream
    partner_target = {
        row.pk: stream["lead"] for stream in parsed for row in stream["rows"] if row.pk != stream["lead"].pk
    }
    all_rows = {row.pk: row for stream in parsed for row in stream["rows"]}
    summary = {"streams": len(parsed), "leads": [], "partners": 0, "unlinked": 0, "lecturers": {}}

    # 1) Bağları aç: aparıcı olanlar + aparıcısı dəyişən tərəfdaşlar + payload-dan kənar, tərəfdaş olacaq sətrə
    #    bağlı qalanlar (əks halda ``patok_row_is_lead`` / ``patok_lead_is_partner`` rədd edərdi).
    becoming_partner = set(partner_target)
    outsiders = TeachingTaskRow.objects.filter(task=task, patok_lead_id__in=becoming_partner).exclude(pk__in=all_rows)
    for row in outsiders:
        _save(task, actor, row, {"patok_lead_id": ""}, amend, request)
        summary["unlinked"] += 1
    for pk, row in all_rows.items():
        target = partner_target.get(pk)
        if row.patok_lead_id and (target is None or row.patok_lead_id != target.pk):
            _save(task, actor, row, {"patok_lead_id": ""}, amend, request)
            row.patok_lead_id = None

    # 2) Aparıcılar: mühazirə cəmi planına qayıdır (tərəfdaş idisə).
    for stream in parsed:
        lead = stream["lead"]
        data = {}
        if int(lead.lecture_total or 0) <= 0:
            plan = _per_group_plan(lead)
            data = {"lecture_plan": plan, "lecture_total": plan * max(int(lead.union_count or 1), 1)}
        if data:
            _save(task, actor, lead, data, amend, request)
        summary["leads"].append(str(lead.pk))

    # 3) Tərəfdaşlar: plan qalır (jurnal saatı), cəm 0 (yük bir dəfə), bağ → aparıcı.
    for pk, lead in partner_target.items():
        row = all_rows[pk]
        data = {"lecture_total": 0, "patok_lead_id": str(lead.pk)}
        if int(row.lecture_plan or 0) <= 0:
            data["lecture_plan"] = _per_group_plan(row)
        if int(row.lecture_total or 0) > 0 or row.patok_lead_id != lead.pk:
            _save(task, actor, row, data, amend, request, shrink=int(row.lecture_total or 0) > 0)
        summary["partners"] += 1

    # 4) Mühazirəçilər.
    for stream in parsed:
        if stream["teacher"] is not None:
            summary["lecturers"][str(stream["lead"].pk)] = _set_lecturer(
                task, actor, stream["lead"], stream["teacher"], amend, request
            )

    # 5) Açılış sinxronu BİR dəfə (ailə eyni fənndir — qardaş sətirlər birlikdə).
    first = parsed[0]["lead"]
    offerings = {}
    if first.subject_id:
        first.task = task
        offerings = compact(
            run_safely(sync_row_offerings, first, actor=actor, request=request, create=plan_reached_chair(task))
        )
    log_action(
        AuditAction.UPDATE,
        user=getattr(actor, "user", None),
        organization=task.organization,
        obj=task,
        new_values={**{k: v for k, v in summary.items() if k != "lecturers"}, "offerings": offerings},
        reason="workload.patok_streams",
        request=request,
        resource_type="workload.TeachingTask",
        resource_id=str(task.pk),
        resource_repr=first.subject_label,
    )
    return {**summary, "offerings": offerings}


__all__ = ["STREAM_ERRORS", "VACANT", "apply_streams"]
