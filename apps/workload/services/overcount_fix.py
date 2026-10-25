"""Artıq sayılan dərs yükünün düzəlişi — RƏSMİ DÜZƏLİŞ AXINI ilə (sahib 2026-10-25).

Aşkarlama :mod:`.overcount_detect`-dədir; burada YALNIZ təhlükəsiz hallar avtomatik düzəlir, qalanı qərar
siyahısıdır (hesabat). Hər yazıdan əvvəl sətir üçün ``amendments.open_amendment`` (səbəb «Texniki səhvin
düzəlişi», qeyddə paket id-si, ``new_values``-da sətrin + bölgülərin TAM əvvəlki halı) — ``--undo`` bu
snapshot-dan bərpa edir (:mod:`.overcount_undo`). Sonda paylanmış sənəd yenidən təsdiqlənir (bildiriş yalnız
yükü dəyişən müəllimə — ``fix_task_row_hours`` naxışı).

1. DUBLİKAT (a) — sətir SİLİNİR (bölgüsü ilə; açılış/jurnal toxunulmur):
   * eyni qrup dəsti, biri vakant / bölgüsüz, digəri bölgülü → vakant gedir (saatı bölgülünün saatına sığırsa);
   * eyni qrup dəsti, bölgü imzası eyni (müəllim + növ + saat) → təkrar gedir; qalan — jurnalı (dərsi) olan,
     sonra rəsmi tapşırıq sətri, sonra ən köhnə;
   * «örtən» sətir (qrupları digərlərinin hamısını əhatə edir, hamısı eyni müəllimdə): RƏSMİ tapşırıq sətridirsə
     (və ya qrup sətirləri onu tam örtmürsə) o qalır, qrup sətirləri gedir; köhnə sistemin birgə jurnalından
     gəlibsə və qrup sətirləri onu tam bölürsə, o gedir — birgə dərs 2-ci addımda SÜBUTLA birləşir. Boş «köhnə»
     qrup («234 K az», 0 tələbə) bölündüyü qruplarla («234 K-1», «234 K-2») eyni sayılır.
   Müəllimləri / saatları fərqli dublikat — qərar siyahısı.
2. AXIN (b) — sübutlu birgə dərs: lövbər sətirdən başqa sətirlərin həmin növ saatı 0, həmin növ bölgüsü silinir.
   ``*_plan`` qrup başına saat kimi SAXLANILIR (jurnalın ``lesson_hours``-u dəyişmir — ``per_group_hours``
   əvvəl planı oxuyur), çarpan 0 (``union_count`` — mühazirə; ``subgroup_count`` — seminar və lab ikisi də 0
   olanda): «bu sətrin öz axını yoxdur, saat lövbər sətirdədir». Bölgü servis yan keçilərək silinir ki,
   jurnal sahibi dəyişməsin (birgə dərsi yenə o müəllim keçir) — hər silinmə audit jurnalındadır.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from django.db import DatabaseError, transaction

from core.audit import log_action
from core.constants import AuditAction

from ..constants import AmendmentReason, AmendmentTarget, TaskStatus
from ..models import TeacherAssignment, TeachingTask, TeachingTaskRow
from .amendments import open_amendment
from .distribution import confirm_distribution, distribution_readiness, teacher_loads
from .overcount_detect import MULTIPLIER_FIELD, PLAN_FIELD, TEACHING_ACTIVITIES, TOTAL_FIELD, detect
from .scoping import WorkloadDenied
from .tasks import ROW_SCALAR_FIELDS, delete_row, save_row

NOTE_PREFIX = "Artıq sayılan saat düzəlişi"
ACTION_DELETED = "overcount_row_deleted"
ACTION_ZEROED = "overcount_joint_zeroed"
AMENDABLE = (TaskStatus.DISTRIBUTED, TaskStatus.AMENDED)
ACTIVITY_LABELS = {"lecture": "Mühazirə", "seminar": "Seminar", "lab": "Laboratoriya"}


# ── qərar (saf funksiyalar) ─────────────────────────────────────────────────


def _covers(kept, other) -> bool:
    """``other``-in hər fəaliyyət saatı ``kept``-dəkindən çox deyil (silinəndə saat itmir)."""
    return all(other.hours[a] <= kept.hours[a] for a in TEACHING_ACTIVITIES)


def _keeper(rows, lessons: dict):
    """Saxlanan sətir: etirazı olan (silinə bilməz), jurnalı (dərsi) olan, rəsmi tapşırıq, ən köhnə."""
    return sorted(
        rows,
        key=lambda r: (not r.has_objection, -lessons.get(r.pk, 0), r.source != "task", r.row.created_at, str(r.pk)),
    )[0]


def _single_teacher_everywhere(rows) -> bool:
    """Hər fəaliyyət bütün sətirlərdə TƏK və EYNİ (vakant olmayan) müəllimdədir."""
    for activity in TEACHING_ACTIVITIES:
        teachers = set()
        for info in rows:
            if not info.hours[activity]:
                continue
            teacher = info.single_teacher(activity)
            if teacher is None:
                return False
            teachers.add(teacher)
        if len(teachers) > 1:
            return False
    return True


def plan_cluster(cluster: dict, lessons: dict) -> dict:
    """Dublikat klasteri → ``{"delete": [(info, saxlanan, səbəb)], "decision": kod | ""}``."""
    rows = cluster["rows"]
    if sum(1 for info in rows if info.has_objection) > 1:
        return _decision("objection_open")
    if cluster["exact"]:
        named = [info for info in rows if info.has_named()]
        if not named:
            kept = _keeper(rows, lessons)
            reason = "vacant_repeat"
        elif len({info.signature() for info in named}) == 1:
            kept = _keeper(named, lessons)
            reason = "same_teacher_repeat"
        else:
            return _decision(_differ_code(named))
        others = [info for info in rows if info is not kept]
        if any(info.has_objection for info in others):
            return _decision("objection_open")
        if any(info.has_named() and info.signature() != kept.signature() for info in others):
            return _decision("teachers_differ")
        if not all(_covers(kept, info) for info in others):
            return _decision("hours_differ")
        return {
            "delete": [(info, kept, reason if info.has_named() else "vacant_repeat") for info in others],
            "decision": "",
        }
    return _plan_covering(rows)


def _plan_covering(rows) -> dict:
    """Örtən sətir C: qrupları bütün digər sətirlərin qruplarını əhatə edir, hamısı eyni müəllimdə.

    * C RƏSMİ tapşırıq sətridirsə və ya digərləri C-nin bütün qruplarını örtmürsə → C qalır (axın orada bir dəfə
      yazılıb), qrup sətirləri gedir — hər birinin saatı C-nin qrup başına saatına sığmalıdır;
    * C köhnə sistemin birgə jurnalıdırsa («Dərs yükü faylı») və qrup sətirləri onun qruplarını tam bölürsə → C
      gedir, qrup sətirləri qalır; birgə dərs sonra SÜBUTLA (cədvəl/jurnal) birləşir — seminar qrup üzrə qalır.
    """
    union = frozenset().union(*(info.groups for info in rows))
    covering = [info for info in rows if info.groups == union]
    if len(covering) != 1:
        return _decision("overlap_complex")
    cover = covering[0]
    parts = [info for info in rows if info is not cover]
    if not _single_teacher_everywhere(rows):
        return _decision("teachers_differ")
    seen: set = set()
    disjoint = True
    for info in parts:
        disjoint = disjoint and not (info.groups & seen)
        seen |= info.groups
    if cover.source == "task" or seen != union:
        for info in parts:
            for activity in TEACHING_ACTIVITIES:
                share = cover.hours[activity] if activity == "lecture" else cover.per_group(activity) * len(info.groups)
                if info.hours[activity] > share:
                    return _decision("hours_differ")
        if any(info.has_objection for info in parts):
            return _decision("objection_open")
        return {"delete": [(info, cover, "repeat_of_stream_row") for info in parts], "decision": ""}
    if not disjoint or len(parts) < 2:
        return _decision("overlap_complex")
    if cover.has_objection:
        return _decision("objection_open")
    for activity in TEACHING_ACTIVITIES:
        if cover.hours[activity] > min(info.hours[activity] for info in parts):
            return _decision("hours_differ")
    return {"delete": [(cover, parts[0], "covered_by_group_rows")], "decision": ""}


def _differ_code(rows) -> str:
    """Bölgü imzaları fərqlidir: müəllim dəstləri eynidirsə — «saatlar fərqli», əks halda — «müəllimlər fərqli»."""
    teachers = {frozenset(a[0] for a in info.assignments if a[0] is not None) for info in rows}
    return "hours_differ" if len(teachers) == 1 else "teachers_differ"


def _decision(code: str) -> dict:
    return {"delete": [], "decision": code}


def offering_lessons(organization, infos) -> dict:
    """Sətir → onun (fənn, semestr, qrup) açılışlarındakı dərs sayı (saxlanacaq sətrin seçimi üçün)."""
    from django.apps import apps as django_apps
    from django.db.models import Count

    CourseOffering = django_apps.get_model("registrar", "CourseOffering")
    keys = {(i.row.subject_id, i.row.period_id) for i in infos if i.row.subject_id and i.row.period_id}
    if not keys:
        return {}
    subject_ids = {key[0] for key in keys}
    counts = {
        (row["subject_id"], row["period_id"], row["group_id"]): row["n"]
        for row in CourseOffering.objects.filter(organization=organization, subject_id__in=subject_ids)
        .values("subject_id", "period_id", "group_id")
        .annotate(n=Count("lessons"))
    }
    return {
        info.pk: sum(counts.get((info.row.subject_id, info.row.period_id, group), 0) for group in info.groups)
        for info in infos
    }


# ── yazı ────────────────────────────────────────────────────────────────────


def row_snapshot(row) -> dict:
    """Bərpa üçün sətrin TAM halı + bölgüləri (``overcount_undo``)."""
    fields = {field: getattr(row, field) for field in ROW_SCALAR_FIELDS}
    fields.update(
        {
            "total_hours": row.total_hours,
            "row_kind": row.row_kind,
            "review_status": row.review_status,
            "subject_id": str(row.subject_id or ""),
            "period_id": str(row.period_id or ""),
            "specialty_id": str(row.specialty_id or ""),
            "faculty_id": str(row.faculty_id or ""),
        }
    )
    assignments = [
        {
            "id": str(item.pk),
            "teacher_id": item.teacher_id,
            "activity": item.activity,
            "hours": item.hours,
            "groups_note": item.groups_note,
            "is_hourly_paid": item.is_hourly_paid,
            "note": item.note,
            "assigned_by_id": item.assigned_by_id,
        }
        for item in TeacherAssignment.objects.filter(row=row).order_by("created_at")
    ]
    return {
        "row_id": str(row.pk),
        "fields": fields,
        "group_ids": [str(pk) for pk in row.groups.values_list("pk", flat=True)],
        "assignments": assignments,
    }


class OvercountFixer:
    """Bir tranzaksiyada (çağıran açır) dublikat → yenidən aşkarlama → axın → yenidən təsdiq."""

    def __init__(self, *, organization, year: str, actor, batch: str, notify: bool = True):
        self.organization = organization
        self.year = year
        self.actor = actor
        self.batch = batch
        self.notify = notify
        self.counts: Counter = Counter()
        self.actions: list[dict] = []
        self.decisions: list[dict] = []
        self.loads_before: dict = {}
        self.was_distributed: set = set()
        self.joint_detection = None

    # -- giriş nöqtəsi --------------------------------------------------------
    def run(self) -> tuple:
        first = detect(self.organization, self.year)
        lessons = offering_lessons(self.organization, [i for c in first.duplicates for i in c["rows"]])
        for cluster in first.duplicates:
            plan = plan_cluster(cluster, lessons)
            if plan["decision"]:
                self.decisions.append({"kind": "duplicate", "code": plan["decision"], "cluster": cluster})
                self.counts["dup_decision_clusters"] += 1
                continue
            self.counts["dup_clusters_fixed"] += 1
            for info, kept, reason in plan["delete"]:
                self._delete(info, kept, reason)
        second = detect(self.organization, self.year)
        self.joint_detection = second  # dublikatlar həll olunandan sonrakı axınlar — hesabatın əsas cədvəli
        for stream in second.joint:
            if not stream["equal_hours"]:
                self.decisions.append({"kind": "joint", "code": "hours_differ", "stream": stream})
                self.counts["joint_decision_streams"] += 1
                continue
            self.counts[f"joint_{stream['activity']}_streams"] += 1
            for info in stream["others"]:
                self._zero(info, stream["activity"], stream["anchor"], ",".join(stream["evidence"]))
        self._reconfirm()
        return first, detect(self.organization, self.year)

    # -- addımlar -------------------------------------------------------------
    def _task(self, info):
        task = TeachingTask.objects.select_for_update().get(pk=info.row.task_id)
        if task.status not in AMENDABLE:
            return None
        if task.pk not in self.loads_before:
            self.loads_before[task.pk] = teacher_loads(task)
            if task.status == TaskStatus.DISTRIBUTED:
                self.was_distributed.add(task.pk)
        return task

    def _amend(self, task, row, action: str, extra: dict) -> None:
        open_amendment(
            task=task,
            actor=self.actor,
            target_kind=AmendmentTarget.ROW,
            target_id=row.pk,
            reason=AmendmentReason.CORRECTION,
            note=f"{NOTE_PREFIX} [{self.batch}]: {extra.get('why', '')}".strip(),
            new_values={"action": action, "batch": self.batch, "before": row_snapshot(row), **extra},
        )

    def _delete(self, info, kept, reason: str) -> None:
        task = self._task(info)
        if task is None:
            self.counts["blocked_status"] += 1
            return
        row = TeachingTaskRow.objects.get(pk=info.pk)
        hours = sum(int(a[2]) for a in info.assignments if a[0] is not None)
        try:
            with transaction.atomic():
                why = f"dublikat ({reason}) — saxlanan sətir {kept.pk}"
                self._amend(task, row, ACTION_DELETED, {"why": why, "kept_row": str(kept.pk), "rule": reason})
                task.refresh_from_db()
                delete_row(task=task, row=row, actor=self.actor)
        except WorkloadDenied as exc:
            self.counts[f"blocked_{exc.code}"] += 1
            return
        except DatabaseError:
            self.counts["blocked_db_guard"] += 1
            return
        self.counts[f"rows_deleted_{reason}"] += 1
        self.counts["hours_removed_named"] += hours
        self.counts["hours_removed_vacant"] += sum(int(a[2]) for a in info.assignments if a[0] is None)
        self.actions.append({"kind": "delete", "rule": reason, "info": info, "kept": kept, "hours": hours})

    def _zero(self, info, activity: str, anchor, evidence: str) -> None:
        if info.has_objection:
            self.counts["blocked_objection"] += 1
            self.decisions.append(
                {"kind": "joint_blocked", "code": "objection_open", "info": info, "activity": activity}
            )
            return
        task = self._task(info)
        if task is None:
            self.counts["blocked_status"] += 1
            return
        row = TeachingTaskRow.objects.get(pk=info.pk)
        removed = list(TeacherAssignment.objects.filter(row=row, activity=activity))
        data = {TOTAL_FIELD[activity]: 0, PLAN_FIELD[activity]: info.per_group(activity)}
        if activity == "lecture":
            data[MULTIPLIER_FIELD["lecture"]] = 0
        else:
            other = "lab" if activity == "seminar" else "seminar"
            if not int(getattr(row, TOTAL_FIELD[other]) or 0):
                data[MULTIPLIER_FIELD[activity]] = 0
        label = ACTIVITY_LABELS[activity]
        data["note"] = (
            (f"{row.note}\n" if row.note else "")
            + f"[{NOTE_PREFIX}] {label} birgə (axın) — saat «{anchor.subject} · {', '.join(sorted(anchor.group_names.values()))}» sətrində sayılır."
        )
        try:
            with transaction.atomic():
                why = f"{label} axını ({evidence}) — lövbər sətir {anchor.pk}"
                self._amend(task, row, ACTION_ZEROED, {"why": why, "activity": activity, "anchor_row": str(anchor.pk)})
                task.refresh_from_db()
                for assignment in removed:
                    payload = {
                        "activity": activity,
                        "hours": assignment.hours,
                        "teacher": str(assignment.teacher_id or ""),
                    }
                    assignment_id = str(assignment.pk)
                    assignment.delete()
                    log_action(
                        AuditAction.DELETE,
                        user=getattr(self.actor, "user", None),
                        organization=self.organization,
                        old_values=payload,
                        new_values={"batch": self.batch, "anchor_row": str(anchor.pk)},
                        reason="workload.overcount_joint_unassigned",
                        resource_type="workload.TeacherAssignment",
                        resource_id=assignment_id,
                        resource_repr=f"{info.subject} · {activity}",
                    )
                save_row(task=task, actor=self.actor, data=data, row=row)
        except WorkloadDenied as exc:
            self.counts[f"blocked_{exc.code}"] += 1
            self.decisions.append({"kind": "joint_blocked", "code": exc.code, "info": info, "activity": activity})
            return
        except DatabaseError:
            self.counts["blocked_db_guard"] += 1
            self.decisions.append({"kind": "joint_blocked", "code": "db_guard", "info": info, "activity": activity})
            return
        hours = sum(int(a.hours or 0) for a in removed if a.teacher_id)
        self.counts[f"rows_zeroed_{activity}"] += 1
        self.counts["hours_removed_named"] += hours
        self.counts["hours_removed_vacant"] += sum(int(a.hours or 0) for a in removed if not a.teacher_id)
        self.actions.append(
            {"kind": "zero", "activity": activity, "info": info, "kept": anchor, "hours": hours, "evidence": evidence}
        )

    def _reconfirm(self) -> None:
        for task in TeachingTask.objects.filter(pk__in=list(self.loads_before)):
            if task.status != TaskStatus.AMENDED or task.pk not in self.was_distributed:
                continue
            readiness = distribution_readiness(task)
            if not readiness["is_ready"]:
                self.counts["tasks_left_amended"] += 1
                continue
            confirm_distribution(
                task=task,
                actor=self.actor,
                allow_vacant=True,
                notify=self.notify,
                loads_before=self.loads_before[task.pk],
            )
            self.counts["tasks_reconfirmed"] += 1


def teacher_totals(organization, year: str) -> dict:
    """Müəllim → {"total", "by_chair": {chair_id: saat}} — bütün kafedralar (ləğv olunmuş sənəd xaric)."""
    totals: dict = defaultdict(lambda: {"total": 0, "by_chair": defaultdict(int)})
    rows = (
        TeacherAssignment.objects.filter(
            organization=organization, row__task__academic_year=year, teacher__isnull=False
        )
        .exclude(row__task__status=TaskStatus.CANCELLED)
        .values_list("teacher_id", "row__task__chair_id", "hours")
    )
    for teacher_id, chair_id, hours in rows:
        totals[teacher_id]["total"] += int(hours or 0)
        totals[teacher_id]["by_chair"][str(chair_id)] += int(hours or 0)
    return totals


__all__ = [
    "ACTION_DELETED",
    "ACTION_ZEROED",
    "NOTE_PREFIX",
    "OvercountFixer",
    "plan_cluster",
    "row_snapshot",
    "teacher_totals",
]
