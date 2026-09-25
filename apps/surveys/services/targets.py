"""Tələbənin qiymətləndirəcəyi hədəflər — kampaniya dövrünün BAĞLI jurnalları üzrə.

Qayda: dövrün hər (DROPPED olmayan) qeydiyyatı üçün jurnalı bağlıdırsa, açılışı
TƏDRİS EDƏN hər müəllim bir hədəfdir — ``(açılış, müəllim)`` cütü; üstəlik
kampaniya başına BİR «ümumi» bölmə (yalnız ən azı bir müəllim hədəfi olan
tələbəyə). Tamamlanma ``SurveyReceipt``-dən oxunur — cavabın özü oxunmur.

Sorğu sayı sabitdir (sətir sayından asılı deyil): qeydiyyatlar 1 + müəllimlər 2
+ qəbzlər 1 (+ etiketlər 2, yalnız ``with_labels``).
"""

from __future__ import annotations

from dataclasses import dataclass

from django.contrib.auth import get_user_model

from .. import registrar_bridge as bridge
from ..constants import Section
from ..models import SurveyReceipt


@dataclass(frozen=True)
class Target:
    scope: str
    offering_id: object = None
    teacher_id: int | None = None
    done: bool = False
    subject: str = ""
    subject_code: str = ""
    group: str = ""
    teacher_name: str = ""

    @property
    def is_general(self) -> bool:
        return self.scope == Section.GENERAL

    @property
    def key(self) -> str:
        return "general" if self.is_general else f"{self.offering_id}:{self.teacher_id}"


def _teacher_names(teacher_ids) -> dict:
    User = get_user_model()
    names = {}
    for pk, first, last, username in User.objects.filter(pk__in=set(teacher_ids)).values_list(
        "pk", "first_name", "last_name", "username"
    ):
        names[pk] = f"{first} {last}".strip() or username
    return names


def student_targets(campaign, student, *, with_labels: bool = False) -> list:
    """Tələbənin bu kampaniyadakı hədəfləri (tamamlanmış daxil), sabit sırada."""
    organization = campaign.organization_id
    offering_ids = list(
        bridge.closed_enrollments(organization, campaign.period_id, student=student)
        .values_list("offering_id", flat=True)
        .distinct()
    )
    teachers = bridge.offering_teachers(offering_ids) if offering_ids else {}
    pairs = sorted(
        ((offering_id, teacher_id) for offering_id, ids in teachers.items() for teacher_id in ids),
        key=lambda pair: (str(pair[0]), pair[1]),
    )
    pairs = [(offering_id, teacher_id) for offering_id, teacher_id in pairs if teacher_id != student.pk]
    if not pairs:
        return []
    receipts = set(
        SurveyReceipt.objects.filter(campaign=campaign, student=student).values_list(
            "scope", "offering_id", "teacher_id"
        )
    )
    labels, names = {}, {}
    if with_labels:
        labels = bridge.offering_labels([offering_id for offering_id, _teacher in pairs])
        names = _teacher_names([teacher_id for _offering, teacher_id in pairs])
    targets = []
    for offering_id, teacher_id in pairs:
        label = labels.get(offering_id, {})
        targets.append(
            Target(
                scope=Section.TEACHER,
                offering_id=offering_id,
                teacher_id=teacher_id,
                done=(Section.TEACHER, offering_id, teacher_id) in receipts,
                subject=label.get("subject", ""),
                subject_code=label.get("subject_code", ""),
                group=label.get("group", ""),
                teacher_name=names.get(teacher_id, ""),
            )
        )
    if with_labels:
        targets.sort(key=lambda t: (t.done, t.subject.lower(), t.teacher_name.lower()))
    general_done = any(scope == Section.GENERAL for scope, _offering, _teacher in receipts)
    targets.append(Target(scope=Section.GENERAL, done=general_done))
    return targets


def pending_counts(campaign, student) -> tuple[int, int]:
    """``(gözləyən, cəmi)`` — qapı və sayğac üçün (etiketsiz, 4 sorğu)."""
    targets = student_targets(campaign, student)
    return sum(1 for target in targets if not target.done), len(targets)


def find_target(targets, *, scope, offering_id=None, teacher_id=None):
    for target in targets:
        if target.scope != scope:
            continue
        if scope == Section.GENERAL:
            return target
        if str(target.offering_id) == str(offering_id) and target.teacher_id == teacher_id:
            return target
    return None


def next_pending(targets):
    """Növbəti gözləyən hədəf: əvvəl müəllimlər, sonda ümumi bölmə."""
    teacher = next((t for t in targets if not t.done and not t.is_general), None)
    if teacher is not None:
        return teacher
    return next((t for t in targets if not t.done), None)
