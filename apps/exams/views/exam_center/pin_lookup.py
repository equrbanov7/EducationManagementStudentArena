"""exam_center paketi — PIN axtarışı (canlı, debounce + modal).

* ``exam_center_pin_lookup``  — səhifə qabığı (axtarış qutusu + boş nəticə + modal).
* ``exam_center_pin_search``  — AJAX: ada/istifadəçi adına görə tələbələr (PIN YOX).
* ``exam_center_student_pins``— AJAX: seçilmiş tələbənin final biletləri + PIN-ləri
  (modal üçün). PIN yalnız icazəli imtahan mərkəzinə açılır; hər açılış audit-ə
  yazılır. Xam PIN URL/log-a düşmür.

PIN axtarışı imtahan mərkəzi RƏHBƏRİ VƏ İŞÇİSİ üçün açıqdır (monitor səviyyəli
funksiya). İcazə ``center_org_or_403`` (is_exam_center) ilə yoxlanır.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import OuterRef, Q, Subquery
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET

from apps.exams.models import ExamStudentPin, FinalExamTicket
from apps.exams.services.final_center import decrypt_ticket_pin
from apps.exams.services.student_pins import student_visible_pin
from core.audit import log_action
from core.constants import AuditAction

from ._shared import center_org_or_403

User = get_user_model()

_SEARCH_LIMIT = 15


@login_required
def exam_center_pin_lookup(request):
    """PIN axtarış səhifəsinin qabığı (data AJAX ilə gəlir)."""
    from django.urls import reverse

    organization = center_org_or_403(request)
    return render(
        request,
        "exams/exam_center/pin_lookup.html",
        {
            "organization": organization,
            "search_url": reverse("exams:exam_center_pin_search"),
            "detail_url_template": reverse("exams:exam_center_student_pins", kwargs={"student_id": 0}),
        },
    )


def _kafedra_subquery(organization):
    from apps.organizations.models import Membership

    return (
        Membership.objects.filter(
            user=OuterRef("pk"), organization=organization, is_active=True, scope_unit__isnull=False
        )
        .order_by("-role__level")
        .values("scope_unit__name")[:1]
    )


@login_required
@require_GET
def exam_center_pin_search(request):
    """Canlı axtarış: bu təşkilatda PIN-i olan tələbələr (ad/username üzrə)."""
    organization = center_org_or_403(request)
    query = (request.GET.get("q") or "").strip()

    # Final-center biletləri və wizard PIN-ləri ayrı modellərdə saxlanır.
    ticket_student_ids = FinalExamTicket.objects.filter(organization=organization).values("student_id")
    student_pin_ids = ExamStudentPin.objects.filter(exam__organization=organization).values("student_id")
    qs = User.objects.filter(Q(id__in=Subquery(ticket_student_ids)) | Q(id__in=Subquery(student_pin_ids))).annotate(
        kafedra=Subquery(_kafedra_subquery(organization)),
    )
    if query:
        qs = qs.filter(
            Q(username__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(email__icontains=query)
        )
    students = list(qs.order_by("first_name", "last_name", "username")[:_SEARCH_LIMIT])
    student_ids = [student.id for student in students]
    exam_ids_by_student = {student_id: set() for student_id in student_ids}
    for student_id, exam_id in FinalExamTicket.objects.filter(
        organization=organization, student_id__in=student_ids
    ).values_list("student_id", "exam_id"):
        exam_ids_by_student.setdefault(student_id, set()).add(exam_id)
    for student_id, exam_id in ExamStudentPin.objects.filter(
        exam__organization=organization, student_id__in=student_ids
    ).values_list("student_id", "exam_id"):
        exam_ids_by_student.setdefault(student_id, set()).add(exam_id)

    results = [
        {
            "id": u.id,
            "name": (u.get_full_name() or u.username),
            "username": u.username,
            "kafedra": getattr(u, "kafedra", "") or "",
            "ticket_count": len(exam_ids_by_student.get(u.id, set())),
        }
        for u in students
    ]
    return JsonResponse({"results": results})


@login_required
@require_GET
def exam_center_student_pins(request, student_id):
    """Seçilmiş tələbənin final biletləri + PIN-ləri (modal). Açılış audit-ə yazılır."""
    organization = center_org_or_403(request)
    student = User.objects.filter(id=student_id).first()
    if student is None:
        return JsonResponse({"error": "not_found"}, status=404)

    tickets = (
        FinalExamTicket.objects.filter(organization=organization, student=student)
        .select_related("exam", "exam__subject", "session", "session__room")
        .order_by("-created_at")
    )
    items = []
    revealed = 0
    ticket_exam_ids = set()
    for ticket in tickets:
        ticket_exam_ids.add(ticket.exam_id)
        pin = decrypt_ticket_pin(ticket)
        if pin:
            revealed += 1
        session = ticket.session
        subject = getattr(ticket.exam, "subject", None)
        items.append(
            {
                "exam_title": ticket.exam.title,
                "subject": (f"{subject.code} — {subject.name}" if subject else ""),
                "room": (session.room.name if session and session.room else ""),
                "scheduled_start": (
                    timezone.localtime(session.scheduled_start).strftime("%d.%m.%Y %H:%M") if session else ""
                ),
                "scheduled_end": (timezone.localtime(session.scheduled_end).strftime("%H:%M") if session else ""),
                "session_state": (session.state if session else ""),
                "status": ticket.status,
                "seat": ticket.seat_number,
                "language": ticket.get_language_display() if ticket.language else "",
                "pin": pin or "",
                "pin_available": bool(pin),
            }
        )

    student_pins = (
        ExamStudentPin.objects.filter(exam__organization=organization, student=student)
        .exclude(exam_id__in=ticket_exam_ids)
        .select_related("exam", "exam__subject")
        .order_by("-created_at")
    )
    for student_pin in student_pins:
        exam = student_pin.exam
        pin = student_visible_pin(exam, student)
        if pin:
            revealed += 1
        subject = getattr(exam, "subject", None)
        items.append(
            {
                "exam_title": exam.title,
                "subject": (f"{subject.code} — {subject.name}" if subject else ""),
                "room": "",
                "scheduled_start": (
                    timezone.localtime(exam.start_datetime).strftime("%d.%m.%Y %H:%M") if exam.start_datetime else ""
                ),
                "scheduled_end": (timezone.localtime(exam.end_datetime).strftime("%H:%M") if exam.end_datetime else ""),
                "session_state": "",
                "status": "assigned",
                "seat": "",
                "language": "",
                "pin": pin or "",
                "pin_available": bool(pin),
            }
        )

    if revealed:
        log_action(
            AuditAction.VIEW,
            user=request.user,
            organization=organization,
            reason=f"final_center_pin_lookup[{student.username}:{revealed}]",
            request=request,
            resource_type="final_exam_pin",
        )

    return JsonResponse(
        {
            "student": {"name": (student.get_full_name() or student.username), "username": student.username},
            "tickets": items,
        }
    )


__all__ = ["exam_center_pin_lookup", "exam_center_pin_search", "exam_center_student_pins"]
