"""Deploy-dan ƏVVƏL: hazırda gedən imtahan fəaliyyəti (YALNIZ-OXU, yalnız saylar).

`manage.py shell`-ə STDIN ilə ötürülür (bax prod-exam-ops.yml). Heç nə YAZMIR və şəxs məlumatı
çap etmir — yalnız aktiv cəhd / canlı sessiya saylarını göstərir ki, deploy (app konteynerlərinin
yenidən yaradılması, qısa 502 pəncərəsi) imtahanın ortasına düşməsin.

2026-10-20: midterm imtahan mərkəzinə keçir (``exam.midterm_via_center``) — açarı yandırmazdan əvvəl
yaxın 14 günün aktiv midterm-ləri, onların zal bileti/oturumu, PIN-li tələbə və hazırda açıq
(kabinetdən başlamış) midterm cəhdləri SAYLARLA göstərilir (ad / istifadəçi YOX).
"""

from datetime import timedelta

from django.utils import timezone

from apps.exams.models import Exam, ExamAttempt, ExamRoomComputer, ExamStudentPin, FinalExamTicket
from apps.live_exam.models import LiveSession
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

now = timezone.now()
with rls_worker_atomic(), bypass_rls():
    open_attempts = ExamAttempt.objects.filter(status__in=["in_progress", "draft"])
    recent = open_attempts.filter(started_at__gte=now - timedelta(hours=4))
    last_15m = ExamAttempt.objects.filter(started_at__gte=now - timedelta(minutes=15)).count()
    finished_15m = ExamAttempt.objects.filter(finished_at__gte=now - timedelta(minutes=15)).count()
    live_active = LiveSession.objects.exclude(state=LiveSession.STATE_FINISHED).filter(
        created_at__gte=now - timedelta(hours=6)
    )
    print(f"server_time_utc: {now:%Y-%m-%d %H:%M}")
    print(f"open_attempts_total: {open_attempts.count()}")
    print(f"open_attempts_started_last_4h: {recent.count()}")
    print(f"attempts_started_last_15m: {last_15m}")
    print(f"attempts_finished_last_15m: {finished_15m}")
    print(f"live_sessions_active_last_6h: {live_active.count()}")
    print(f"live_sessions_in_question_or_reveal: {live_active.filter(state__in=['question', 'reveal']).count()}")

    # ── Midterm → imtahan mərkəzi hazırlığı (2026-10-20) — yalnız saylar ──────────────────────────
    horizon = now + timedelta(days=14)
    midterms = Exam.objects.filter(is_active=True, exam_type_extended="midterm")
    upcoming = midterms.filter(start_datetime__gte=now, start_datetime__lte=horizon)
    open_now = midterms.filter(start_datetime__lte=now).exclude(end_datetime__lt=now)
    upcoming_ids = list(upcoming.values_list("id", flat=True))
    tickets = FinalExamTicket.objects.filter(exam_id__in=upcoming_ids)
    print(f"midterm_active_start_next_14d: {len(upcoming_ids)}")
    print(f"midterm_active_open_now: {open_now.count()}")
    print(f"midterm_next_14d_with_center_tickets: {tickets.values('exam_id').distinct().count()}")
    print(
        "midterm_next_14d_with_center_sessions: "
        f"{tickets.filter(session__isnull=False).values('exam_id').distinct().count()}"
    )
    print(f"midterm_next_14d_students_with_pin: {ExamStudentPin.objects.filter(exam_id__in=upcoming_ids).count()}")
    print(
        "midterm_open_attempts_cabinet_flow: "
        f"{open_attempts.filter(exam__exam_type_extended='midterm', final_tickets__isnull=True).count()}"
    )
    print(f"exam_hall_registered_computers: {ExamRoomComputer.objects.filter(is_active=True).count()}")
