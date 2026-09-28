"""
Labs Views - Lab CRUD Operations
Lab yaratma, redaktə, silmə və yayımlama
"""

import logging
from collections import defaultdict

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext
from django.views.decorators.http import require_http_methods, require_POST

from apps.courses.models import CourseMembership
from core.helpers import parse_form_datetime

from ...models import Lab
from ..shared._helpers import (
    _get_tenant_course_or_404,
    _get_tenant_lab_or_404,
    _normalize_extensions,
    _parse_max_size_mb,
    _validate_and_prepare_lab_upload,
)

logger = logging.getLogger(__name__)
User = get_user_model()

# Yaradılış/redaktə modalında seçilə bilən statuslar (publish_lab ilə eyni məna).
_EDITABLE_STATUSES = {"draft", "published", "archived"}


def _course_student_groups(course):
    """Kursun tələbə üzvləri: (bütün tələbə id-ləri, casefold qrup → kanonik ad, casefold qrup → id-lər)."""
    student_ids = set()
    canonical = {}
    members = defaultdict(set)
    for user_id, group_name in CourseMembership.objects.filter(course=course, role="student").values_list(
        "user_id", "group_name"
    ):
        student_ids.add(user_id)
        name = (group_name or "").strip()
        if name:
            canonical.setdefault(name.casefold(), name)
            members[name.casefold()].add(user_id)
    return student_ids, canonical, members


def _resolve_lab_targets(course, raw_groups, raw_student_ids):
    """Modalın ``group_names[]`` + ``student_ids[]`` → (allowed_groups, allowed_students id-ləri).

    Lab girişi «qrup VƏ YA fərdi tələbə» birləşməsidir (`Lab.can_student_access`).
    Əvvəl işarələnmiş hər qrup `allowed_groups`-a yazılırdı → qrupdan 2 tələbə
    seçilsə də bütün qrup giriş alırdı (qismən seçim mümkün deyildi). İndi
    (2026-09-28, assignments/projects ilə eyni qayda):

    * tələbə seçilməyibsə — işarələnmiş qruplar bütövlükdə;
    * tələbə seçilibsə — yalnız BÜTÜN tələbələri seçilmiş qrup qrup kimi
      qalır (sonradan qoşulan da görür), qalanları fərdi tələbə kimi yazılır.

    Yalnız bu kursun tələbə üzvləri qəbul olunur (başqa kurs/tenant id-si atılır).
    """
    course_student_ids, canonical, members = _course_student_groups(course)

    selected_groups = []
    for raw in raw_groups:
        key = (raw or "").strip().casefold()
        if key in canonical and key not in selected_groups:
            selected_groups.append(key)

    selected_students = {int(sid) for sid in raw_student_ids if str(sid).strip().isdigit()} & course_student_ids

    if selected_students:
        kept_groups = [key for key in selected_groups if members[key] and members[key] <= selected_students]
    else:
        kept_groups = selected_groups

    covered = set().union(*(members[key] for key in kept_groups)) if kept_groups else set()
    allowed_groups = ",".join(canonical[key] for key in kept_groups)
    return allowed_groups, selected_students - covered


def _lab_edit_target_payload(lab):
    """Redaktə modalı üçün: göstəriləcək qruplar + həmin qruplarda girişi OLMAYAN tələbələr.

    Modal qrupu işarələyəndə bütün tələbələrini avtomatik seçir;
    ``group_excluded_student_ids`` olmadan qismən seçim toxunulmamış
    saxlamada bütün qrupa genişlənirdi.
    """
    _all_ids, canonical, members = _course_student_groups(lab.course)
    allowed_keys = {g.casefold() for g in lab.get_allowed_groups_list()}
    student_ids = set(lab.allowed_students.values_list("id", flat=True))

    display_keys = {key for key in canonical if key in allowed_keys or members[key] & student_ids}
    excluded = set()
    for key in display_keys:
        if key not in allowed_keys:
            excluded |= members[key] - student_ids
    return sorted(canonical[key] for key in display_keys), sorted(student_ids), sorted(excluded)


def _local_input_value(value):
    """``datetime-local`` dəyəri layihə vaxt qurşağında (UTC ``strftime`` hər
    toxunulmamış saxlamada tarixi −4 saat sürüşdürürdü)."""
    if not value:
        return ""
    return timezone.localtime(value).strftime("%Y-%m-%dT%H:%M")


@login_required
@require_POST
def create_lab(request, course_id):
    """Lab yarat"""

    course = _get_tenant_course_or_404(request, course_id)

    if course.owner != request.user:
        return JsonResponse(
            {"success": False, "error": pgettext("labs.view.permission", "permission_denied")}, status=403
        )

    try:
        allowed_extensions = _normalize_extensions(request.POST.get("allowed_extensions", ""))
        max_file_size_mb = _parse_max_size_mb(request.POST.get("max_file_size_mb", 50), fallback=50)
        teacher_file = request.FILES.get("teacher_files")
        if teacher_file is not None:
            _validate_and_prepare_lab_upload(
                teacher_file,
                allowed_extensions=allowed_extensions,
                max_size_mb=max_file_size_mb,
            )

        # Seçilmiş qruplar və tələbələr → kursa məxsus hədəflər
        allowed_groups, student_ids = _resolve_lab_targets(
            course, request.POST.getlist("group_names[]"), request.POST.getlist("student_ids[]")
        )

        # Audit 2026-09-13 backend F-07 (2026-09-14): lab + icazəli tələbələr (M2M) + fayl
        # birlikdə — istisna `except`-ə çıxır (500), yarımçıq lab qalmır.
        with transaction.atomic():
            lab = _create_lab_with_students(
                request, course, allowed_groups, student_ids, allowed_extensions, max_file_size_mb, teacher_file
            )

        # 2026-09-28: modalın «Status» seçimi nəzərə alınır — «Yayımla» seçilibsə
        # `publish_lab` kimi təyin olunanlara bildiriş gedir (əvvəl həmişə draft idi).
        if lab.status == "published":
            from apps.notifications.public import get_lab_assigned_user_ids, notify_task_assignment

            notify_task_assignment(task=lab, user_ids=get_lab_assigned_user_ids(lab), task_kind="lab")

        return JsonResponse({"success": True, "lab_id": lab.id})

    except ValidationError as exc:
        return JsonResponse({"success": False, "error": exc.messages[0]}, status=400)
    except Exception:
        logger.exception("Unexpected error in create_lab")
        return JsonResponse({"success": False, "error": "An unexpected error occurred."}, status=500)


def _create_lab_with_students(
    request, course, allowed_groups, student_ids, allowed_extensions, max_file_size_mb, teacher_file
):
    """`create_lab`-ın yazı hissəsi (çağıran ``transaction.atomic`` içindədir)."""
    status = request.POST.get("status")
    lab = Lab.objects.create(
        course=course,
        title=request.POST.get("title"),
        description=request.POST.get("description", ""),
        start_datetime=parse_form_datetime(request.POST.get("start_datetime")),
        end_datetime=parse_form_datetime(request.POST.get("end_datetime")),
        max_score=request.POST.get("max_score", 100),
        max_attempts=request.POST.get("max_attempts", 1),  # Cəhd sayı
        status="published" if status == "published" else "draft",
        questions_per_student=request.POST.get("questions_per_student", 0),
        allow_late_submission=request.POST.get("allow_late_submission") == "on",
        late_penalty_percent=request.POST.get("late_penalty_percent", 0),
        allow_file_upload=request.POST.get("allow_file_upload") == "on",
        allow_link_submission=request.POST.get("allow_link_submission") == "on",
        max_file_size_mb=max_file_size_mb,
        allowed_extensions=",".join(ext.lstrip(".") for ext in sorted(allowed_extensions)),
        teacher_instructions=request.POST.get("teacher_instructions", ""),
        allowed_groups=allowed_groups,
        created_by=request.user,
    )

    if student_ids:
        lab.allowed_students.set(User.objects.filter(pk__in=student_ids))

    if teacher_file is not None:
        lab.teacher_files = teacher_file
        lab.save()

    return lab


@login_required
@require_http_methods(["GET", "POST"])
@transaction.atomic
def edit_lab(request, pk):
    """Lab redaktə et"""
    lab = _get_tenant_lab_or_404(request, pk)

    if lab.created_by != request.user:
        return JsonResponse(
            {"success": False, "error": pgettext("labs.view.permission", "permission_denied")}, status=403
        )

    if request.method == "GET":
        # Göstəriləcək qruplar, fərdi tələbələr və qrupda girişi olmayanlar
        group_names, student_ids, excluded_ids = _lab_edit_target_payload(lab)

        data = {
            "id": lab.id,
            "title": lab.title or "",
            "description": lab.description or "",
            "start_datetime": _local_input_value(lab.start_datetime),
            "end_datetime": _local_input_value(lab.end_datetime),
            "max_score": lab.max_score or 100,
            "max_attempts": getattr(lab, "max_attempts", 1) or 1,
            "status": lab.status or "draft",
            "questions_per_student": lab.questions_per_student or 0,
            "allow_late_submission": lab.allow_late_submission,
            "late_penalty_percent": lab.late_penalty_percent or 0,
            "allow_file_upload": lab.allow_file_upload,
            "allow_link_submission": lab.allow_link_submission,
            "max_file_size_mb": lab.max_file_size_mb or 50,
            "allowed_extensions": lab.allowed_extensions or "zip,pdf,docx,png,jpg,txt,py,java,cpp",
            "teacher_instructions": lab.teacher_instructions or "",
            "teacher_files_url": lab.teacher_files.url if lab.teacher_files else None,
            "group_names": group_names,
            "group_excluded_student_ids": excluded_ids,
            "student_ids": student_ids,
        }
        return JsonResponse({"success": True, "data": data})

    # POST - yenilə
    try:
        previous_status = lab.status
        from apps.notifications.public import get_lab_assigned_user_ids, notify_task_assignment

        previous_recipient_ids = get_lab_assigned_user_ids(lab)
        allowed_groups, student_ids = _resolve_lab_targets(
            lab.course, request.POST.getlist("group_names[]"), request.POST.getlist("student_ids[]")
        )

        lab.title = request.POST.get("title")
        lab.description = request.POST.get("description", "")
        lab.start_datetime = parse_form_datetime(request.POST.get("start_datetime")) or None
        lab.end_datetime = parse_form_datetime(request.POST.get("end_datetime")) or None
        lab.max_score = int(request.POST.get("max_score", 100) or 100)
        new_status = request.POST.get("status")
        if new_status in _EDITABLE_STATUSES:
            lab.status = new_status

        # max_attempts field varsa
        if hasattr(lab, "max_attempts"):
            lab.max_attempts = int(request.POST.get("max_attempts", 1) or 1)

        lab.questions_per_student = int(request.POST.get("questions_per_student", 0) or 0)
        lab.allow_late_submission = request.POST.get("allow_late_submission") == "on"
        lab.late_penalty_percent = int(request.POST.get("late_penalty_percent", 0) or 0)
        lab.allow_file_upload = request.POST.get("allow_file_upload") == "on"
        lab.allow_link_submission = request.POST.get("allow_link_submission") == "on"
        lab.max_file_size_mb = _parse_max_size_mb(request.POST.get("max_file_size_mb", 50), fallback=50)
        lab.allowed_extensions = request.POST.get("allowed_extensions", "")
        lab.teacher_instructions = request.POST.get("teacher_instructions", "")
        lab.allowed_groups = allowed_groups

        teacher_file = request.FILES.get("teacher_files")
        if teacher_file is not None:
            allowed_extensions = _normalize_extensions(lab.allowed_extensions)
            _validate_and_prepare_lab_upload(
                teacher_file,
                allowed_extensions=allowed_extensions,
                max_size_mb=lab.max_file_size_mb,
            )
            lab.teacher_files = teacher_file

        lab.save()

        # Update allowed_students M2M relation (yalnız kursun tələbələri)
        lab.allowed_students.set(User.objects.filter(pk__in=student_ids))

        current_recipient_ids = get_lab_assigned_user_ids(lab)
        should_notify_all = previous_status != "published" and lab.status == "published"
        new_recipient_ids = (
            current_recipient_ids if should_notify_all else (current_recipient_ids - previous_recipient_ids)
        )
        if new_recipient_ids and lab.status == "published":
            notify_task_assignment(
                task=lab,
                user_ids=new_recipient_ids,
                task_kind="lab",
            )

        return JsonResponse({"success": True})

    except ValidationError as exc:

        transaction.set_rollback(True)
        return JsonResponse({"success": False, "error": exc.messages[0]}, status=400)
    except Exception:
        transaction.set_rollback(True)
        logger.exception("Unexpected error in edit_lab")
        return JsonResponse({"success": False, "error": "An unexpected error occurred."}, status=500)


@login_required
@require_POST
def delete_lab(request, pk):
    """Lab sil"""
    lab = _get_tenant_lab_or_404(request, pk)

    if lab.created_by != request.user:
        return JsonResponse(
            {"success": False, "error": pgettext("labs.view.permission", "permission_denied")}, status=403
        )

    course_id = lab.course.id
    lab.delete()
    messages.success(request, pgettext("labs.view.message", "lab_deleted"))
    return JsonResponse(
        {
            "success": True,
            "redirect_url": reverse("courses:course_dashboard", args=[course_id]),
        }
    )


@login_required
@require_POST
def publish_lab(request, pk):
    """Lab yayımla"""
    lab = _get_tenant_lab_or_404(request, pk)

    if lab.created_by != request.user:
        return JsonResponse(
            {"success": False, "error": pgettext("labs.view.permission", "permission_denied")}, status=403
        )

    lab.status = "published"
    lab.save()
    from apps.notifications.public import get_lab_assigned_user_ids, notify_task_assignment

    notify_task_assignment(
        task=lab,
        user_ids=get_lab_assigned_user_ids(lab),
        task_kind="lab",
    )
    messages.success(request, pgettext("labs.view.message", "lab_published"))
    return JsonResponse({"success": True})
