"""Laboratoriya qrupları — Ekologiya kafedrası, 2026-11-06 (sabit id-lər; sahib: «köhnə sistemdəki kimi bölün»).

Köhnə sistemdə lab jurnalları Lab-1 / Lab-2 siyahılarına bölünmüşdü (``journals.students_id``); köçürmə hər fənnə BİR
jurnal yaratdı. Bu modul köhnə bölgünü ``Enrollment.lab_group``-a yazır (:mod:`apps.registrar.lab_groups`):

* 236 SBİO «Ümumi biologiya» (seminar 20, lab 10 + 10) — köhnə sistemdə bölgü yoxdur; sahib: fizikanın lab
  siyahıları kimi (köhnə 15365 Lab-1, 15366 Lab-2). Lab müəllimi (dərs yükündə lab 20 saat) seminarçıdır — onun
  payına «lab» növü əlavə olunur;
* 236 SBİO «Ümumi kimya» (seminar 15, lab 15 + 15) — köhnə 15244 (Lab-1), 15259 (Lab-2);
* 235 EM «Analitik kimya və instrumental analiz» (seminar 10, lab 5 + 5) — köhnə 15357 (Lab-1), 15358 (Lab-2).

Köhnə tələbə id-ləri EMS hesablarına delta alətlərinin ``StudentMapper`` qaydası ilə (ledger → identifikator → FİN)
prod nüsxəsində (2026-11-03) həll olunub; burada YALNIZ hesab id-ləri var. Siyahıda olmayan tələbə qrupsuz qalır
(``ungrouped`` sayı) — onu sahib/RİM qərar verir. Mövcud qrupsuz lab dərsinin bütün xanaları BİR qrupun
tələbələrindədirsə dərs həmin qrupa bağlanır (köçürülmüş Lab-1 / Lab-2 dərsləri).

İdempotentdir: ikinci qaçışda heç nə yazılmır (``*_already`` sayılır). Başqa dəyərli sətir üzərinə YAZILMIR
(``*_conflict``). Geri qaytarma: həmin açılışlarda ``lab_group`` sahələrini NULL etmək (köhnə davranış).
"""

from __future__ import annotations

from django.apps import apps as django_apps

from core.audit import log_action
from core.constants import AuditAction

REASON = "Sahib 2026-11-06 (Ekologiya kafedrası): lab qrupları köhnə sistemin Lab-1 / Lab-2 siyahıları ilə"
RESOURCE = "registrar.lab_groups"

# fmt: off
#: Fizika 236 SBİO, köhnə 15365 / 15366 (biologiya üçün də — sahib).
_PHYSICS_LAB1 = (
    8465, 8493, 8582, 8639, 8765, 8907, 8937, 8939, 8956, 8958, 8989, 9035, 9086, 9097, 9116, 9229, 9289, 9292, 9295,
)
_PHYSICS_LAB2 = (
    8448, 8451, 8514, 8523, 8555, 8637, 8696, 8774, 8817, 8835, 8894, 8921, 9138, 9145, 9302, 9374, 9405, 9426,
)

PLANS = (
    {
        "key": "bio",
        "offering": "975bd440-7d00-4a90-b0c1-86b166d07fcc",  # 236 SBİO «Ümumi biologiya»
        "groups": {1: _PHYSICS_LAB1, 2: _PHYSICS_LAB2},
        "lab_teacher": 9497,  # dərs yükü: seminar 40 + lab 20 (2 alt qrup)
    },
    {
        "key": "chem",
        "offering": "648d7125-c379-4ef0-8371-e921ee42a7a8",  # 236 SBİO «Ümumi kimya»; köhnə 15244 / 15259
        "groups": {
            1: (
                3793, 3796, 3799, 8465, 8493, 8582, 8639, 8765, 8907, 8956, 8958, 8989, 9035, 9086, 9097, 9116,
                9229, 9289, 9292, 9295,
            ),
            2: (
                3163, 8448, 8451, 8514, 8523, 8555, 8637, 8696, 8774, 8817, 8835, 8894, 8921, 9138, 9145, 9302,
                9374, 9405, 9426,
            ),
        },
        "lab_teacher": None,  # pay artıq «lab» növünü daşıyır
    },
    {
        "key": "anal",
        "offering": "f6555d68-5273-4c2d-9808-9a9a5b50d123",  # 235 EM «Analitik kimya …»; köhnə 15357 / 15358
        "groups": {
            1: (
                5852, 5918, 6016, 6018, 6022, 6024, 6030, 6061, 6062, 6063, 6064, 6069, 6070, 6071, 6611, 6618,
                6635, 11307,
            ),
            2: (
                6034, 6038, 6041, 6053, 6056, 6057, 6060, 6065, 6066, 6072, 6073, 6074, 6075, 6076, 6077, 6609,
                6613, 6615,
            ),
        },
        "lab_teacher": None,
    },
)
# fmt: on


def _model(name):
    return django_apps.get_model("registrar", name)


def _place_students(plan, offering, counts) -> dict:
    Enrollment = _model("Enrollment")
    key = plan["key"]
    rows = {
        row.student_id: row
        for row in Enrollment.objects.select_for_update().filter(
            organization_id=offering.organization_id, offering=offering, status=Enrollment.Status.ENROLLED
        )
    }
    wanted = {student: group for group, students in plan["groups"].items() for student in students}
    changed = []
    for student_id, group in sorted(wanted.items()):
        row = rows.get(student_id)
        if row is None:
            counts[f"{key}_not_enrolled"] += 1
        elif row.lab_group == group:
            counts[f"{key}_already"] += 1
        elif row.lab_group is not None:
            counts[f"{key}_conflict"] += 1
        else:
            row.lab_group = group
            changed.append(row)
            counts[f"{key}_lab{group}"] += 1
    if changed:
        Enrollment.objects.bulk_update(changed, ["lab_group"])
    counts[f"{key}_ungrouped"] += sum(1 for student_id, row in rows.items() if row.lab_group is None)
    return {row.pk: row.lab_group for row in rows.values()}


def _group_lessons(plan, offering, group_of, counts) -> None:
    """Qrupsuz lab dərsi → bütün xanaları bir qrupdadırsa həmin qrup."""
    Lesson = _model("Lesson")
    LessonMark = _model("LessonMark")
    key = plan["key"]
    for lesson in Lesson.objects.filter(offering=offering, kind="lab").order_by("date", "created_at"):
        if lesson.lab_group is not None:
            counts[f"{key}_lesson_already"] += 1
            continue
        marked = {
            group_of.get(pk) for pk in LessonMark.objects.filter(lesson=lesson).values_list("enrollment_id", flat=True)
        }
        if not marked:
            counts[f"{key}_lesson_unmarked"] += 1
        elif len(marked) == 1 and None not in marked:
            lesson.lab_group = marked.pop()
            lesson.save(update_fields=["lab_group", "updated_at"])
            counts[f"{key}_lesson_lab{lesson.lab_group}"] += 1
        else:
            counts[f"{key}_lesson_mixed"] += 1


def _share_lab_kind(plan, offering, counts) -> None:
    teacher_id = plan.get("lab_teacher")
    if teacher_id is None:
        return
    JournalShare = _model("JournalShare")
    key = plan["key"]
    share = JournalShare.objects.filter(offering=offering, teacher_id=teacher_id, is_active=True).first()
    if share is None:
        counts[f"{key}_share_missing"] += 1
    elif not share.kinds or "lab" in share.kinds:
        counts[f"{key}_share_already"] += 1  # boş = bütün növlər
    else:
        share.kinds = [*share.kinds, "lab"]
        share.save(update_fields=["kinds", "updated_at"])
        counts[f"{key}_share_lab_added"] += 1


def run(*, organization, actor, counts) -> None:
    CourseOffering = _model("CourseOffering")
    for plan in PLANS:
        key = plan["key"]
        offering = (
            CourseOffering.objects.select_for_update().filter(organization=organization, pk=plan["offering"]).first()
        )
        if offering is None:
            counts[f"{key}_offering_missing"] += 1
            continue
        before = dict(counts)
        group_of = _place_students(plan, offering, counts)
        _group_lessons(plan, offering, group_of, counts)
        _share_lab_kind(plan, offering, counts)
        delta = {name: value - before.get(name, 0) for name, value in counts.items() if value != before.get(name, 0)}
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            obj=offering,
            old_values={},
            new_values=delta,
            reason=REASON,
            resource_type=RESOURCE,
            resource_id=str(offering.pk),
        )


__all__ = ["PLANS", "REASON", "run"]
