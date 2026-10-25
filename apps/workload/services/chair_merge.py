"""Kafedra qovuşması — dərs yükü, fənn kataloqu və sillabus tərəfi (sahib 2026-10-25).

Sahib: «İngilis dili mərkəzi (Kafedra)» rəsmi olaraq «Xarici dillər kafedrası»na çevrilib — ona birləşdir.
Vahid tərəfi (üzvlüklər, arxiv, köhnə ad) ``organizations.chair_merge``-dədir; bu modul yalnız mənbə
kafedraya bağlı CARİ işləri hədəfə köçürür. TARİXİ data toxunulmur: ``year``-dan əvvəlki tədris illərinin
tapşırıqları və köhnə semestrlərin sillabusları mənbə (arxiv) kafedrada qalır.

DƏRS YÜKÜ (``year`` və sonrakı illər, ləğv edilməmiş sənədlər):

* hədəfin həmin il tapşırığı YOXDURSA — mənbə tapşırığın ``chair``-i hədəfə dəyişir (status, bölgü, düzəliş
  tarixçəsi olduğu kimi qalır);
* VARSA — sətirlər bölgüləri ilə birlikdə hədəf tapşırığa köçür (``row.task``; bölgü/rəy/etiraz sətirə
  bağlıdır, açılışlar fənn + semestr + qrup ilə tapılır — açılış dəyişmir). EYNİ sətir (semestr, dövr, fənn,
  növ, qruplar, forma, dərəcə) hədəfdə artıq varsa saat İKİ DƏFƏ sayılmasın deyə köçmür, birləşir: hədəf
  sətrin bölgüsü yoxdursa mənbənin bölgüsü ona keçir (saat balansı yoxlanılır), mənbə sətri silinir; hər
  ikisinin bölgüsü varsa — ``duplicate_rows_conflict`` (əmr apply-ı rədd edir, qərar sahibindir).
  Boşalmış mənbə tapşırıq SİLİNMİR — ``cancelled`` olur (düzəliş/dilim tarixçəsi onda qalır), qeyd yazılır.
  Hədəf tapşırığın statusuna toxunulmur (``distributed`` qalır).

FƏNN KATALOQU: ``Subject.chair_unit`` və tədris planı sətrinin ``teaching_chair``-i — hamısı (kataloq cari
qaydadır, semestrə bağlı deyil).

SILLABUS: ``chair_unit`` mənbədirsə və dövrü ``year`` və sonrakıdırsa VƏ YA dövrsüz «baza sillabus»dursa
(müəllimin cari şablonu) — hədəfə; köhnə semestrlərinki qalır.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from django.apps import apps as django_apps
from django.db.models import Q

from core.audit import log_action, log_actions
from core.constants import AuditAction

from ..constants import TaskStatus
from ..models import TeacherAssignment, TeachingTask, TeachingTaskRow


def _text_key(value) -> str:
    return " ".join(str(value or "").casefold().split())


def row_key(row, group_ids) -> tuple:
    """Sətrin eyniliyi: semestr, dövr, fənn, növ, qruplar (yoxdursa yazılış), forma, dərəcə."""
    subject = str(row.subject_id) if row.subject_id else _text_key(row.subject_text)
    groups = frozenset(str(pk) for pk in group_ids) or _text_key(row.groups_text)
    return (row.season, str(row.period_id or ""), subject, row.row_kind, groups, row.education_form, row.degree_level)


def _rows_with_groups(task) -> list:
    rows = list(TeachingTaskRow.objects.filter(task=task).order_by("season", "order", "created_at"))
    groups = defaultdict(set)
    through = TeachingTaskRow.groups.through
    for row_id, group_id in through.objects.filter(teachingtaskrow__task=task).values_list(
        "teachingtaskrow_id", "orgunit_id"
    ):
        groups[row_id].add(group_id)
    return [(row, row_key(row, groups[row.pk])) for row in rows]


def _fits(target_row, assignments) -> bool:
    """Mənbə bölgüsü hədəf sətrin fəaliyyət cəmlərinə sığırmı (``workload_assignment_balance`` trigger-i)."""
    totals = Counter()
    for item in assignments:
        totals[item.activity] += int(item.hours or 0)
    return all(target_row.activity_total(activity) >= hours for activity, hours in totals.items())


class _LoadMerger:
    def __init__(self, organization, source, target, *, year, actor, reason, note):
        self.org, self.source, self.target = organization, source, target
        self.year, self.actor, self.reason, self.note = year, actor, reason, note
        self.counts: Counter = Counter()
        self.audit: list = []

    def _log(self, obj, old, new):
        self.audit.append(
            {
                "action": AuditAction.UPDATE,
                "user": self.actor,
                "organization": self.org,
                "obj": obj,
                "reason": self.reason,
                "old_values": old,
                "new_values": new,
            }
        )

    # ── dərs yükü ───────────────────────────────────────────────────────────
    def tasks(self):
        source_tasks = TeachingTask.objects.filter(
            organization=self.org, chair=self.source, academic_year__gte=self.year
        ).exclude(status=TaskStatus.CANCELLED)
        self.counts["tasks_history_kept"] = TeachingTask.objects.filter(
            organization=self.org, chair=self.source, academic_year__lt=self.year
        ).count()
        for task in source_tasks.order_by("academic_year"):
            target_task = TeachingTask.objects.filter(
                organization=self.org, academic_year=task.academic_year, chair=self.target
            ).first()
            if target_task is None:
                task.chair = self.target
                task.save(update_fields=["chair", "updated_at"])
                self.counts["tasks_rechaired"] += 1
                self.counts["rows_moved"] += task.rows.count()
                self._log(task, {"chair": str(self.source.pk)}, {"chair": str(self.target.pk)})
                continue
            self._merge_rows(task, target_task)

    def _merge_rows(self, task, target_task):
        index = {key: row for row, key in _rows_with_groups(target_task)}
        moved = []
        for row, key in _rows_with_groups(task):
            twin = index.get(key)
            assignments = list(TeacherAssignment.objects.filter(row=row))
            if twin is None:
                moved.append(row.pk)
                self.counts["rows_moved"] += 1
                self.counts["assignments_moved"] += len(assignments)
                self.counts["hours_moved"] += int(row.total_hours or 0)
                continue
            twin_has = TeacherAssignment.objects.filter(row=twin).exists()
            if assignments and (twin_has or not _fits(twin, assignments)):
                self.counts["duplicate_rows_conflict"] += 1
                continue
            if assignments:
                TeacherAssignment.objects.filter(row=row).update(row=twin)
                self.counts["assignments_moved"] += len(assignments)
            self.counts["duplicate_rows_merged"] += 1
            self._log(twin, {"merged_row": str(row.pk)}, {"assignments_moved": len(assignments)})
            row.delete()
        if moved:
            TeachingTaskRow.objects.filter(pk__in=moved).update(task=target_task)
            self._log(target_task, {"rows_from_task": str(task.pk)}, {"rows_moved": len(moved)})
        if not TeachingTaskRow.objects.filter(task=task).exists():
            old_status = task.status
            task.status = TaskStatus.CANCELLED
            task.note = f"{task.note}\n{self.note}".strip()
            task.save(update_fields=["status", "note", "updated_at"])
            self.counts["tasks_closed"] += 1
            self._log(
                task, {"status": old_status}, {"status": TaskStatus.CANCELLED, "merged_into": str(target_task.pk)}
            )

    # ── kataloq və sillabus ─────────────────────────────────────────────────
    def catalog(self):
        Subject = django_apps.get_model("registrar", "Subject")
        CurriculumSubject = django_apps.get_model("registrar", "CurriculumSubject")
        Syllabus = django_apps.get_model("syllabus", "Syllabus")
        subjects = Subject.objects.filter(organization=self.org, chair_unit=self.source)
        self.counts["subjects_moved"] = subjects.update(chair_unit=self.target)
        plan_rows = CurriculumSubject.objects.filter(teaching_chair=self.source)
        self.counts["plan_rows_moved"] = plan_rows.update(teaching_chair=self.target)
        current = Q(period__isnull=True) | Q(period__academic_year__gte=self.year)
        syllabi = Syllabus.objects.filter(organization=self.org, chair_unit=self.source)
        self.counts["syllabi_history_kept"] = syllabi.exclude(current).count()
        moved_ids = list(syllabi.filter(current).values_list("pk", flat=True))
        self.counts["syllabi_moved"] = Syllabus.objects.filter(pk__in=moved_ids).update(chair_unit=self.target)
        if self.counts["subjects_moved"] or self.counts["plan_rows_moved"] or self.counts["syllabi_moved"]:
            log_action(
                action=AuditAction.UPDATE,
                user=self.actor,
                organization=self.org,
                obj=self.target,
                reason=self.reason,
                old_values={"chair_unit": str(self.source.pk)},
                new_values={
                    "subjects_moved": self.counts["subjects_moved"],
                    "plan_rows_moved": self.counts["plan_rows_moved"],
                    "syllabi_moved": self.counts["syllabi_moved"],
                },
            )

    def run(self) -> Counter:
        self.tasks()
        self.catalog()
        if self.audit:
            log_actions(self.audit)
        return self.counts


def merge_chair_load(organization, source, target, *, year, actor=None, reason="", note="") -> Counter:
    """Mənbə kafedranın cari yükünü/kataloqunu/sillabuslarını hədəfə köçürür (YAZIR — dry-run çağıranın
    tranzaksiya geri qaytarmasıdır). Saylar ``Counter``-dir; ``duplicate_rows_conflict`` > 0 → apply olmamalıdır."""
    return _LoadMerger(organization, source, target, year=year, actor=actor, reason=reason, note=note).run()


__all__ = ["merge_chair_load", "row_key"]
