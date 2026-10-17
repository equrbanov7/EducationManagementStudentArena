"""Dərs cədvəlində olub dərs yükündə OLMAYAN dərs → tapşırıq sətri (sahib 2026-10-17).

Sahib: «Bunları da əlavə et sistemə. Müəllimlər görsün. Dərs yükündə olmayanlar vardır, onları da əlavə et.»
Magistratura cədvəlinin fənlərinin çoxu TAPŞIRIQ-ı heç idxal olunmamış kafedralara aiddir (beynəlxalq
münasibətlər, psixologiya, tarix, MBA …) — tapşırıq sətri, deməli açılış (jurnal) da yoxdur.
``assign_task_rows_from_timetable --create-missing-rows`` bu modulu işə salır.

QAYDALAR (ehtiyatlı):

* Namizəd — yalnız ``group_no_task_rows`` / ``subject_not_in_group`` hüceyrəsi (yaxın, amma qismən/çox
  mənalı fənn — ``subject_partial`` / ``subject_ambiguous`` — YARADILMIR); qrup başlığı DƏQİQ bir qrup
  vahidinə düşməlidir (alt qrup açılışı / eyni adlı iki qrup → ``create_group_not_single``).
* Bir (fənn, qrup) — BİR sətir: bir neçə hüceyrə toplanır; saat «(N saat)»-ın MAKSİMUMU (fərqlidirsə
  ``row_hours_differ`` sayı + hüceyrədə ``hours_max:…``); saat yoxdursa ``create_hours_missing``.
* Fənn — :meth:`Importer.find_subject` (kitabça idxalçısının qaydası: dəqiq ad, sonra ≥ 0.9 oxşarlıq);
  yoxdursa :meth:`Importer.resolve_subject` kimi kataloqda YARADILIR (``subject_created``, kod «QKU-N»,
  fənnin kafedrası = sətrin kafedrası).
* Kafedra (= tapşırıq) — fənnin sahib kafedrası (``Subject.chair_unit``) varsa o (müəllim əvvəl həmin
  kafedrada axtarılır; kənardan yalnız ``allow_outside_chair`` ilə — əlavə üzvlük); yoxdursa müəllim
  təşkilatda TƏK uyğun aktiv hesab olmalıdır və sətir onun ƏSAS kafedrasına düşür (bir neçə kafedra və
  əsası yoxdur → ``teacher_chair_unknown``). Hüceyrələrdə fərqli müəllim → ``conflict``.
* Tapşırıq — ``tasks.get_or_create_task`` (yoxdursa qaralama, audit; ``task_created``). Sətir —
  ``row_edit.save_row_amended`` (UI-nin yolu: bölgü təsdiqlənibsə əvvəl «Rəsmi sərəncam/əmr» düzəlişi);
  yalnız ``draft`` / ``distributed`` / ``amended`` sənədə (digər statusda ``task_blocked``). Saat bölgüsü
  məlum deyil → hamısı mühazirədə, qeyd «saat bölgüsü cədvəldən — kafedra dəqiqləşdirsin».
* Bölgü və açılış — mövcud sətirlərlə EYNİ yol (``TimetableTaskAssigner._apply_task``: qaralamanın rəsmi
  təsdiqi, ``RowPlanApplier``, ``Importer._confirm_and_enroll`` → açılış + qrupun tələbələri). Hər kafedra
  öz savepoint-indədir; dry-run-da heç nə yazılmır (yalnız saylar).
* İdempotent — ikinci işə salmada sətir artıq var → adi axın (``already_assigned``).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from django.apps import apps as django_apps
from django.db import transaction

from apps.registrar.public import schedule_docx_match, schedule_docx_parse
from core.constants import OrgUnitType

from ..constants import TEACHER_ROLE_NAMES, AmendmentReason, DegreeLevel, TaskStatus
from ..models import TeachingTask
from .imports import normalize
from .row_edit import AMENDABLE_STATUSES, save_row_amended
from .scoping import WorkloadDenied
from .tasks import get_or_create_task

NEW_ROW_NOTE = "saat bölgüsü cədvəldən — kafedra dəqiqləşdirsin"
ROW_CREATED = "row_created"
ROW_PLANNED = "row_planned"
#: Yeni sətir YALNIZ bu hallarda (yaxın fənn — ``subject_partial`` / ``subject_ambiguous`` — yox).
CREATABLE = ("group_no_task_rows", "subject_not_in_group")
#: Sətir əlavə oluna bilən tapşırıq statusları (``submitted`` / ``approved`` / ``distributing`` … — yox).
_OPEN_STATUSES = (TaskStatus.DRAFT, *AMENDABLE_STATUSES)
_CHAIR_TYPES = (OrgUnitType.CHAIR, OrgUnitType.DEPARTMENT)
_LECTURE = "lecture"


@dataclass
class _Spec:
    group: object
    name: str
    subject: object
    label: object
    cells: list = field(default_factory=list)
    chair: object = None
    user: object = None
    hours: int = 0


def _is_chair(unit) -> bool:
    return unit is not None and unit.is_active and unit.unit_type in _CHAIR_TYPES


class MissingRowCreator:
    def __init__(self, assigner, resolver):
        self.assigner = assigner
        self.resolver = resolver
        self.importer = assigner.importer
        self.counters = assigner.counters
        self._teacher_chairs: dict = {}

    # ── toplama ───────────────────────────────────────────────────────────
    def run(self) -> None:
        by_chair: dict = defaultdict(list)
        for spec in self._collect().values():
            if self._check(spec):
                by_chair[spec.chair.pk].append(spec)
        for specs in by_chair.values():
            if self.importer.apply:
                self._apply_chair(specs)
            else:
                self._plan_chair(specs)

    def _fail(self, cells, status: str, detail: str = "") -> None:
        for cell in cells:
            cell.detail = detail or cell.status
            cell.status = status

    def _single_group(self, label):
        units = self.resolver.group_units(label)
        if len(units) != 1:
            return None
        own = schedule_docx_parse.parse_group_label(units[0].name)
        same = own is not None and schedule_docx_match.label_key(own) + (own.sub,) == (
            schedule_docx_match.label_key(label) + (label.sub,)
        )
        return units[0] if same else None

    def _collect(self) -> dict:
        specs: dict = {}
        for cell in self.assigner.cells:
            if cell.status not in CREATABLE:
                continue
            text = cell.entry.text
            group = self._single_group(cell.entry.group)
            if group is None:
                self._fail([cell], "create_group_not_single")
                continue
            subject = self.importer.find_subject(text.subject)[0]
            key = (group.pk, subject.pk if subject is not None else f"name:{normalize(text.subject)}")
            spec = specs.setdefault(key, _Spec(group=group, name=text.subject, subject=subject, label=cell.entry.group))
            spec.cells.append(cell)
        return specs

    # ── yoxlama: saat, kafedra, müəllim ───────────────────────────────────
    def _check(self, spec: _Spec) -> bool:
        hours = {int(cell.entry.text.hours or 0) for cell in spec.cells} - {0}
        if not hours:
            self._fail(spec.cells, "create_hours_missing")
            return False
        spec.hours = max(hours)
        if len(hours) > 1:
            self.counters["row_hours_differ"] += 1
            for cell in spec.cells:
                cell.detail = "hours_max:" + "/".join(str(value) for value in sorted(hours, reverse=True))
        owner = getattr(spec.subject, "chair_unit", None) if spec.subject is not None else None
        resolved = []
        for cell in spec.cells:
            token = cell.entry.text.teacher
            if _is_chair(owner):
                user, action = self.assigner.resolve_teacher(owner, token)
            else:
                user, action = self._teacher_anywhere(token)
            cell.user, cell.teacher_action = user, action
            resolved.append(user)
        if any(user is None for user in resolved):
            for cell in spec.cells:
                if cell.user is None:
                    self._fail([cell], cell.teacher_action)
                else:
                    self._fail([cell], "conflict", "unresolved_peer")
            return False
        if len({user.pk for user in resolved}) > 1:
            self._fail(spec.cells, "conflict", "teachers_differ")
            return False
        spec.user = resolved[0]
        spec.chair = owner if _is_chair(owner) else self._teacher_chair(spec.user)
        if spec.chair is None:
            self._fail(spec.cells, "teacher_chair_unknown")
            return False
        return True

    def _teacher_anywhere(self, token: str) -> tuple:
        """Fənnin kafedrası yoxdur → təşkilatda TƏK uyğun aktiv müəllim (sonra əməkdaş) hesabı."""
        mapped = self.assigner.mapped_teacher(token)
        if mapped is not None:
            return mapped
        if not schedule_docx_match.split_teacher(token)[0]:
            return None, "teacher_missing"
        teachers, staff = self.assigner._org_pool()
        for users, action in ((teachers, "org_teacher"), (staff, "org_staff")):
            found = schedule_docx_match.teacher_matches(users, token, fuzzy=False)
            if len(found) > 1:
                return None, "teacher_ambiguous"
            if found:
                return found[0], action
        return None, "teacher_not_found"

    def _teacher_chair(self, user):
        """Müəllimin ƏSAS kafedrası: tək kafedra üzvlüyü və ya bir neçəsindən ``is_primary`` olanı."""
        if user.pk not in self._teacher_chairs:
            Membership = django_apps.get_model("organizations", "Membership")
            memberships = (
                Membership.objects.filter(
                    organization=self.assigner.org,
                    user=user,
                    is_active=True,
                    role__is_active=True,
                    role__name__in=TEACHER_ROLE_NAMES,
                    scope_unit__unit_type__in=_CHAIR_TYPES,
                    scope_unit__is_active=True,
                )
                .select_related("scope_unit")
                .order_by("-is_primary")
            )
            chairs = {m.scope_unit_id: m.scope_unit for m in memberships}
            primary = {m.scope_unit_id: m.scope_unit for m in memberships if m.is_primary}
            pick = chairs if len(chairs) == 1 else primary
            self._teacher_chairs[user.pk] = next(iter(pick.values())) if len(pick) == 1 else None
        return self._teacher_chairs[user.pk]

    # ── yazı ──────────────────────────────────────────────────────────────
    def _mark(self, spec: _Spec, status: str, row=None) -> None:
        for cell in spec.cells:
            cell.status, cell.row, cell.activity, cell.chair = status, row, _LECTURE, spec.chair
            cell.user = spec.user

    def _plan_chair(self, specs) -> None:
        """Dry-run: heç nə yazılmır — tapşırıq/fənn/sətir saylanır, status bloku əvvəlcədən görünür."""
        chair = specs[0].chair
        task = TeachingTask.objects.filter(
            organization=self.assigner.org, chair=chair, academic_year=self.assigner.year
        ).first()
        if task is not None and task.status not in _OPEN_STATUSES:
            for spec in specs:
                self._fail(spec.cells, "task_blocked", "workload.task_not_editable")
            self.counters["task_blocked"] += 1
            return
        self.counters["task_created"] += task is None
        for spec in specs:
            if spec.subject is None:
                spec.subject = self.importer.resolve_subject(spec.name, chair, "")[0]
            self.counters["row_created"] += 1
            self._mark(spec, ROW_PLANNED)
            for cell in spec.cells:
                cell.assignment = "would_assign"

    def _apply_chair(self, specs) -> None:
        importer = self.importer
        snapshot = (dict(importer.subject_index), list(importer.subject_names), importer.next_code)
        subjects_before = importer.counters["subject_created"]
        try:
            with transaction.atomic():
                rows, results = self._write_chair(specs)
        except WorkloadDenied as exc:
            importer.subject_index, importer.subject_names, importer.next_code = snapshot
            importer.counters["subject_created"] = subjects_before
            for spec in specs:
                self._fail(spec.cells, "task_blocked", getattr(exc, "code", "") or "workload_denied")
            self.counters["task_blocked"] += 1
            return
        self.counters["row_created"] += len(rows)
        for spec in specs:
            for cell in spec.cells:
                cell.assignment = results.get(cell.row.pk, "")

    def _write_chair(self, specs) -> tuple[list, dict]:
        importer, assigner = self.importer, self.assigner
        chair = specs[0].chair
        task, created = get_or_create_task(
            organization=assigner.org, chair_id=chair.pk, academic_year=assigner.year, actor=importer.actor
        )
        if task.status not in _OPEN_STATUSES:
            raise WorkloadDenied("workload.task_not_editable", "Tapşırıq bu statusda yeni sətir qəbul etmir.")
        self.counters["task_created"] += created
        amended = task.status in AMENDABLE_STATUSES
        rows, desired = [], {}
        for spec in specs:
            if spec.subject is None:
                spec.subject = importer.resolve_subject(spec.name, chair, "")[0]
            task.refresh_from_db(fields=["status", "distributed_at"])
            row = self._create_row(task, spec)
            rows.append(row)
            desired[row.pk] = {_LECTURE: [(spec.user.pk, spec.hours, False)]}
            self._mark(spec, ROW_CREATED, row)
        confirmed = self.counters["task_confirmed"]
        results = assigner._apply_task(task, rows, desired)
        task.refresh_from_db(fields=["status"])
        if amended and task.status == TaskStatus.AMENDED and self.counters["task_confirmed"] == confirmed:
            # Düzəlişi sətrin yaradılması açıb (``save_row_amended``) — bölgü təsdiqi sənədi yenidən bağlayır.
            importer._confirm_and_enroll(task)
            self.counters["task_confirmed"] += 1
        return rows, results

    def _create_row(self, task, spec: _Spec):
        group = spec.group
        parent = group.parent if group.parent_id else None
        data = {
            "season": self._season(),
            "period_id": str(self.assigner.period.pk),
            "subject_id": str(spec.subject.pk),
            "subject_text": spec.subject.name[:255],
            "groups_text": group.name[:255],
            "group_ids": [str(group.pk)],
            "union_count": 1,
            "subgroup_count": 1,
            "lecture_plan": spec.hours,
            "lecture_total": spec.hours,
            "note": NEW_ROW_NOTE,
        }
        if parent is not None and parent.unit_type == OrgUnitType.SPECIALTY:
            data["specialty_id"] = str(parent.pk)
        if "/" in spec.label.digits:  # «631/5 K» — magistratura qrupu
            data["degree_level"] = str(DegreeLevel.MASTER)
        amend = {"reason": str(AmendmentReason.OFFICIAL), "note": self.importer.applier.note}
        return save_row_amended(task=task, actor=self.importer.actor, data=data, amend=amend)

    def _season(self) -> str:
        from .timetable_task_assign import period_season

        return period_season(self.assigner.period)


__all__ = ["CREATABLE", "NEW_ROW_NOTE", "ROW_CREATED", "ROW_PLANNED", "MissingRowCreator"]
