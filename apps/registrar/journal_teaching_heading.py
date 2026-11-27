"""Read-only heading projection: current teaching share and retained journal history."""

from django.utils import timezone
from django.utils.translation import gettext

from core.group_identity import canonical_aliases

from .journal_assignment_sources import teacher_journal_plan_hours
from .models import Lesson
from .practical_label import kind_choices


def current_plan(offering, user):
    from .language_cohort_journal import hours_for_offering, teacher_assignments

    if (None, None, offering.pk) in teacher_assignments(organization=offering.organization, teacher_id=user.pk):
        return hours_for_offering(offering)
    plans = teacher_journal_plan_hours(organization=offering.organization, teacher_id=user.pk)
    intensive = plans.get((None, None, offering.pk))
    if intensive is not None:
        return intensive
    group = offering.group if offering.group_id else None
    group_id = canonical_aliases([group]).get(group.pk, group).pk if group is not None else None
    return plans.get((offering.subject_id, offering.period_id, group_id), {})


def summarize(offering, *, personal_actor=None, scope=None):
    lessons = list(
        Lesson.objects.filter(organization_id=offering.organization_id, offering=offering)
        .select_related("instructor")
        .only(
            "kind",
            "hours",
            "date",
            "lab_group",
            "seminar_group",
            "is_passive",
            "instructor__first_name",
            "instructor__last_name",
            "instructor__username",
        )
    )
    # «Passiv» dərs (sahib 2026-11-14): keçirilmiş / planlı saata, həddə düşmür — başlıqda ayrıca «Passiv: N saat».
    passive = [lesson for lesson in lessons if lesson.is_passive]
    lessons = [lesson for lesson in lessons if not lesson.is_passive]
    plan = current_plan(offering, personal_actor) if personal_actor is not None else None
    allowed = set(plan) if plan else (getattr(scope, "kinds", None) if personal_actor is not None else None)
    permitted = [lesson for lesson in lessons if scope is None or scope.allows_lesson(lesson)]
    visible = [lesson for lesson in permitted if allowed is None or lesson.kind in allowed]
    if personal_actor is not None and plan:
        visible = _without_co_teachers(offering, visible, plan, personal_actor)
    result = _summary(
        offering,
        visible,
        total=sum(plan.values()) if plan else (None if personal_actor else offering.lesson_hours),
        # Fənnin (tələbə başına) saatı: Lab-1 və Lab-2 toplanmır; müəllimin şəxsi planı isə hər iki qrupu sayır.
        per_student=personal_actor is None,
    )
    result["personal"] = personal_actor is not None
    # Cari journal sahibinə təhvil verildikdən sonra əsas başlıq cari sahibin
    # adını göstərsin. Keçmiş dərslərin real müəllifləri ayrıca tarixçədə qalır.
    if personal_actor is not None and plan:
        current_name = (personal_actor.get_full_name() or "").strip() or personal_actor.username
        unknown = gettext("Müəllifi göstərilməyən tarixçə")
        for row in result["kinds"]:
            if row["kind"] in plan:
                # Müəllifsiz köhnə dərs heç vaxt cari sahibə yazılmır — işarə qalır.
                row["teachers"] = [current_name] + [name for name in row["teachers"] if name == unknown]
    today = timezone.localdate()
    result["passive_total"] = sum(
        int(lesson.hours or 0)
        for lesson in passive
        if (scope is None or scope.allows_lesson(lesson))
        and (allowed is None or lesson.kind in allowed)
        and (lesson.date is None or lesson.date <= today)
    )
    if plan:
        by_kind = {row["kind"]: row for row in result["kinds"]}
        for kind, hours in plan.items():
            row = by_kind.get(kind)
            if row is None:
                row = {"kind": kind, "label": dict(kind_choices(offering)).get(kind, kind), "held": 0, "teachers": []}
                result["kinds"].append(row)
            row["planned"] = hours
        result["kinds"].sort(key=lambda row: ("lecture", "seminar", "lab").index(row["kind"]))
    _split_parts(offering, result["kinds"], visible)
    if personal_actor is not None:
        result["history"] = _summary(offering, permitted, total=None)
        result["others"] = _other_shares(offering, plan, lessons) if plan else []
    if personal_actor is not None and not result["held_total"]:
        from .journal_prior_history_badge import available

        result["prior_history_available"] = offering.pk in available(
            personal_actor,
            [offering],
            organization=offering.organization,
            kinds={offering.pk: allowed},
            enrollment_ids={offering.pk: getattr(scope, "enrollment_ids", None)},
        )
    return result


def _without_co_teachers(offering, lessons, plan, actor):
    """MR-000879 (2026-11-27, 435 R ing / 935 BM): bir jurnalda EYNİ növü iki müəllim öz tələbələrinə ayrıca keçir
    (hər birinin öz yük sətri var, məs. 105 + 105). Şəxsi başlıq yalnız öz dərslərini saymalıdır — əks halda
    «149 / 105 — hədd keçilib» və öz planı alt qruplara bölünürdü («75 / 52»).

    Həmkar = dərsin müəllimi HAZIRDA bu jurnalın həmin növünə öz planı olan başqa müəllimdir. Təhvildən sonra köhnə
    müəllimin (cari planı yoxdur) və müəllifsiz köhnə dərslər əvvəlki kimi cari sahibin başlığında qalır."""
    others = {
        lesson.instructor_id
        for lesson in lessons
        if lesson.instructor_id and lesson.instructor_id != actor.pk and lesson.kind in plan
    }
    co_kinds = {}
    for teacher_id in others:
        kinds = set(current_plan(offering, _Teacher(teacher_id))) & set(plan)
        if kinds:
            co_kinds[teacher_id] = kinds
    if not co_kinds:
        return lessons
    return [lesson for lesson in lessons if lesson.kind not in co_kinds.get(lesson.instructor_id, ())]


class _Teacher:
    """``current_plan`` yalnız ``pk`` oxuyur — həmkarın istifadəçi sətrini ayrıca yükləmək lazım deyil."""

    def __init__(self, pk):
        self.pk = pk


def _split_parts(offering, kinds, lessons):
    """Sahib 2026-11-12 (135 TSPX): seminar alt qruplara / lab qruplarına bölünürsə, başlıqda hər biri ayrıca
    görünsün — «Seminar · 135TSPX-1 · 18 / 30», «Seminar · 135TSPX-2 · 14 / 30». Planlı saat bərabər bölünür."""
    from . import lab_groups, seminar_groups

    today = timezone.localdate()
    fields = {"seminar": ("seminar_group", seminar_groups.label), "lab": ("lab_group", lab_groups.label)}
    for row in kinds:
        spec = fields.get(row["kind"])
        if spec is None:
            continue
        field, label = spec
        held: dict = {}
        for lesson in lessons:
            number = getattr(lesson, field, None) if lesson.kind == row["kind"] else None
            if number:
                hours = int(lesson.hours or 0) if lesson.date is None or lesson.date <= today else 0
                held[number] = held.get(number, 0) + hours
        if len(held) < 2:
            continue
        planned = row.get("planned")
        share = int(planned) // len(held) if planned else None
        row["parts"] = [
            {"label": label(number, offering), "held": hours, "planned": share}
            for number, hours in sorted(held.items())
        ]


def _other_shares(offering, plan, lessons):
    """Sahib 2026-11-09: bölünmüş jurnalda mühazirəçi seminarın (və əksinə) KİMƏ təyin olunduğunu görsün.

    Fənnin rəsmi (bir qrup) planında olub bu müəllimin payına düşməyən növlər — yalnız OXU üçün başlıq çipi:
    növ, qrupun planlı saatı, keçirilmiş saat və pay sahibinin adı (``JournalShare``; pay yoxdursa dərsi
    aparan müəllim). Cəmlərə (``total`` / ``held_total``) qatılmır — onlar müəllimin öz payıdır.
    """
    from .journal_shares import active_shares
    from .plan_hours import plan_hours_for_offering

    official = {kind: int(hours) for kind, hours in plan_hours_for_offering(offering).items() if int(hours or 0)}
    missing = [kind for kind in ("lecture", "seminar", "lab") if kind in official and kind not in plan]
    if not missing:
        return []
    today = timezone.localdate()
    labels = dict(kind_choices(offering))
    rows = []
    for kind in missing:
        names = {}
        for share in active_shares(offering):
            if kind in (share.kinds or []) and share.teacher_id and share.teacher:
                names[share.teacher_id] = share.teacher.get_full_name().strip() or share.teacher.username
        held = 0
        for lesson in lessons:
            if lesson.kind != kind:
                continue
            if lesson.date is None or lesson.date <= today:
                held += int(lesson.hours or 0)
            if not names and lesson.instructor is not None:
                names[lesson.instructor_id] = lesson.instructor.get_full_name().strip() or lesson.instructor.username
        rows.append(
            {
                "kind": kind,
                "label": labels.get(kind, kind),
                "planned": official[kind],
                "held": held,
                "teachers": list(names.values()),
            }
        )
    return rows


def _summary(offering, lessons, *, total, per_student=False):
    from .lab_groups import is_split, per_student_hours

    today = timezone.localdate()
    labels = dict(kind_choices(offering))
    by_kind, scheduled_total = {}, 0
    for lesson in lessons:
        row = by_kind.setdefault(lesson.kind, {"held": 0, "teachers": {}})
        hours = int(lesson.hours or 0)
        scheduled_total += hours
        if lesson.date is None or lesson.date <= today:
            row["held"] += hours
        # Ownership and data-entry authorship never prove who actually taught an anonymous lesson.
        teacher = lesson.instructor
        name = (
            (teacher.get_full_name().strip() or teacher.username)
            if teacher
            else gettext("Müəllifi göstərilməyən tarixçə")
        )
        row["teachers"][teacher.pk if teacher else None] = name
    kinds = [
        {
            "kind": kind,
            "label": labels.get(kind, kind),
            "held": data["held"],
            "teachers": list(data["teachers"].values()),
        }
        for kind, data in by_kind.items()
    ]
    kinds.sort(key=lambda row: {"lecture": 0, "seminar": 1, "lab": 2}.get(row["kind"], 9))
    held_total = sum(row["held"] for row in kinds)
    if per_student and any(is_split(lesson) for lesson in lessons):
        # Lab qrupları / seminar alt qrupları (sahib 2026-11-06/07): tələbə yalnız öz qrupunun dərsindədir.
        held_lessons = [lesson for lesson in lessons if lesson.date is None or lesson.date <= today]
        scheduled_total = per_student_hours(lessons)
        held_total = per_student_hours(held_lessons)
        for row in kinds:
            row["held"] = per_student_hours([lesson for lesson in held_lessons if lesson.kind == row["kind"]])
    total = int(total or 0)
    return {
        "kinds": kinds,
        "held_total": held_total,
        "scheduled_total": scheduled_total,
        "total": total,
        "remaining": max(0, total - scheduled_total) if total else None,
        "over": bool(total and scheduled_total > total),
        "completed": bool(total and held_total >= total),
    }
