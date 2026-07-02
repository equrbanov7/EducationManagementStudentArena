"""live_exam host paketi — session."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext

from apps.audit.public import log_action
from apps.exams.models import Exam
from apps.exams.public import is_teacher_user
from apps.live_exam.models import LiveSession
from apps.live_exam.services import finish_session
from core.constants import AuditAction

from ._shared import (
    _ensure_host_org_permission,
    _host_session_context,
)
from .constants import (
    LIVE_ACTIVE_STATES,
)


@login_required
def live_create_session_by_slug(request, slug):
    exam = get_object_or_404(Exam.objects.select_related("organization"), slug=slug)

    is_superadmin = request.user.is_superuser or getattr(request.user, "is_superadmin", False)

    if not is_superadmin and not is_teacher_user(request.user):
        raise Http404(pgettext("live_exam.view.permission", "host_teacher_only"))

    if not is_superadmin and exam.author != request.user:
        raise Http404(pgettext("live_exam.view.permission", "host_author_only"))

    _ensure_host_org_permission(request, exam.organization)

    if not exam.is_active:
        messages.warning(request, pgettext("live_exam.view.message", "exam_must_be_active_before_live"))
        return redirect(reverse("exams:teacher_exam_detail", kwargs={"slug": exam.slug}))

    force_new_session = str(request.GET.get("force_new") or "").strip().lower() in {"1", "true", "yes", "on"}
    probe_only = str(request.GET.get("probe") or "").strip().lower() in {"1", "true", "yes", "on"}
    active_sessions = LiveSession.objects.filter(
        exam=exam,
        host_user=request.user,
        state__in=LIVE_ACTIVE_STATES,
    ).order_by("-created_at", "-id")
    active_session = active_sessions.first()

    if probe_only:
        if active_session:
            presentation_url = reverse("liveExam:host_presentation", kwargs={"pin": active_session.pin})
            new_url = f"{reverse('liveExam:create_session_slug', kwargs={'slug': exam.slug})}?force_new=1"
            return JsonResponse(
                {
                    "active": True,
                    "pin": active_session.pin,
                    "created": timezone.localtime(active_session.created_at).strftime("%d.%m.%Y %H:%M"),
                    "return_url": f"{presentation_url}?controls=1",
                    "new_url": new_url,
                }
            )
        return JsonResponse({"active": False})

    if active_session and not force_new_session:
        presentation_url = reverse("liveExam:host_presentation", kwargs={"pin": active_session.pin})
        return redirect(f"{presentation_url}?controls=1")

    if force_new_session:
        for old_session in active_sessions:
            finish_session(old_session)

    session = LiveSession.objects.create(exam=exam, host_user=request.user)
    log_action(
        action=AuditAction.CREATE,
        user=request.user,
        organization=exam.organization,
        obj=session,
        new_values={"exam": str(exam.pk), "pin": session.pin},
        request=request,
    )
    presentation_url = reverse("liveExam:host_presentation", kwargs={"pin": session.pin})
    return redirect(f"{presentation_url}?controls=1")


@login_required
def live_host_lobby(request, pin):
    session = get_object_or_404(LiveSession.objects.select_related("exam__organization"), pin=pin)

    if session.host_user != request.user:
        raise Http404(pgettext("live_exam.view.permission", "not_allowed"))

    _ensure_host_org_permission(request, session.exam.organization)

    context = _host_session_context(request, session)
    return render(request, "liveExam/host_lobby.html", context)


@login_required
def live_host_presentation(request, pin):
    session = get_object_or_404(LiveSession.objects.select_related("exam__organization"), pin=pin)

    if session.host_user != request.user:
        raise Http404(pgettext("live_exam.view.permission", "not_allowed"))

    _ensure_host_org_permission(request, session.exam.organization)

    controls_enabled = str(request.GET.get("controls") or "").strip().lower() in {"1", "true", "yes", "on"}
    context = _host_session_context(request, session, auto_fullscreen="1" if request.GET.get("autofs") == "1" else "0")
    context["presentation_controls"] = controls_enabled
    return render(request, "liveExam/host_presentation.html", context)
