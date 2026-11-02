"""Explicit current allocation from a populated journal; never manufacture taught hours."""

from django.apps import apps
from django.db import transaction
from django.db.models import F, Sum
from django.urls import reverse

from apps.registrar.public import offering_chairs
from apps.syllabus.public import approved_restore_sources, bind_approved_restore_source
from core.audit import log_action
from core.constants import AuditAction
from core.reviewed_graph import digest, graph

from ..constants import AmendmentReason, RowKind, TaskStatus
from ..models import TeacherAssignment, TeachingTask, TeachingTaskRow
from .history_restore_zero_plan import zero_placeholder_plan
from .row_edit import assign_amended, save_row_amended
from .scoping import WorkloadDenied, ensure_can_distribute, ensure_can_manage, manageable_chairs, resolve_actor

KINDS = ("lecture", "seminar", "lab")
RELEASED = (TaskStatus.APPROVED, TaskStatus.DISTRIBUTED, TaskStatus.AMENDED)


def actor_for_restore(request):
    user = getattr(request, "real_user", None) if getattr(request, "is_view_as", False) else request.user
    if not getattr(user, "is_active", False) or not getattr(user, "is_authenticated", False):
        raise WorkloadDenied("workload.history_restore_denied", "Aktiv istifadəçi tələb olunur.")
    if getattr(request, "is_view_as", False):
        if request.view_as_mode != "full":
            raise WorkloadDenied("workload.history_restore_denied", "Bu baxış rejimində yük bərpa edilmir.")
        return resolve_actor(request.real_user, request.organization)
    return resolve_actor(request.user, request.organization, request=request)


def _require(ok, code, text):
    if not ok:
        raise WorkloadDenied("workload.history_restore_" + code, text)


def _course(organization, offering_id, *, lock=False):
    model = apps.get_model("registrar.CourseOffering")
    queryset = model.objects.filter(organization=organization, pk=offering_id)
    if lock:
        queryset = queryset.select_for_update(of=("self",))
    course = queryset.select_related("period", "subject", "group", "instructor").first()
    _require(
        course is not None
        and course.is_active
        and not course.is_intensive
        and course.group_id is not None
        and course.instructor_id is not None
        and course.instructor.is_active,
        "course",
        "Aktiv müəllimi və fiziki qrupu olan adi jurnal tələb olunur.",
    )
    _require(
        course.period.organization_id == organization.pk
        and course.subject.organization_id == organization.pk
        and course.group.organization_id == organization.pk
        and course.period.is_active
        and course.period.is_current
        and course.period.locked_at is None,
        "period",
        "Yalnız aktiv cari semestrin açıq jurnalı bərpa edilə bilər.",
    )
    _require(
        apps.get_model("registrar.Lesson")
        .objects.filter(organization=organization, offering=course, instructor_id=course.instructor_id)
        .exists(),
        "history",
        "Bu müəllimin adına keçirilmiş dərs qeydi olan jurnal tələb olunur.",
    )
    return course


def _actor_chairs(actor):
    scope = actor.scope_for("workload.distribute")
    if not actor.has("workload.distribute") or not scope.has_structure_access:
        return []
    return list(manageable_chairs(actor).filter(scope.unit_subtree_q()))


def _unknown_chair_allowed(actor):
    return all(actor.scope_for(key).is_org_wide for key in ("workload.manage", "workload.distribute"))


def syllabus_context(course):
    from apps.registrar.public import credit_source, program_for_offering

    parent_id = getattr(course.group, "parent_id", None) if course.group_id else None
    programs = (
        apps.get_model("registrar.Program").objects.filter(
            organization_id=course.organization_id, specialty_unit_id=parent_id, is_active=True
        )
        if parent_id
        else None
    )
    if programs is None or programs.count() != 1:
        return None
    program = program_for_offering(course)
    if program is None or not program.degree_level or not program.education_form:
        return None
    credits = credit_source.plan_credit_for_offering(course)
    if not credits or credits <= 0:
        return None
    return program.degree_level, program.education_form, credits


def available_chairs(actor, course):
    known = offering_chairs.official_offering_chairs(
        course.__class__.objects.filter(pk=course.pk, organization=actor.organization), actor.organization.pk
    ).get(course.pk, frozenset())
    if not known and not _unknown_chair_allowed(actor):
        return []
    return [chair for chair in _actor_chairs(actor) if not known or str(chair.pk) in known]


def plan(request, offering_id):
    actor = actor_for_restore(request)
    course = _course(actor.organization, offering_id)
    chairs = available_chairs(actor, course)
    _require(bool(chairs), "scope", "Bu jurnalın kafedrası üzrə yük idarəetmə səlahiyyəti yoxdur.")
    return actor, course, chairs


def _matching_rows(course):
    return TeachingTaskRow.objects.filter(
        organization=course.organization,
        task__organization=course.organization,
        subject_id=course.subject_id,
        period_id=course.period_id,
        groups=course.group,
        row_kind=RowKind.TEACHING,
    ).exclude(task__status=TaskStatus.CANCELLED)


@transaction.atomic
def restore(*, request, offering_id, chair_id, hours, reason, syllabus_id=""):
    actor = actor_for_restore(request)
    course = _course(actor.organization, offering_id, lock=True)
    _require(
        isinstance(reason, str) and 10 <= len(reason.strip()) <= 2000, "reason", "Ən azı 10 simvolluq səbəb yazın."
    )
    _require(isinstance(hours, dict) and set(hours) == set(KINDS), "hours", "Üç dərs növünün saatını ayrıca göstərin.")
    _require(
        all(type(value) is int and 0 <= value <= 1000 for value in hours.values())
        and sum(hours.values()) > 0
        and sum(hours.values()) == course.lesson_hours,
        "hours",
        "Mühazirə, seminar və laboratoriya cəmi jurnalın mövcud ümumi saatına bərabər olmalıdır.",
    )
    taught = (
        apps.get_model("registrar.Lesson")
        .objects.filter(organization=actor.organization, offering=course, instructor_id=course.instructor_id)
        .values("kind")
        .annotate(total=Sum("hours"))
    )
    _require(
        all(row["kind"] in hours and hours[row["kind"]] >= row["total"] for row in taught),
        "taught_hours",
        "Plan saatı müəllimin həmin növdə artıq keçdiyi saatdan az ola bilməz.",
    )
    chairs = {str(chair.pk): chair for chair in available_chairs(actor, course)}
    _require(str(chair_id) in chairs, "scope", "Jurnalın səlahiyyətli mənbə kafedrasını seçin.")
    chair = chairs[str(chair_id)]
    ensure_can_manage(actor, chair.pk)
    ensure_can_distribute(actor, chair.pk)
    task = (
        TeachingTask.objects.select_for_update()
        .filter(organization=actor.organization, chair=chair, academic_year=course.period.academic_year)
        .first()
    )
    _require(task is not None and task.status in RELEASED, "task", "Kafedranın təsdiqlənmiş yük sənədi tələb olunur.")
    rows = list(_matching_rows(course).select_for_update(of=("self",)).select_related("task"))
    _require(
        len(rows) <= 1 and all(row.task_id == task.pk for row in rows),
        "row_conflict",
        "Eyni jurnal üçün başqa və ya bir neçə yük sətri var; bölgüdə uyğunlaşdırın.",
    )
    row = rows[0] if rows else None
    placeholder_plan = None
    if row is not None:
        row_groups = set(row.groups.values_list("pk", flat=True))
        _require(
            row_groups == {course.group_id},
            "patok",
            "Çoxqruplu yük sətirini yük bölgüsündə bərpa edin.",
        )
        placeholder_plan = zero_placeholder_plan(
            row,
            course=course,
            group_ids=row_groups,
            assignments=list(TeacherAssignment.objects.select_for_update().filter(row=row)),
        )
        _require(
            all(row.activity_total(kind) == hours[kind] for kind in KINDS) or placeholder_plan == hours,
            "plan_changed",
            "Mövcud yük sətrinin saatları ilə bərpa saatları uyğun gəlmir.",
        )
    assignments = list(TeacherAssignment.objects.select_for_update().filter(row__in=rows, activity__in=KINDS))
    _require(
        all(a.teacher_id in (None, course.instructor_id) for a in assignments),
        "teacher_conflict",
        "Bu fəaliyyət başqa müəllimə təyin olunub; bərpa onun təyinatını dəyişmir.",
    )
    by_kind = {kind: [a for a in assignments if a.activity == kind] for kind in KINDS}
    _require(all(len(values) <= 1 for values in by_kind.values()), "duplicate", "Bölgüdə təkrarlanan təyinat var.")
    already = all(
        (not hours[kind] and not by_kind[kind])
        or (
            len(by_kind[kind]) == 1
            and by_kind[kind][0].teacher_id == course.instructor_id
            and by_kind[kind][0].hours == hours[kind]
        )
        for kind in KINDS
    )
    sources = approved_restore_sources(course, chair_id=chair.pk, hours=hours, context_for=syllabus_context)
    own_source = next((source for source in sources if source.offering_id == course.pk), None)
    if not syllabus_id and own_source is not None:
        syllabus_id = str(own_source.pk)
    _require(
        len(sources) <= 1 or bool(syllabus_id),
        "syllabus_choice",
        "Bir neçə uyğun təsdiqli sillabus var; istifadə ediləcək sillabusu seçin.",
    )
    before = digest(graph({"registrar.CourseOffering": [course.pk]}, organization_id=actor.organization.pk))
    amend = {"reason": AmendmentReason.CORRECTION, "note": reason.strip()}
    if row is None:
        data = {
            "subject_id": str(course.subject_id),
            "period_id": str(course.period_id),
            "group_ids": [str(course.group_id)],
            "groups_text": course.group.name,
            "note": reason.strip(),
        }
        for kind in KINDS:
            data[kind + "_plan"] = hours[kind]
            data[kind + "_total"] = hours[kind]
        row = save_row_amended(task=task, actor=actor, data=data, amend=amend, request=request, sync_offerings=False)
    if placeholder_plan is not None:
        data = {kind + "_total": hours[kind] for kind in KINDS}
        data.update(union_count=int(hours["lecture"] > 0), subgroup_count=int(hours["seminar"] > 0 or hours["lab"] > 0))
        row = save_row_amended(
            task=task, row=row, actor=actor, data=data, amend=amend, request=request, sync_offerings=False
        )
    for kind in KINDS:
        if not hours[kind]:
            continue
        prior = by_kind[kind][0] if by_kind[kind] else None
        if prior is not None and prior.teacher_id == course.instructor_id:
            _require(prior.hours == hours[kind], "allocation_changed", "Mövcud müəllim saatı dəyişdirilmir.")
            continue
        assign_amended(
            row=row,
            actor=actor,
            activity=kind,
            teacher_id=course.instructor_id,
            hours=hours[kind],
            assignment=prior,
            amend=amend,
            note=reason.strip(),
            request=request,
            sync_offerings=False,
        )
    syllabus = bind_approved_restore_source(
        offering=course,
        actor=actor,
        chair_id=chair.pk,
        hours=hours,
        selected_id=syllabus_id,
        request=request,
        context_for=syllabus_context,
    )
    after_graph = graph({"registrar.CourseOffering": [course.pk]}, organization_id=actor.organization.pk)
    if syllabus["share_id"]:
        after_graph["syllabus.SyllabusShare"] = [
            item for item in after_graph.get("syllabus.SyllabusShare", []) if item["id"] != syllabus["share_id"]
        ]
        if not after_graph["syllabus.SyllabusShare"]:
            after_graph.pop("syllabus.SyllabusShare")
    after = digest(after_graph)
    _require(before == after, "academic_graph", "Jurnal məlumatları dəyişdi; bərpa geri qaytarıldı.")
    log_action(
        AuditAction.UPDATE,
        user=actor.user,
        organization=actor.organization,
        resource_type="workload.HistoryLoadRestore",
        resource_id=str(course.pk),
        reason=reason.strip(),
        old_values={"academic_sha256": before},
        new_values={
            "academic_sha256": after,
            "row_id": str(row.pk),
            "hours": hours,
            "teacher_id": course.instructor_id,
        },
        request=request,
    )
    return {
        "status": "already_restored" if already else "restored",
        "offering_id": str(course.pk),
        "row_id": str(row.pk),
        "syllabus_status": syllabus["status"],
    }


def attach_actions(request, offerings):
    if request is None:
        return
    candidates = [
        o
        for o in offerings
        if getattr(o, "journal_is_current_load", None) is False
        and o.instructor_id == request.user.pk
        and o.period.is_current
        and o.period.is_active
        and not o.is_intensive
    ]
    if not candidates:
        return
    try:
        actor = actor_for_restore(request)
        if not actor.has("workload.manage") or not actor.has("workload.distribute"):
            return
        ids = set(
            apps.get_model("registrar.Lesson")
            .objects.filter(
                organization=actor.organization,
                offering_id__in=[o.pk for o in candidates],
                instructor_id=F("offering__instructor_id"),
            )
            .values_list("offering_id", flat=True)
        )
        chairs = _actor_chairs(actor)
        mapping = offering_chairs.official_offering_chairs(
            candidates[0].__class__.objects.filter(pk__in=[o.pk for o in candidates], organization=actor.organization),
            actor.organization.pk,
        )
        for course in candidates:
            known = mapping.get(course.pk, frozenset())
            if (
                course.pk in ids
                and (known or _unknown_chair_allowed(actor))
                and any(not known or str(c.pk) in known for c in chairs)
            ):
                course.history_load_restore_url = reverse("workload:history_restore", args=[course.pk])
        from .history_restore_actions import attach_automatic_plans

        attach_automatic_plans(actor.organization, candidates)
    except WorkloadDenied:
        return


def previous_plan(course):
    rows = list(_matching_rows(course).filter(task__status__in=RELEASED))
    if len(rows) == 1 and set(rows[0].groups.values_list("pk", flat=True)) == {course.group_id}:
        hours = zero_placeholder_plan(
            rows[0],
            course=course,
            group_ids={course.group_id},
            assignments=list(TeacherAssignment.objects.filter(row=rows[0])),
        ) or {kind: rows[0].activity_total(kind) for kind in KINDS}
        if sum(hours.values()) == course.lesson_hours:
            return hours, "Mövcud təsdiqli yük sətri: " + str(rows[0].pk)
    sources = approved_restore_sources(course, context_for=syllabus_context)
    shapes = {tuple(int(s.approved_version.plan_hours.get(kind, 0)) for kind in KINDS) for s in sources}
    if len(shapes) == 1:
        return dict(zip(KINDS, shapes.pop())), "Müəllimin uyğun təsdiqli sillabus planı"
    return {}, "Əvvəlki dəqiq plan tapılmadı; dərs növlərinin planını ayrıca göstərin."
