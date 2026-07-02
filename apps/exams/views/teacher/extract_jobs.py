"""Asinxron mətn-çıxarma (P3): start + status endpointləri.

Sual importu / AI mənbə faylı üçün OCR-lı PDF-lər sinxron sorğunu dəqiqələrlə
tuta bilir. Bu endpointlər faylı ``TextExtractionJob``-a yazıb Celery task-ı
növbəyə qoyur; frontend statusu poll edib hazır mətni formaya doldurur.
Broker əlçatan olmadıqda start endpointi köhnə sinxron yola qayıdır
(graceful degradation) — davranış heç vaxt "işləmir"ə düşmür.
"""

import logging

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.translation import pgettext
from django.views.decorators.http import require_GET, require_POST

from apps.exams.models import TextExtractionJob
from apps.exams.services.access_policy import _ensure_teacher
from apps.exams.services.parsing import MAX_UPLOAD_BYTES, extract_text_from_upload
from apps.exams.tasks import run_text_extraction_job
from core.tenancy import get_request_organization
from core.upload_security import randomize_uploaded_filename

logger = logging.getLogger(__name__)


def _job_payload(job):
    payload = {"job_id": str(job.pk), "status": job.status}
    if job.status == TextExtractionJob.STATUS_SUCCESS:
        payload["text"] = job.text
    elif job.status == TextExtractionJob.STATUS_FAILED:
        payload["error"] = job.error
    if job.result_meta:
        payload["meta"] = job.result_meta
    return payload


def start_ai_generation_job(request, *, payload, uploaded, service_error_message):
    """P4: AI generasiya job-u yaradıb növbəyə qoyur (view-lar üçün ortaq).

    Eager/sinxron bitmiş halda KÖHNƏ cavab formasını qaytarır (servis result
    dict-i ilə birə-bir) — mövcud JS/testlər dəyişikliksiz işləyir; real
    broker-də isə 202 + job_id qaytarır və frontend poll edir.
    """
    from apps.exams.tasks import run_ai_generation_job

    source_name = ""
    if uploaded is not None:
        if uploaded.size and uploaded.size > MAX_UPLOAD_BYTES:
            return JsonResponse(
                {"ok": False, "error": pgettext("exams.view.extract_job.error", "file_too_large")},
                status=400,
            )
        source_name = (uploaded.name or "")[:255]
        randomize_uploaded_filename(uploaded)

    job = TextExtractionJob.objects.create(
        kind=TextExtractionJob.KIND_AI_GENERATE,
        organization=get_request_organization(request),
        user=request.user,
        source_name=source_name,
        file=uploaded,
        payload=payload,
    )

    try:
        run_ai_generation_job.delay(str(job.pk))
    except Exception:
        # Broker əlçatan deyil — task funksiyasını elə burada icra et
        # (köhnə sinxron davranış).
        logger.warning("start_ai_generation_job: növbə əlçatan deyil, sinxron fallback (job %s)", job.pk)
        run_ai_generation_job(str(job.pk))

    job.refresh_from_db()
    if job.status == TextExtractionJob.STATUS_SUCCESS:
        return JsonResponse({**job.result_meta, "text": job.text}, status=200)
    if job.status == TextExtractionJob.STATUS_FAILED:
        if job.result_meta.get("service_exception"):
            return JsonResponse({"ok": False, "error": service_error_message}, status=500)
        body = {**job.result_meta}
        body["ok"] = False
        if job.error:
            body["error"] = job.error
        return JsonResponse(body, status=400)
    return JsonResponse({"ok": True, "job_id": str(job.pk), "status": job.status}, status=202)


@login_required
@require_POST
def start_text_extraction(request):
    """Faylı qəbul edib çıxarma job-u yaradır → ``{job_id, status}``.

    Növbə mümkün olmazsa (broker xətası) mətni elə burada sinxron çıxarıb
    ``{status: "success", text}`` qaytarır — köhnə davranışla eyni.
    """
    _ensure_teacher(request.user)

    uploaded = request.FILES.get("source_file")
    if uploaded is None:
        return JsonResponse(
            {"ok": False, "error": pgettext("exams.view.extract_job.error", "file_required")},
            status=400,
        )

    if uploaded.size and uploaded.size > MAX_UPLOAD_BYTES:
        return JsonResponse(
            {"ok": False, "error": pgettext("exams.view.extract_job.error", "file_too_large")},
            status=400,
        )

    source_name = (uploaded.name or "")[:255]
    randomize_uploaded_filename(uploaded)
    # Workbench birbaşa import yolu düstur-şəkil stash-ı da istəyir (P3-b).
    payload = {"stash_math": True} if request.POST.get("stash_math") == "1" else {}
    job = TextExtractionJob.objects.create(
        organization=get_request_organization(request),
        user=request.user,
        source_name=source_name,
        file=uploaded,
        payload=payload,
    )

    try:
        run_text_extraction_job.delay(str(job.pk))
    except Exception:
        # Broker əlçatan deyil — köhnə sinxron davranışa qayıdırıq ki, müəllim
        # bloklanmasın. Job qeydini nəticə ilə yeniləyirik (audit üçün).
        logger.warning("start_text_extraction: növbə əlçatan deyil, sinxron fallback (job %s)", job.pk)
        try:
            uploaded.seek(0)
            uploaded.name = source_name
            text = extract_text_from_upload(uploaded)
        except Exception as exc:
            job.status = TextExtractionJob.STATUS_FAILED
            job.error = str(exc)
            job.save(update_fields=["status", "error"])
            job.file.delete(save=True)
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        job.status = TextExtractionJob.STATUS_SUCCESS
        job.text = text
        job.save(update_fields=["status", "text"])
        job.file.delete(save=True)
        return JsonResponse({"ok": True, **_job_payload(job)})

    return JsonResponse({"ok": True, **_job_payload(job)}, status=202)


@login_required
@require_GET
def text_extraction_status(request, job_id):
    """Job statusu — yalnız sahibi üçün (tenant RLS + user filtri)."""
    _ensure_teacher(request.user)
    job = get_object_or_404(TextExtractionJob, pk=job_id, user=request.user)
    return JsonResponse({"ok": True, **_job_payload(job)})


def start_export_job(request, *, export_name, params):
    """C2: böyük export üçün job yaradır. Eager/sinxron-fallback halda faylı
    dərhal attachment kimi qaytarır (köhnə UX); real broker-də gözləmə
    səhifəsinə yönləndirir (poll → avtomatik endirmə)."""
    from django.contrib import messages
    from django.http import HttpResponseRedirect
    from django.shortcuts import redirect

    from apps.exams.tasks import run_export_job

    job = TextExtractionJob.objects.create(
        kind=TextExtractionJob.KIND_EXPORT,
        organization=get_request_organization(request),
        user=request.user,
        payload={"export": export_name, "params": params},
    )

    try:
        run_export_job.delay(str(job.pk))
    except Exception:
        logger.warning("start_export_job: növbə əlçatan deyil, sinxron fallback (job %s)", job.pk)
        run_export_job(str(job.pk))

    job.refresh_from_db()
    if job.status == TextExtractionJob.STATUS_SUCCESS:
        return _serve_export_file(job)
    if job.status == TextExtractionJob.STATUS_FAILED:
        if job.error == "empty_export":
            messages.warning(request, pgettext("exams.view.export_job.error", "empty_export"))
        else:
            messages.error(request, pgettext("exams.view.export_job.error", "export_failed"))
        fallback = request.META.get("HTTP_REFERER") or "/"
        return HttpResponseRedirect(fallback)
    return redirect("exams:export_job_waiting", job_id=job.pk)


def _serve_export_file(job):
    from django.http import FileResponse, Http404

    if job.status != TextExtractionJob.STATUS_SUCCESS or not job.result_file:
        raise Http404
    meta = job.result_meta or {}
    response = FileResponse(
        job.result_file.open("rb"),
        as_attachment=True,
        filename=meta.get("filename") or "export",
    )
    if meta.get("content_type"):
        response["Content-Type"] = meta["content_type"]
    return response


@login_required
@require_GET
def export_job_waiting(request, job_id):
    """Gözləmə səhifəsi — status poll edib hazır olanda avtomatik endirir."""
    from django.shortcuts import render
    from django.urls import reverse

    _ensure_teacher(request.user)
    job = get_object_or_404(TextExtractionJob, pk=job_id, user=request.user)
    return render(
        request,
        "exams/teacher/export_waiting.html",
        {
            "job": job,
            "status_url": reverse("exams:text_extraction_status", kwargs={"job_id": job.pk}),
            "download_url": reverse("exams:export_job_download", kwargs={"job_id": job.pk}),
        },
    )


@login_required
@require_GET
def export_job_download(request, job_id):
    """Hazır export faylını endirir — yalnız sahibi üçün."""
    _ensure_teacher(request.user)
    job = get_object_or_404(TextExtractionJob, pk=job_id, user=request.user)
    return _serve_export_file(job)
