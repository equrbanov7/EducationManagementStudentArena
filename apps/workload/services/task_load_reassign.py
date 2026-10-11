"""Rəsmi yük sənədindən (TAPŞIRIQ kitabçası / «Forma 1») mövcud tapşırıq sətrinin
müəllim bölgüsünü YENİLƏMƏ — yalnız mövcud servislər üzərindən (sahib 2026-10-12).

Yol (heç nə yan keçilmir):

1. Bölgü təsdiqlənibsə (``distributed``) — sətir üçün ``amendments.open_amendment``
   (səbəb «Rəsmi sərəncam/əmr», hədəf sətir) → tapşırıq ``amended``;
2. ``assignments.unassign`` (artıq bölgü) / ``assignments.assign_teacher`` (mövcud bölgü
   yerində yenilənir, çatışmayan yaradılır) — saat balansı, kafedra üzvlüyü qaydası və
   jurnal sahibinin (``CourseOffering.instructor``) DƏRHAL sinxronu oradadır;
3. çağıran sənəd sonunda ``confirm_distribution`` ilə yenidən ``distributed``-ə qaytarır.

BLOK (heç nə dəyişmir, sətir hesabatda ``blocked:<kod>``): jurnal sahibi dəyişəcəksə və
açılış «Fənn təhvili»/əl ilə başqa müəllimə verilibsə (``offering_owner_differs``), jurnal
bağlıdırsa / dövr bitibsə / açılış ləğv olunubsa / yeni müəllim bal yaza bilmirsə
(``registrar.handover.blockers`` ilə eyni kodlar), fəaliyyət bir neçə müəllimə bölünübsə
və sənəd tək müəllim deyirsə yox — hər halda servis imtina etsə (``WorkloadDenied``) və ya
sinxrondan sonra açılışın müəllimi yeni sahibə keçməyibsə (``offering_not_followed``).
Hər sətir öz savepoint-indədir: blok olan sətrin yarımçıq dəyişikliyi geri alınır.
"""

from __future__ import annotations

from collections import Counter

from django.apps import apps as django_apps
from django.db import transaction

from ..constants import AmendmentReason, AmendmentTarget, TaskStatus
from ..models import TeacherAssignment
from .amendments import open_amendment
from .assignments import assign_teacher, unassign
from .scoping import WorkloadDenied

#: ``registrar.handover.blockers`` kodlarından yük idxalını dayandıranlar.
_BLOCKING_CODES = ("offering_inactive", "journal_closed", "past_period", "target_not_eligible")

#: Nəticə kodları (hesabatda ``action``).
UNCHANGED = "unchanged"
ASSIGNED = "assigned"
REASSIGNED = "reassigned"
WOULD_ASSIGN = "would_assign"
WOULD_REASSIGN = "would_reassign"
DIFFERS = "teacher_differs"
BLOCKED = "blocked"


class _Blocked(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _signature(entries) -> list:
    return sorted((str(teacher_id or ""), int(hours), bool(hourly)) for teacher_id, hours, hourly in entries)


def _owner_id(plan: dict):
    """Jurnal sahibi (``offering_rules.journal_owner`` qaydası): mühazirəçi, yoxdursa ilk müəllim."""
    for teacher_id, _, _ in plan.get("lecture", []):
        if teacher_id:
            return teacher_id
    for activity in sorted(plan):
        for teacher_id, _, _ in plan[activity]:
            if teacher_id:
                return teacher_id
    return None


class RowPlanApplier:
    """Bir sətrin istənilən bölgüsünü (``{fəaliyyət: [(müəllim_id|None, saat, saathesabı)]}``) tətbiq edir."""

    def __init__(self, *, organization, actor, apply: bool, reassign: bool, note: str):
        self.org = organization
        self.actor = actor
        self.apply = apply
        self.reassign = reassign
        self.note = note
        self.counters: Counter = Counter()

    # ── oxu ───────────────────────────────────────────────────────────────
    def current_plan(self, row) -> dict:
        plan: dict = {}
        for assignment in TeacherAssignment.objects.filter(row=row).order_by("activity", "created_at"):
            plan.setdefault(str(assignment.activity), []).append(
                (assignment.teacher_id, assignment.hours, assignment.is_hourly_paid)
            )
        return plan

    def _offerings(self, row) -> list:
        if not row.subject_id or not row.period_id:
            return []
        CourseOffering = django_apps.get_model("registrar", "CourseOffering")
        return list(
            CourseOffering.objects.filter(
                organization=self.org,
                subject_id=row.subject_id,
                period_id=row.period_id,
                group_id__in=row.groups.values("pk"),
            ).select_related("period")
        )

    def blockers(self, row, current: dict, desired: dict) -> str:
        """İlk bloker kodu ("" = dəyişmək olar). Baza yazılmır."""
        for activity, entries in desired.items():
            if len(current.get(activity, [])) > 1 and len(entries) == 1 and not self._same_split(current, activity):
                # Fəaliyyət yarımqruplar üzrə bir neçə müəllimə bölünüb — tək ad ilə əzilmir.
                return "split_assignment"
        old_owner, new_owner = _owner_id(current), _owner_id(desired)
        if old_owner == new_owner:
            return ""
        from apps.registrar.public import handover

        for offering in self._offerings(row):
            if offering.instructor_id not in (None, old_owner, new_owner):
                return "offering_owner_differs"
            codes = (
                handover.blockers(offering, new_instructor_id=new_owner) if new_owner else handover.blockers(offering)
            )
            for code in _BLOCKING_CODES:
                if code in codes:
                    return code
        return ""

    @staticmethod
    def _same_split(current, activity) -> bool:
        return len({teacher_id for teacher_id, _, _ in current.get(activity, [])}) == 1

    # ── əsas ──────────────────────────────────────────────────────────────
    def apply_plan(self, row, desired: dict) -> tuple[str, str]:
        """→ ``(nəticə, detal)``. ``desired`` yalnız dəyişdirilən fəaliyyətləri saxlayır."""
        current = self.current_plan(row)
        changed = {a: e for a, e in desired.items() if _signature(e) != _signature(current.get(a, []))}
        if not changed:
            return self._count(UNCHANGED), ""
        fresh = not current
        if not fresh and not self.reassign:
            return self._count(DIFFERS), ",".join(sorted(changed))
        code = "" if fresh else self.blockers(row, current, {**current, **changed})
        if code:
            return self._count(BLOCKED), code
        if not self.apply:
            return self._count(WOULD_ASSIGN if fresh else WOULD_REASSIGN), ",".join(sorted(changed))
        try:
            with transaction.atomic():
                self._write(row, changed)
                if not fresh:
                    self._verify_offerings(row, _owner_id({**current, **changed}))
        except _Blocked as exc:
            return self._count(BLOCKED), exc.code
        except WorkloadDenied as exc:
            return self._count(BLOCKED), getattr(exc, "code", "") or "workload_denied"
        return self._count(ASSIGNED if fresh else REASSIGNED), ",".join(sorted(changed))

    def _count(self, action: str) -> str:
        self.counters[action] += 1
        return action

    def _ensure_amended(self, row) -> None:
        task = row.task
        task.refresh_from_db(fields=["status"])
        if task.status == TaskStatus.DISTRIBUTED:
            open_amendment(
                task=task,
                actor=self.actor,
                target_kind=AmendmentTarget.ROW,
                target_id=row.pk,
                reason=AmendmentReason.OFFICIAL,
                note=self.note,
                new_values={"source": "official_load_document"},
            )
            self.counters["amendment_opened"] += 1

    def _write(self, row, changed: dict) -> None:
        self._ensure_amended(row)
        row.task.refresh_from_db(fields=["status"])
        for activity, entries in changed.items():
            existing = list(TeacherAssignment.objects.filter(row=row, activity=activity).order_by("created_at"))
            for assignment in existing[len(entries) :]:
                unassign(assignment=assignment, actor=self.actor)
            pairs = list(zip(existing, entries))
            # Saatı azalanlar əvvəl — artan bölgü qalığı «görsün».
            pairs.sort(key=lambda pair: int(pair[1][1]) - pair[0].hours)
            for assignment, (teacher_id, hours, hourly) in pairs:
                assign_teacher(
                    row=row, actor=self.actor, activity=activity, teacher_id=teacher_id, hours=hours,
                    is_hourly_paid=hourly, note=self.note, assignment=assignment,
                )  # fmt: skip
            for teacher_id, hours, hourly in entries[len(existing) :]:
                assign_teacher(
                    row=row, actor=self.actor, activity=activity, teacher_id=teacher_id, hours=hours,
                    is_hourly_paid=hourly, note=self.note,
                )  # fmt: skip

    def fill_subject(self, row, subject) -> str:
        """Fənni BOŞ olan mövcud sətrə həll olunmuş fənni yazır (``tasks.save_row`` + düzəliş).

        Yalnız boş sahə doldurulur — mövcud fənn heç vaxt dəyişdirilmir."""
        if row.subject_id is not None or subject is None:
            return ""
        if not self.apply or not subject.pk:
            return self._count("would_fill_subject")
        from .tasks import save_row

        try:
            with transaction.atomic():
                self._ensure_amended(row)
                row.task.refresh_from_db(fields=["status"])
                saved = save_row(task=row.task, actor=self.actor, data={"subject_id": str(subject.pk)}, row=row)
        except WorkloadDenied as exc:
            self.counters["subject_fill_blocked"] += 1
            return f"subject_fill_blocked:{exc.code}"
        row.subject_id = saved.subject_id
        return self._count("subject_filled")

    def _verify_offerings(self, row, owner_id) -> None:
        if owner_id is None:
            return
        for offering in self._offerings(row):
            if offering.is_active and offering.instructor_id != owner_id:
                raise _Blocked("offering_not_followed")


__all__ = [
    "ASSIGNED",
    "BLOCKED",
    "DIFFERS",
    "REASSIGNED",
    "UNCHANGED",
    "WOULD_ASSIGN",
    "WOULD_REASSIGN",
    "RowPlanApplier",
]
