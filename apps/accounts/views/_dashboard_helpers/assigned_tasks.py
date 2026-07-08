"""
Assigned-tasks collector for the profile dashboard.
"""

from django.contrib.auth import get_user_model
from django.db.models import Count, F, IntegerField, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils import timezone

from apps.assignments.models import Assignment
from apps.courses.models import CourseMembership
from apps.exams.constants import ATTEMPT_FINISHED_STATUSES
from apps.exams.models import ExamAttempt, StudentExamAttemptGrant
from apps.exams.public import student_final_exam_context
from apps.labs.models import Lab
from apps.projects.models import Project

from .._helpers import (
    _append_query_params,
    _assigned_courses_queryset,
    _assigned_exams_queryset,
    _csv_to_lower_token_set,
    _normalize_assigned_tasks_filter,
    _task_state_badge_data,
)
from .formatters import _standard_item_type_meta

User = get_user_model()


def _collect_assigned_tasks(request, filter_type=None, search=None):
    """
    Build a unified assigned task list across exams, assignments, labs, and projects.
    """
    user = request.user
    selected_filter = filter_type if filter_type is not None else request.GET.get("assigned_type")
    filter_type = _normalize_assigned_tasks_filter(selected_filter)
    search_query = (search if search is not None else request.GET.get("assigned_search", "")).strip()
    search_token = search_query.lower()
    now = timezone.now()

    assigned_courses_qs = _assigned_courses_queryset(request, user).select_related("owner").order_by("-created_at")
    course_ids = list(assigned_courses_qs.values_list("id", flat=True))

    memberships = CourseMembership.objects.filter(
        course_id__in=course_ids,
        user=user,
        role="student",
    ).values_list("course_id", "group_name")
    course_groups = {}
    for course_id, group_name in memberships:
        normalized_group = (group_name or "").strip().lower()
        if not normalized_group:
            continue
        course_groups.setdefault(course_id, set()).add(normalized_group)

    items = []
    counts = {"exams": 0, "courses": 0, "assignments": 0, "labs": 0, "independent": 0}

    def matches_search(*values):
        if not search_token:
            return True
        for value in values:
            if search_token in (value or "").lower():
                return True
        return False

    def append_item(
        *,
        category,
        title,
        kind,
        icon,
        detail_url,
        assigned_at=None,
        deadline=None,
        state="open",
        description="",
        extra=None,
    ):
        state_label, state_badge = _task_state_badge_data(state)
        payload = {
            "category": category,
            "title": title,
            "kind": kind,
            "icon": icon,
            "type_label": _standard_item_type_meta(category)[0],
            "detail_url": detail_url,
            "assigned_at": assigned_at,
            "deadline": deadline,
            "state_label": state_label,
            "state_badge": state_badge,
            "description": description,
            "sort_at": assigned_at or deadline or now,
        }
        if extra:
            payload.update(extra)
        items.append(payload)

    counts["courses"] = assigned_courses_qs.count()

    # Cəhd limiti bitmiş (tamamlanıb qiymətləndirilmiş) imtahanlar təyin olunmuş
    # tapşırıqlardan çıxır — tələbə nəticəsini "Nəticələr" bölməsində görür.
    # Müəllimin verdiyi əlavə cəhd (grant) nəzərə alınır.
    _finished_sq = Subquery(
        ExamAttempt.objects.filter(
            exam=OuterRef("pk"),
            user=user,
            status__in=ATTEMPT_FINISHED_STATUSES,
        )
        .values("exam")
        .annotate(cnt=Count("id"))
        .values("cnt"),
        output_field=IntegerField(),
    )
    _grant_sq = Subquery(
        StudentExamAttemptGrant.objects.filter(exam=OuterRef("pk"), student=user).values("extra_attempts")[:1],
        output_field=IntegerField(),
    )
    assigned_exams_qs = (
        _assigned_exams_queryset(request, user, active_only=True)
        .annotate(
            _finished_attempts=Coalesce(_finished_sq, 0),
            _extra_grant=Coalesce(_grant_sq, 0),
        )
        .filter(
            Q(max_attempts_per_user__isnull=True)
            | Q(max_attempts_per_user=0)
            | Q(_finished_attempts__lt=F("max_attempts_per_user") + F("_extra_grant"))
        )
        .order_by("-start_datetime", "-created_at")
    )
    counts["exams"] = assigned_exams_qs.count()
    if filter_type in {"all", "exams"}:
        for exam in assigned_exams_qs:
            if not matches_search(
                exam.title,
                exam.description,
                exam.course.title if exam.course else "",
            ):
                continue

            category = getattr(exam, "exam_type_extended", None)
            # Final imtahanları HƏMİŞƏ imtahan mərkəzi axını ilə verilir: tələbə
            # kabinetdən imtahana BAŞLAYA BİLMİR — yalnız məlumat + fərdi giriş
            # PIN-ini görür və imtahana `/exams/final/` səhifəsindən istifadəçi
            # adı + PIN ilə daxil olur. Bilet hələ təyin olunmayıbsa (otaq-oturum
            # yaradılmayıb) modal bunu bildirir; giriş kodu/PIN xanası göstərilmir.
            is_final_exam = category == "final"
            final_ctx = student_final_exam_context(user, exam) if is_final_exam else {}
            has_ticket = bool(final_ctx.get("has_ticket"))
            use_center_flow = is_final_exam

            # Final/midterm: imtahan yaradılanda hər tələbəyə təyin olunan fərdi
            # PIN (dərhal görünür). Midterm bunu kabinet giriş xanasında, final
            # isə yalnız məlumat olaraq (PIN blokunda) göstərir.
            student_pin = None
            if category in {"final", "midterm"}:
                from apps.exams.services.student_pins import student_visible_pin

                student_pin = student_visible_pin(exam, user)

            # Final imtahanının kabinetdə göstərilən giriş PIN-i: imtahan mərkəzi
            # bileti varsa onun (zaman-pəncərəli) PIN-i, yoxdursa təyin olunmuş
            # fərdi PIN. `final_pin_assigned` — PIN mənbəyi mövcuddur (təyin
            # olunub); False olduqda modal "hələ təyin olunmayıb" göstərir.
            if has_ticket:
                final_display_pin = final_ctx.get("pin")
                final_pin_assigned = True
            else:
                final_display_pin = student_pin
                final_pin_assigned = bool(student_pin)

            # Biletli final: vaxt aralığı oturumla təyin olunur; digərləri imtahan
            # başlama/bitmə tarixinə görə.
            if use_center_flow and has_ticket:
                window_start = final_ctx.get("window_start")
                window_end = final_ctx.get("window_end")
                if window_start and now < window_start:
                    state = "upcoming"
                elif window_end and now > window_end:
                    state = "closed"
                else:
                    state = "open"
            elif exam.start_datetime and now < exam.start_datetime:
                state = "upcoming"
            elif exam.end_datetime and now > exam.end_datetime:
                state = "closed"
            else:
                state = "open"

            extra = {
                "exam_slug": exam.slug,
                "exam_type_display": exam.get_exam_type_display(),
                "exam_total_duration_minutes": exam.total_duration_minutes,
                "exam_start_at": exam.start_datetime,
                "exam_end_at": exam.end_datetime,
                # Final imtahanı kabinetdən başladılmadığı üçün giriş kodu/PIN
                # xanası göstərilmir; yalnız midterm/adi imtahanlar kod istəyə bilər.
                "exam_requires_code": (not use_center_flow) and (bool(exam.access_code) or bool(student_pin)),
                "is_final": use_center_flow,
                # Sehrbazla yaradılan midterm imtahanında tələbənin fərdi PIN-i.
                "student_pin": student_pin or "",
            }
            if use_center_flow:
                extra.update(
                    {
                        # PIN mənbəyi (bilet və ya fərdi PIN) təyin olunubmu.
                        "final_has_ticket": final_pin_assigned,
                        "final_pin": final_display_pin,
                        "final_room": final_ctx.get("room_name"),
                        "final_entry_open": final_ctx.get("entry_open", False),
                        "final_status": final_ctx.get("status"),
                        "final_entry_url": reverse("exams:final_exam_entry"),
                        # Modal/aralıq göstərişi üçün oturum vaxtları (exam tarixlərini əvəz edir).
                        "exam_start_at": final_ctx.get("window_start") or exam.start_datetime,
                        "exam_end_at": final_ctx.get("window_end") or exam.end_datetime,
                    }
                )

            append_item(
                category="exams",
                title=exam.title,
                kind=f"İmtahan - {exam.get_exam_type_display()}",
                icon=_standard_item_type_meta("exams")[1],
                detail_url=_append_query_params(
                    reverse("exams:start_exam", kwargs={"slug": exam.slug}),
                    from_section="assigned-exams",
                    assigned_type=filter_type,
                ),
                assigned_at=(final_ctx.get("window_start") if has_ticket else exam.start_datetime) or exam.created_at,
                deadline=final_ctx.get("window_end") if has_ticket else exam.end_datetime,
                state=state,
                description=exam.description,
                extra=extra,
            )

    assignments_qs = (
        Assignment.objects.filter(
            course_id__in=course_ids,
            assigned_students=user,
        )
        .exclude(status__in=["inactive", "archived"])
        .select_related("course")
        .distinct()
        .order_by("-created_at")
    )
    counts["assignments"] = assignments_qs.count()
    if filter_type in {"all", "assignments"}:
        for assignment in assignments_qs:
            if not matches_search(assignment.title, assignment.description, assignment.course.title):
                continue

            if assignment.start_date and assignment.start_date > now:
                state = "upcoming"
            elif assignment.due_date and now > assignment.due_date and not assignment.allow_late:
                state = "closed"
            elif assignment.status not in {"published", "active"}:
                state = "closed"
            else:
                state = "open"

            append_item(
                category="assignments",
                title=assignment.title,
                kind=f"Sərbəst İş • {assignment.course.title}",
                icon=_standard_item_type_meta("assignments")[1],
                detail_url=_append_query_params(
                    reverse("assignments:assignment_detail", kwargs={"pk": assignment.id}),
                    from_section="assigned-exams",
                    assigned_type=filter_type,
                ),
                assigned_at=assignment.start_date or assignment.created_at,
                deadline=assignment.due_date,
                state=state,
                description=assignment.description,
            )

    labs_qs = (
        Lab.objects.filter(course_id__in=course_ids, status="published")
        .select_related("course")
        .prefetch_related("allowed_students")
        .order_by("-created_at")
    )
    assigned_labs = []
    for lab in labs_qs:
        # Use .all() to hit the prefetch_related cache (values_list bypasses it).
        allowed_student_ids = {s.id for s in lab.allowed_students.all()}
        allowed_group_names = _csv_to_lower_token_set(lab.allowed_groups)
        if not allowed_student_ids and not allowed_group_names:
            continue

        is_assigned = user.id in allowed_student_ids
        if not is_assigned and allowed_group_names:
            student_groups = course_groups.get(lab.course_id, set())
            is_assigned = bool(student_groups.intersection(allowed_group_names))

        if is_assigned:
            assigned_labs.append(lab)

    counts["labs"] = len(assigned_labs)
    if filter_type in {"all", "labs"}:
        for lab in assigned_labs:
            if not matches_search(lab.title, lab.description, lab.course.title):
                continue

            if lab.start_datetime and now < lab.start_datetime:
                state = "upcoming"
            elif lab.end_datetime and now > lab.end_datetime and not lab.allow_late_submission:
                state = "closed"
            else:
                state = "open"

            append_item(
                category="labs",
                title=lab.title,
                kind=f"Lab işi • {lab.course.title}",
                icon=_standard_item_type_meta("labs")[1],
                detail_url=_append_query_params(
                    reverse("labs:lab_detail", kwargs={"pk": lab.id}),
                    from_section="assigned-exams",
                    assigned_type=filter_type,
                ),
                assigned_at=lab.start_datetime or lab.created_at,
                deadline=lab.end_datetime,
                state=state,
                description=lab.description,
            )

    projects_qs = (
        Project.objects.filter(
            course_id__in=course_ids,
            assigned_students=user,
        )
        .exclude(status="archived")
        .select_related("course")
        .distinct()
        .order_by("-created_at")
    )
    counts["independent"] = projects_qs.count()
    if filter_type in {"all", "independent"}:
        for project in projects_qs:
            if not matches_search(project.title, project.description, project.course.title):
                continue

            if project.start_date and project.start_date > now:
                state = "upcoming"
            elif project.deadline and now > project.deadline:
                state = "closed"
            elif project.status != "active":
                state = "closed"
            else:
                state = "open"

            append_item(
                category="independent",
                title=project.title,
                kind=f"Kurs işi • {project.course.title}",
                icon=_standard_item_type_meta("independent")[1],
                detail_url=_append_query_params(
                    reverse("projects:project_detail", kwargs={"pk": project.id}),
                    from_section="assigned-exams",
                    assigned_type=filter_type,
                ),
                assigned_at=project.start_date or project.created_at,
                deadline=project.deadline,
                state=state,
                description=project.description,
            )

    items.sort(key=lambda item: item["sort_at"] or now, reverse=True)
    for item in items:
        item.pop("sort_at", None)

    counts["all"] = counts["exams"] + counts["assignments"] + counts["labs"] + counts["independent"]
    return items, counts, filter_type
