"""
Celery tasks for the exams app.

Currently hosts the supervision resume-window sweep: any attempt that a teacher
(or an automatic recovery flow) put back into the ``resumed`` state, but where
the student never actually returned within the per-exam resume window, is
auto-finished by the backend so it does not linger in the supervision monitor.
"""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="exams.expire_stale_resumed_attempts")
def expire_stale_resumed_attempts():
    """
    Finish supervised attempts whose resume window has elapsed without the
    student returning.  Runs globally across all organizations; tenant
    isolation is preserved because each finished attempt records its incident
    under its own ``exam.organization``.

    Returns the number of attempts that were auto-finished.
    """
    # Imported lazily so the task module stays import-safe even when the app
    # registry is not fully loaded (e.g. during Celery autodiscovery).
    from apps.exams.services.supervision import sweep_expired_resume_windows
    from core.rls import bypass_rls
    from core.rls_pooling import rls_worker_atomic

    # Global periodic sweep has no org_id argument; it intentionally scans every
    # tenant and each write records the attempt's own organization.
    with rls_worker_atomic(), bypass_rls():
        expired = sweep_expired_resume_windows()
    if expired:
        logger.info("expire_stale_resumed_attempts: auto-finished %d attempt(s)", expired)
    return expired


@shared_task(
    name="exams.run_text_extraction_job",
    time_limit=900,
    soft_time_limit=840,
)
def run_text_extraction_job(job_id):
    """P3 (2026-07-02): yüklənmiş fayldan mətn çıxarmanı worker-də icra edir.

    OCR-lı PDF-lər dəqiqələr çəkə bilər — sinxron sorğuda parse etmək əvəzinə
    view job yaradıb bu task-ı növbəyə qoyur, frontend statusu poll edir.
    Fayl nəticə yazılan kimi silinir (müvəqqəti saxlama).
    """
    from django.utils import timezone

    from apps.exams.models import TextExtractionJob
    from apps.exams.services.parsing import extract_text_from_upload
    from core.rls import bypass_rls
    from core.rls_pooling import rls_worker_atomic

    # Sistem worker-i yalnız PK alır — istənilən tenantın job-unu bypass ilə
    # oxumalıdır (warm_session_settings_cache pattern-i).
    with rls_worker_atomic(), bypass_rls():
        try:
            job = TextExtractionJob.objects.get(pk=job_id)
        except TextExtractionJob.DoesNotExist:
            logger.warning("run_text_extraction_job: job %s tapılmadı", job_id)
            return "missing"

        if job.status not in {TextExtractionJob.STATUS_PENDING, TextExtractionJob.STATUS_PROCESSING}:
            return job.status

        job.status = TextExtractionJob.STATUS_PROCESSING
        job.started_at = timezone.now()
        job.save(update_fields=["status", "started_at"])

    meta = {}
    try:
        import os as _os

        from django.core.files.base import File

        with job.file.open("rb") as fh:
            # extract_text_from_upload `.name`/`.size` gözləyir. FieldFile-ın
            # `.name`-ini DƏYİŞMƏK OLMAZ (storage yolunu sındırır) — əvəzinə
            # açılmış handle-ı orijinal adla File-a sarıyırıq ki, uzantı
            # yoxlamaları düzgün işləsin.
            wrapped = File(fh, name=job.source_name or _os.path.basename(job.file.name))
            text = extract_text_from_upload(wrapped)
        status, text_value, error_value = TextExtractionJob.STATUS_SUCCESS, text, ""

        # P3-b: workbench import yolu üçün düstur-şəkil stash-ı (yalnız PDF).
        # Uğursuzluq qeyri-fatal-dır — mətn yenə də istifadəyə yararlıdır.
        if (job.payload or {}).get("stash_math") and (job.source_name or "").lower().endswith(".pdf"):
            try:
                from apps.exams.services.import_media import stash_math_images

                with job.file.open("rb") as fh2:
                    wrapped2 = File(fh2, name=job.source_name)
                    token = stash_math_images(wrapped2)
                if token:
                    meta["math_token"] = token
            except Exception:
                logger.warning("run_text_extraction_job: job %s math stash alınmadı", job_id)
    except Exception as exc:  # istifadəçiyə göstəriləcək səbəb
        logger.info("run_text_extraction_job: job %s xəta ilə bitdi: %s", job_id, exc)
        status, text_value, error_value = TextExtractionJob.STATUS_FAILED, "", str(exc)

    with rls_worker_atomic(), bypass_rls():
        job.refresh_from_db()
        job.status = status
        job.text = text_value
        job.error = error_value
        job.result_meta = meta
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "text", "error", "result_meta", "finished_at"])
        try:
            job.file.delete(save=True)
        except Exception:
            logger.warning("run_text_extraction_job: job %s faylı silinmədi", job_id)

    return status


@shared_task(
    name="exams.run_ai_generation_job",
    time_limit=900,
    soft_time_limit=840,
)
def run_ai_generation_job(job_id):
    """P4 (2026-07-02): AI sual generasiyasını worker-də icra edir.

    Gemini çağırışı (10-60s) + opsional fayl-çıxarma sinxron sorğunu tuturdu.
    View validasiya/icazə yoxlayıb job yaradır; nəticə mətn `text`-də,
    metadata (question_count/remaining/limit/ok) `result_meta`-da saxlanır.

    QEYD: generator view fasadından həll olunur — testlər
    `apps.exams.views.teacher.question_bank.generate_question_bank_text`-i
    patch edir (mövcud konvensiya) və eager rejimdə də təsirli olmalıdır.
    """
    from django.utils import timezone

    from apps.exams.models import TextExtractionJob
    from core.rls import bypass_rls
    from core.rls_pooling import rls_worker_atomic

    with rls_worker_atomic(), bypass_rls():
        try:
            job = TextExtractionJob.objects.get(pk=job_id)
        except TextExtractionJob.DoesNotExist:
            logger.warning("run_ai_generation_job: job %s tapılmadı", job_id)
            return "missing"

        if job.status not in {TextExtractionJob.STATUS_PENDING, TextExtractionJob.STATUS_PROCESSING}:
            return job.status

        job.status = TextExtractionJob.STATUS_PROCESSING
        job.started_at = timezone.now()
        job.save(update_fields=["status", "started_at"])

    payload = dict(job.payload or {})
    status = TextExtractionJob.STATUS_SUCCESS
    text_value, error_value, meta = "", "", {}

    # 1) Fayl varsa əvvəl mətn çıxar (extract job-u ilə eyni qayda).
    if job.file:
        try:
            import os as _os

            from django.core.files.base import File

            from apps.exams.services.parsing import extract_text_from_upload

            with job.file.open("rb") as fh:
                wrapped = File(fh, name=job.source_name or _os.path.basename(job.file.name))
                extracted = extract_text_from_upload(wrapped)
            existing = (payload.get("source_text") or "").strip()
            payload["source_text"] = "\n\n".join(part for part in [existing, extracted] if part.strip())
        except Exception as exc:
            status = TextExtractionJob.STATUS_FAILED
            error_value = str(exc)

    # 2) Generasiya (fasad-rezolyusiya — patch nöqtəsi sabit qalsın).
    if status == TextExtractionJob.STATUS_SUCCESS:
        try:
            from apps.exams.views.teacher import question_bank as _qb_facade

            result = _qb_facade.generate_question_bank_text(**payload)
        except Exception:
            logger.exception("run_ai_generation_job: servis xətası (job %s)", job_id)
            status = TextExtractionJob.STATUS_FAILED
            meta = {"service_exception": True}
        else:
            meta = {k: v for k, v in result.items() if k != "text"}
            if result.get("ok"):
                text_value = result.get("text") or ""
            else:
                status = TextExtractionJob.STATUS_FAILED
                error_value = result.get("error") or ""

    with rls_worker_atomic(), bypass_rls():
        job.refresh_from_db()
        job.status = status
        job.text = text_value
        job.error = error_value
        job.result_meta = meta
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "text", "error", "result_meta", "finished_at"])
        if job.file:
            try:
                job.file.delete(save=True)
            except Exception:
                logger.warning("run_ai_generation_job: job %s faylı silinmədi", job_id)

    return status


@shared_task(
    name="exams.run_export_job",
    time_limit=900,
    soft_time_limit=840,
)
def run_export_job(job_id):
    """C2 (2026-07-03): böyük fayl exportlarını (xlsx/docx) worker-də qurur.

    Nəticə `result_file`-a yazılır; frontend status-poll edib download
    endpointindən götürür. Builder-lər: apps/exams/export_registry.py.
    """
    from django.core.files.base import ContentFile
    from django.utils import timezone

    from apps.exams.export_registry import run_export
    from apps.exams.models import TextExtractionJob
    from core.rls import bypass_rls
    from core.rls_pooling import rls_worker_atomic

    with rls_worker_atomic(), bypass_rls():
        try:
            job = TextExtractionJob.objects.select_related("organization", "user").get(pk=job_id)
        except TextExtractionJob.DoesNotExist:
            logger.warning("run_export_job: job %s tapılmadı", job_id)
            return "missing"

        if job.status not in {TextExtractionJob.STATUS_PENDING, TextExtractionJob.STATUS_PROCESSING}:
            return job.status

        job.status = TextExtractionJob.STATUS_PROCESSING
        job.started_at = timezone.now()
        job.save(update_fields=["status", "started_at"])

        payload = dict(job.payload or {})
        try:
            filename, content_type, data = run_export(
                payload.get("export", ""),
                user=job.user,
                organization=job.organization,
                params=payload.get("params") or {},
            )
        except ValueError as exc:
            job.status = TextExtractionJob.STATUS_FAILED
            job.error = str(exc)
            job.finished_at = timezone.now()
            job.save(update_fields=["status", "error", "finished_at"])
            return job.status
        except Exception:
            logger.exception("run_export_job: builder xətası (job %s)", job_id)
            job.status = TextExtractionJob.STATUS_FAILED
            job.result_meta = {"service_exception": True}
            job.finished_at = timezone.now()
            job.save(update_fields=["status", "result_meta", "finished_at"])
            return job.status

        job.result_file.save(filename, ContentFile(data), save=False)
        job.status = TextExtractionJob.STATUS_SUCCESS
        job.result_meta = {"filename": filename, "content_type": content_type}
        job.finished_at = timezone.now()
        job.save(update_fields=["result_file", "status", "result_meta", "finished_at"])
        return job.status
