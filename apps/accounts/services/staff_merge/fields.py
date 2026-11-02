"""Dublikat müəllim hesabından əsas hesaba KÖÇƏN sahələrin inventarı (sahib 2026-11-03).

Siyahı istifadəçiyə işarə edən BÜTÜN FK-ların kod üzrə taranmasından çıxıb (``get_user_model()`` → hər
``related_model``); burada YALNIZ məhsulun «bu müəllimin işi»ni oxuduğu sahələr var — hər sətrin yanında oxuyan yer:

* ``registrar.CourseOffering.instructor`` — jurnal sahibi (``teacher_journal_list.project``: ``instructor=user``).
* ``registrar.Lesson.instructor`` — «Adınıza keçirilmiş: N dərs / M saat»
  (``teacher_journal_list.attach``: ``Lesson.objects.filter(..., instructor=user, date__lte=bu gün)``),
  dərs yükü hesabatı (``teaching_hours.recorded_teaching_hours``), fənn qovluğu (``subject_folder.services.lookups``).
* ``registrar.Lesson.created_by`` — müəllimin öz tarixçəsi (``journal_own_history.recorded_lessons``).
* ``registrar.ScheduleSlot.instructor`` — müəllim cədvəli (``schedule.effective_instructor``).
* ``registrar.JournalShare.teacher`` — bölünmüş jurnal payı (``journal_shares.own_or_shared_q``).
* ``workload.TeacherAssignment.teacher`` / ``TeacherWorkloadProfile.teacher`` / ``LoadObjection.teacher`` — dərs yükü.
* ``syllabus.Syllabus.author`` — «mənim sillabusum» (``syllabus.services.scoping.is_author``, ``offerings``);
  ``SyllabusVersion.created_by`` / ``submitted_by``, ``SyllabusSection.updated_by``, ``SyllabusShare.created_by`` —
  müəllif tərəfinin versiya/paylaşım sahələri.
* ``timetable.TeacherAvailability.teacher`` / ``TimetableDraftSlot.teacher`` — cədvəl qurucusu.
* ``subject_folder.SubjectFolder.owner`` — fənn qovluğu.
* ``exams.Exam.journal_teacher`` — imtahan ↔ jurnal körpüsü (``exam_journal_link``).

QƏSDƏN KÖÇMƏYƏNLƏR (səbəb ilə):

* bal/davamiyyət cədvəllərinin ``entered_by`` sahələri (``LessonMark``, ``ComponentScore``, ``FinalGrade`` …) — dəyər
  sətirlərinə toxunulmur (sahibin şərti); «keçirilib» sayı onlardan oxunmur;
* aktor/tarixçə sahələri (``*_by``, ``TeachingHandover.from/to_instructor``, ``LessonCorrection.old/new_instructor``,
  ``AuditLog.user``) — nə vaxt, kim etdi faktıdır;
* hesabın öz kimliyi (``UserProfile``, ``Membership``, ``EmploymentContract``, ``OrgUnit.head``) — dublikat bloklu
  qalır, əsas hesabın öz üzvlüyü var;
* sorğu (``surveys.*``) — anonim qiymətləndirmə, tələbə × müəllim unikallığı; imtahan müəllifliyi (``Exam.author``,
  ``QuestionSubmission`` …) — dublikat heç vaxt daxil olmayıb, belə sətir yaratmayıb.

Qalan istinadlar əmrin sonunda ``staff_merge_left:`` sətrində SAYLA göstərilir (gizli qalmır).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from django.db.models import Q


@dataclass(frozen=True)
class Move:
    label: str  # "app.Model"
    field: str  # FK adı (``_id`` olmadan)
    #: Hədəfdə eyni məntiqi sətir artıq varsa (unikallıq / mənasız təkrar) mənbə sətri ATLANIR.
    conflict: Callable | None = None

    @property
    def key(self) -> str:
        return f"{self.label.replace('.', '_').lower()}_{self.field}"


def _share_conflict(model, row, target_id):
    if not row.is_active:
        return False
    if model._base_manager.filter(offering_id=row.offering_id, teacher_id=target_id, is_active=True).exists():
        return True
    # Hədəf jurnalın TAM sahibidirsə dar pay onun səlahiyyətini məhdudlaşdırardı (təhvil qaydası ilə eyni).
    return row.offering.instructor_id == target_id


def _assignment_conflict(model, row, target_id):
    return model._base_manager.filter(row_id=row.row_id, activity=row.activity, teacher_id=target_id).exists()


def _profile_conflict(model, row, target_id):
    return model._base_manager.filter(
        organization_id=row.organization_id, academic_year=row.academic_year, teacher_id=target_id
    ).exists()


def _base_syllabus_conflict(model, row, target_id):
    if row.offering_id is not None or row.period_id is not None:
        return False
    return model._base_manager.filter(
        organization_id=row.organization_id,
        subject_id=row.subject_id,
        author_id=target_id,
        offering__isnull=True,
        period__isnull=True,
    ).exists()


def _availability_conflict(model, row, target_id):
    return model._base_manager.filter(
        organization_id=row.organization_id, period_id=row.period_id, teacher_id=target_id
    ).exists()


def _folder_conflict(model, row, target_id):
    period = Q(period__isnull=True) if row.period_id is None else Q(period_id=row.period_id)
    return (
        model._base_manager.filter(organization_id=row.organization_id, subject_id=row.subject_id, owner_id=target_id)
        .filter(period)
        .exists()
    )


#: Sıra vacibdir: açılış sahibi əvvəl köçür ki, jurnal payının «hədəf artıq sahibdir» yoxlaması onu görsün.
MOVES = (
    Move("registrar.CourseOffering", "instructor"),
    Move("registrar.Lesson", "instructor"),
    Move("registrar.Lesson", "created_by"),
    Move("registrar.ScheduleSlot", "instructor"),
    Move("registrar.JournalShare", "teacher", _share_conflict),
    Move("workload.TeacherAssignment", "teacher", _assignment_conflict),
    Move("workload.TeacherWorkloadProfile", "teacher", _profile_conflict),
    Move("workload.LoadObjection", "teacher"),
    Move("syllabus.Syllabus", "author", _base_syllabus_conflict),
    Move("syllabus.SyllabusVersion", "created_by"),
    Move("syllabus.SyllabusVersion", "submitted_by"),
    Move("syllabus.SyllabusSection", "updated_by"),
    Move("syllabus.SyllabusShare", "created_by"),
    Move("timetable.TeacherAvailability", "teacher", _availability_conflict),
    Move("timetable.TimetableDraftSlot", "teacher"),
    Move("subject_folder.SubjectFolder", "owner", _folder_conflict),
    Move("exams.Exam", "journal_teacher"),
)
