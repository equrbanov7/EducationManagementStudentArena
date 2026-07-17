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


@shared_task(name="exams.expire_overdue_attempts")
def expire_overdue_attempts():
    """
    Auto-finish any draft/in_progress attempt whose exam-duration deadline has
    passed.  Runs globally every minute so a timed exam never lingers "in
    progress / pending" after time is up — in the room monitor, the teacher's
    supervision monitor, or anywhere else — even when the student's browser is
    closed (so its client-side auto-submit never fired).  Answers saved up to
    the deadline are preserved and graded.

    Returns the number of attempts that were auto-finished.
    """
    from apps.exams.services.attempts import sweep_overdue_attempts
    from core.rls import bypass_rls
    from core.rls_pooling import rls_worker_atomic

    # Global periodic sweep has no org_id argument; each finished attempt is
    # written under its own exam.organization, preserving tenant isolation.
    with rls_worker_atomic(), bypass_rls():
        expired = sweep_overdue_attempts()
    if expired:
        logger.info("expire_overdue_attempts: auto-finished %d attempt(s)", expired)
    return expired


@shared_task(name="exams.reap_stuck_extraction_jobs")
def reap_stuck_extraction_jobs(lease_seconds: int = 1200):
    """EXAM-P1-15: crash-safe lease reaper.

    Bir ``TextExtractionJob`` PENDING→PROCESSING atomik claim edildikdən sonra
    icraçı (worker və ya inline-fallback) crash edərsə, job əbədi PROCESSING-də
    ilişib qalırdı — istifadəçi status poll edir, heç vaxt nəticə gəlmir. Bu
    task ``started_at`` üstündən ``lease_seconds`` (default task time_limit-dən
    böyük) keçmiş PROCESSING job-ları FAILED-ə keçirir ki, istifadəçi xəta
    görüb yenidən cəhd edə bilsin. Global sweep — tenant izolyasiyası bypass ilə.
    """
    from datetime import timedelta

    from django.utils import timezone

    from apps.exams.models import TextExtractionJob
    from core.rls import bypass_rls
    from core.rls_pooling import rls_worker_atomic

    cutoff = timezone.now() - timedelta(seconds=lease_seconds)
    with rls_worker_atomic(), bypass_rls():
        reaped = TextExtractionJob.objects.filter(
            status=TextExtractionJob.STATUS_PROCESSING,
            started_at__lt=cutoff,
        ).update(
            status=TextExtractionJob.STATUS_FAILED,
            error="İcra vaxtı bitdi (lease). Zəhmət olmasa yenidən cəhd edin.",
            finished_at=timezone.now(),
        )
    if reaped:
        logger.warning("reap_stuck_extraction_jobs: %d ilişmiş job FAILED edildi", reaped)
    return reaped


@shared_task(name="exams.notify_upcoming_final_exams")
def notify_upcoming_final_exams():
    """
    Final oturumu yaxınlaşan tələbələrə xatırlatma bildirişi göndərir
    ("gəl imtahanı ver"). Dublikat ``reminder_stage`` ilə əngəllənir; global
    sweep bütün təşkilatları gəzir, hər bildiriş biletin öz org-u altındadır.

    Qaytarır: göndərilən bildiriş sayı.
    """
    from apps.exams.services.final_center import notify_upcoming_final_exams as _run
    from core.rls import bypass_rls
    from core.rls_pooling import rls_worker_atomic

    with rls_worker_atomic(), bypass_rls():
        sent = _run()
    if sent:
        logger.info("notify_upcoming_final_exams: sent %d reminder(s)", sent)
    return sent


@shared_task(name="exams.auto_close_daily_room_sessions")
def auto_close_daily_room_sessions():
    """Gün sonu (22:00 Asia/Baku) təhlükəsizlik süpürgəsi: hələ açıq qalmış zal
    oturumlarını avtomatik bağlayır ki, heç bir imtahan gecəyə qalmasın.

    Aktiv oturumlar bitirilir (cavablar qorunur), giriş açıq amma başlamamış
    oturumlar ləğv olunur. Gələcək tarixli oturumlara toxunulmur. Global sweep —
    tenant izolyasiyası bypass altında, hər yazı öz təşkilatını audit-ə yazır.
    """
    from apps.exams.services.final_center import auto_close_stale_room_sessions
    from core.rls import bypass_rls
    from core.rls_pooling import rls_worker_atomic

    with rls_worker_atomic(), bypass_rls():
        result = auto_close_stale_room_sessions()
    if result.get("ended") or result.get("cancelled"):
        logger.info(
            "auto_close_daily_room_sessions: ended=%d cancelled=%d",
            result.get("ended", 0),
            result.get("cancelled", 0),
        )
    return result


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
        # ATOMİK CLAIM (CAS): yalnız PENDING→PROCESSING keçidini qazanan icra
        # edir — worker + inline-fallback paralel işləməsin (Codex finding:
        # broker sağ / worker ölü ssenarisi üçün pickup-watchdog fallback-i).
        claimed = TextExtractionJob.objects.filter(pk=job_id, status=TextExtractionJob.STATUS_PENDING).update(
            status=TextExtractionJob.STATUS_PROCESSING, started_at=timezone.now()
        )
        try:
            job = TextExtractionJob.objects.get(pk=job_id)
        except TextExtractionJob.DoesNotExist:
            logger.warning("run_text_extraction_job: job %s tapılmadı", job_id)
            return "missing"
        if not claimed:
            # Başqa icraçı artıq götürüb (və ya bitirib) — toxunma.
            return job.status

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
    except ValueError as exc:
        # extract_text_from_upload-un lokalizə olunmuş, istifadəçiyə uyğun xətaları.
        logger.info("run_text_extraction_job: job %s istifadəçi xətası: %s", job_id, exc)
        status, text_value, error_value = TextExtractionJob.STATUS_FAILED, "", str(exc)
    except Exception:
        # Texniki xəta (yol/kod/infra) — istifadəçi RAW mesajı görməməlidir.
        logger.exception("run_text_extraction_job: job %s texniki xəta", job_id)
        from django.utils.translation import pgettext

        status, text_value = TextExtractionJob.STATUS_FAILED, ""
        error_value = pgettext(
            "exams.task.extract.error",
            "Fayl emal edilərkən texniki xəta baş verdi. Yenidən cəhd edin — problem davam edərsə inzibatçıya bildirin.",
        )

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
        # ATOMİK CLAIM (CAS): yalnız PENDING→PROCESSING keçidini qazanan icra
        # edir — worker + inline-fallback paralel işləməsin (Codex finding:
        # broker sağ / worker ölü ssenarisi üçün pickup-watchdog fallback-i).
        claimed = TextExtractionJob.objects.filter(pk=job_id, status=TextExtractionJob.STATUS_PENDING).update(
            status=TextExtractionJob.STATUS_PROCESSING, started_at=timezone.now()
        )
        try:
            job = TextExtractionJob.objects.get(pk=job_id)
        except TextExtractionJob.DoesNotExist:
            logger.warning("run_ai_generation_job: job %s tapılmadı", job_id)
            return "missing"
        if not claimed:
            # Başqa icraçı artıq götürüb (və ya bitirib) — toxunma.
            return job.status

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
        except ValueError as exc:
            status = TextExtractionJob.STATUS_FAILED
            error_value = str(exc)
        except Exception:
            logger.exception("run_ai_generation_job: job %s fayl-çıxarma texniki xətası", job_id)
            from django.utils.translation import pgettext

            status = TextExtractionJob.STATUS_FAILED
            error_value = pgettext(
                "exams.task.extract.error",
                "Fayl emal edilərkən texniki xəta baş verdi. Yenidən cəhd edin — problem davam edərsə inzibatçıya bildirin.",
            )

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
        # ATOMİK CLAIM (CAS): yalnız PENDING→PROCESSING keçidini qazanan icra
        # edir — worker + inline-fallback paralel işləməsin (Codex finding:
        # broker sağ / worker ölü ssenarisi üçün pickup-watchdog fallback-i).
        claimed = TextExtractionJob.objects.filter(pk=job_id, status=TextExtractionJob.STATUS_PENDING).update(
            status=TextExtractionJob.STATUS_PROCESSING, started_at=timezone.now()
        )
        try:
            job = TextExtractionJob.objects.select_related("organization", "user").get(pk=job_id)
        except TextExtractionJob.DoesNotExist:
            logger.warning("run_export_job: job %s tapılmadı", job_id)
            return "missing"
        if not claimed:
            # Başqa icraçı artıq götürüb (və ya bitirib) — toxunma.
            return job.status

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
