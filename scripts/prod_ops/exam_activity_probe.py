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

# ── Cavab sağlamlığı (sahib 2026-10-27: «tələbənin cavabları düşməyənlər var») — yalnız saylar ─────────────
# Bu gün (Bakı) başlamış cəhdlər üzrə imtahan başına: status sayları, cavab sətri / cavablanmış sual sayı,
# heç bir autosave-i uğurlu olmamış (autosave_revision=0) və cavabsız bitmiş cəhdlər. Ad / istifadəçi YOX.
from django.db.models import Count, Q  # noqa: E402

from apps.exams.models import ExamAnswer, ExamQuestion  # noqa: E402

baku_midnight = (now + timedelta(hours=4)).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(hours=4)
with rls_worker_atomic(), bypass_rls():
    today = ExamAttempt.objects.filter(started_at__gte=baku_midnight, is_trial=False)
    exam_ids = sorted(set(today.values_list("exam_id", flat=True)))
    print(f"save_health_exams_today: {len(exam_ids)}")
    answered_q = Q(selected_options__isnull=False) | (Q(text_answer__isnull=False) & ~Q(text_answer=""))
    for exam_id in exam_ids:
        exam = Exam.objects.only("exam_type_extended", "start_datetime").get(pk=exam_id)
        questions = ExamQuestion.objects.filter(exam_id=exam_id).count()
        attempts = today.filter(exam_id=exam_id)
        by_status = dict(attempts.order_by().values_list("status").annotate(n=Count("id")))
        finished = list(attempts.filter(finished_at__isnull=False).values_list("id", "autosave_revision"))
        answers = ExamAnswer.objects.filter(attempt_id__in=[pk for pk, _rev in finished])
        rows = dict(answers.order_by().values_list("attempt_id").annotate(n=Count("id")))
        answered = dict(
            answers.filter(answered_q).order_by().values_list("attempt_id").annotate(n=Count("id", distinct=True))
        )
        zero = sum(1 for pk, _rev in finished if not answered.get(pk))
        partial = sum(1 for pk, _rev in finished if 0 < answered.get(pk, 0) < max(rows.get(pk, 0), 1) // 2)
        no_autosave = sum(1 for _pk, rev in finished if rev == 0)
        no_autosave_zero = sum(1 for pk, rev in finished if rev == 0 and not answered.get(pk))
        start = exam.start_datetime.strftime("%H:%M") if exam.start_datetime else "-"
        print(
            f"exam={exam_id} type={exam.exam_type_extended} start_utc={start} questions={questions} "
            f"status={by_status} finished={len(finished)} zero_answered={zero} under_half={partial} "
            f"autosave_never_ok={no_autosave} autosave_never_ok_and_zero={no_autosave_zero}"
        )
    last_answer = ExamAnswer.objects.filter(attempt__started_at__gte=baku_midnight).order_by("-updated_at")
    stamp = last_answer.values_list("updated_at", flat=True).first()
    print(f"save_health_last_answer_write_utc: {stamp:%H:%M:%S}" if stamp else "save_health_last_answer_write_utc: -")
