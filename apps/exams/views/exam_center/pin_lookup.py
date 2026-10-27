"""exam_center paketi — PIN axtarışı (canlı, debounce + modal).

* Səhifə qabığı kabinet bölməsidir (``?section=exam-center-pins``,
  ``_pin_lookup_body.html``); müstəqil ``center/pin-lookup/`` səhifəsi URL auditi
  A12 (2026-10-10) ilə silindi.
* ``exam_center_pin_search``  — AJAX: ad/soyad/ata adı/istifadəçi adına görə tələbələr (PIN YOX).
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
from django.utils import timezone
from django.views.decorators.http import require_GET

from apps.exams.domain.final_center import TICKET_STATUS_ASSIGNED
from apps.exams.models import ExamStudentPin, FinalExamTicket
from apps.exams.services.center_exams import active_center_kinds, exam_kind, kind_label
from apps.exams.services.final_center import decrypt_ticket_pin
from apps.exams.services.student_pins import decrypt_student_pin_row
from apps.organizations.public import organization_role_user_queryset
from core.audit import log_action
from core.constants import AuditAction
from core.person_names import user_display_name_with_patronymic
from core.roles import ProfileRole
from core.search_text import tolerant_q

from ._shared import center_org_or_403

User = get_user_model()

_SEARCH_LIMIT_DEFAULT = 15
_SEARCH_LIMIT_MAX = 50


def _kafedra_subquery(organization):
    from apps.organizations.models import Membership

    return (
        Membership.objects.filter(
            user=OuterRef("pk"), organization=organization, is_active=True, scope_unit__isnull=False
        )
        .order_by("-role__level")
        .values("scope_unit__name")[:1]
    )


def _pin_holder_student_queryset(organization):
    """Return active org students who have at least one final/wizard PIN row."""
    ticket_student_ids = FinalExamTicket.objects.filter(organization=organization).values("student_id")
    student_pin_ids = ExamStudentPin.objects.filter(exam__organization=organization).values("student_id")
    users_with_pins = User.objects.filter(
        Q(id__in=Subquery(ticket_student_ids)) | Q(id__in=Subquery(student_pin_ids)),
        is_active=True,
    )
    return organization_role_user_queryset(
        organization,
        {ProfileRole.STUDENT, ProfileRole.LEAD_STUDENT},
        queryset=users_with_pins,
    )


def _patronymic(user) -> str:
    """Profildəki ata adı (yer tutucular «-» boş sayılır); profil yoxdursa ``""``."""
    profile = getattr(user, "profile", None)
    return getattr(profile, "patronymic_display", "") if profile is not None else ""


@login_required
@require_GET
def exam_center_pin_search(request):
    """Canlı axtarış: bu təşkilatda PIN-i olan tələbələr (ad/username üzrə).

    Lazy səhifələnən (offset/limit + has_more) — panel açılanda ilk səhifə
    dərhal göstərilir, aşağı sürüşdürdükcə növbəti səhifə gəlir (bütün
    PIN-li tələbələr bir dəfəyə yüklənmir).
    """
    organization = center_org_or_403(request)
    query = (request.GET.get("q") or "").strip()
    try:
        offset = max(0, int(request.GET.get("offset", 0)))
    except (TypeError, ValueError):
        offset = 0
    try:
        limit = int(request.GET.get("limit", _SEARCH_LIMIT_DEFAULT))
    except (TypeError, ValueError):
        limit = _SEARCH_LIMIT_DEFAULT
    limit = max(1, min(limit, _SEARCH_LIMIT_MAX))

    qs = _pin_holder_student_queryset(organization).annotate(kafedra=Subquery(_kafedra_subquery(organization)))
    # Sahib 2026-10-26: ata adı siyahıda görünür və axtarılır (eyni adlı tələbələr ayrılsın).
    search_q = tolerant_q(query, ("username", "first_name", "last_name", "profile__patronymic", "email"))
    if search_q is not None:
        qs = qs.filter(search_q)
    qs = qs.select_related("profile")
    window = list(qs.order_by("first_name", "last_name", "username")[offset : offset + limit + 1])
    has_more = len(window) > limit
    students = window[:limit]
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
            "name": user_display_name_with_patronymic(u),
            "patronymic": _patronymic(u),
            "username": u.username,
            "kafedra": getattr(u, "kafedra", "") or "",
            "ticket_count": len(exam_ids_by_student.get(u.id, set())),
        }
        for u in students
    ]
    return JsonResponse({"results": results, "has_more": has_more})


def _window_labels(start, end):
    """Başlanğıc/bitmə etiketləri — bitmə BAŞQA GÜNDƏDİRSƏ tarix də yazılır.

    2026-09-14 (W3 `w3sweep` brauzer süpürgəsi): PIN axtarışında 14.09→30.10
    pəncərəsi «14.09.2026 00:00–23:00» görünürdü (bitmə həmişə yalnız saat idi).
    """
    if not start:
        return "", ""
    start_local = timezone.localtime(start)
    if not end:
        return start_local.strftime("%d.%m.%Y %H:%M"), ""
    end_local = timezone.localtime(end)
    end_fmt = "%H:%M" if end_local.date() == start_local.date() else "%d.%m.%Y %H:%M"
    return start_local.strftime("%d.%m.%Y %H:%M"), end_local.strftime(end_fmt)


def _ticket_status_label(status):
    """Nişan xam açar («assigned») deyil, tərcümə olunmuş etiket olsun (W3 `w3sweep`)."""
    labels = dict(FinalExamTicket.STATUS_CHOICES)
    return str(labels.get(status, status))


def _device_change_urls(organization, student) -> dict:
    """``{exam_id: (url, təsdiq_gözləyir)}`` — tələbənin cihaza bağlı, davam edən final cəhdləri.

    Təhlükəsizlik dizaynı 2026-10-08: mərkəz tələbənin cihazını buradan dəyişə bilir
    (``exam_center_final_device_change``). İki sorğu, imtahan sayından asılı deyil.
    """
    from django.urls import reverse

    from apps.exams.models import ExamAttempt
    from apps.exams.services.final_center.device_binding import device_change_states

    active = dict(
        ExamAttempt.objects.filter(
            user=student,
            exam__organization=organization,
            exam__exam_type_extended__in=sorted(active_center_kinds()),
            status__in=("draft", "in_progress"),
            is_trial=False,
        ).values_list("exam_id", "id")
    )
    states = device_change_states(active.values()) if active else {}
    return {
        exam_id: (
            reverse("exams:exam_center_final_device_change", kwargs={"attempt_id": attempt_id}),
            states[attempt_id],
        )
        for exam_id, attempt_id in active.items()
        if attempt_id in states
    }


@login_required
@require_GET
def exam_center_student_pins(request, student_id):
    """Seçilmiş tələbənin final biletləri + PIN-ləri (modal). Açılış audit-ə yazılır."""
    organization = center_org_or_403(request)
    student = _pin_holder_student_queryset(organization).select_related("profile").filter(id=student_id).first()
    if student is None:
        return JsonResponse({"error": "not_found"}, status=404)
    device_changes = _device_change_urls(organization, student)

    tickets = (
        FinalExamTicket.objects.filter(organization=organization, student=student)
        .select_related("exam", "exam__subject", "session", "session__room")
        .order_by("-created_at")
    )
    items = []
    revealed = 0
    ticket_exam_ids = set()
    # Sahib 2026-10-27: zal biletli imtahanda tələbə KABİNET PIN-i (``ExamStudentPin``) ilə girir — zal monitoru da
    # onu göstərir. Biletin köhnə öz PIN-i boşdursa səhifə «PIN yoxdur» deyirdi, halbuki tələbənin PIN-i var idi.
    cabinet_pins = {
        row.exam_id: row
        for row in ExamStudentPin.objects.filter(exam__organization=organization, student=student).only(
            "exam_id", "pin_cipher"
        )
    }
    for ticket in tickets:
        ticket_exam_ids.add(ticket.exam_id)
        pin = decrypt_student_pin_row(cabinet_pins.get(ticket.exam_id)) or decrypt_ticket_pin(ticket)
        if pin:
            revealed += 1
        session = ticket.session
        subject = getattr(ticket.exam, "subject", None)
        scheduled_start, scheduled_end = _window_labels(
            session.scheduled_start if session else None, session.scheduled_end if session else None
        )
        items.append(
            {
                "exam_title": ticket.exam.title,
                # 2026-10-20: midterm də zal axınındadır — mərkəz növü etiketi (Final / Midterm).
                "exam_kind": exam_kind(ticket.exam),
                "exam_kind_label": kind_label(exam_kind(ticket.exam)),
                "subject": (f"{subject.code} — {subject.name}" if subject else ""),
                "room": (session.room.name if session and session.room else ""),
                "scheduled_start": scheduled_start,
                "scheduled_end": scheduled_end,
                "session_state": (session.state if session else ""),
                "status": _ticket_status_label(ticket.status),
                "status_key": ticket.status,
                "seat": ticket.seat_number,
                "language": ticket.get_language_display() if ticket.language else "",
                "pin": pin or "",
                "pin_available": bool(pin),
                "device_change_url": device_changes.get(ticket.exam_id, ("", False))[0],
                "device_change_pending": device_changes.get(ticket.exam_id, ("", False))[1],
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
        # 2026-10-13 (gecə): sətir artıq yüklənib — imtahan başına ayrıca PIN sorğusu (N+1) yoxdur.
        pin = decrypt_student_pin_row(student_pin)
        if pin:
            revealed += 1
        subject = getattr(exam, "subject", None)
        scheduled_start, scheduled_end = _window_labels(exam.start_datetime, exam.end_datetime)
        items.append(
            {
                "exam_title": exam.title,
                "exam_kind": exam_kind(exam),
                "exam_kind_label": kind_label(exam_kind(exam)),
                "subject": (f"{subject.code} — {subject.name}" if subject else ""),
                "room": "",
                "scheduled_start": scheduled_start,
                "scheduled_end": scheduled_end,
                "session_state": "",
                "status": _ticket_status_label(TICKET_STATUS_ASSIGNED),
                "status_key": TICKET_STATUS_ASSIGNED,
                "seat": "",
                "language": "",
                "pin": pin or "",
                "pin_available": bool(pin),
                "device_change_url": device_changes.get(exam.pk, ("", False))[0],
                "device_change_pending": device_changes.get(exam.pk, ("", False))[1],
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
            "student": {
                "name": user_display_name_with_patronymic(student),
                "patronymic": _patronymic(student),
                "username": student.username,
            },
            "tickets": items,
        }
    )


__all__ = ["exam_center_pin_search", "exam_center_student_pins"]
