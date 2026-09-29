"""Deploy-dan ƏVVƏL: hazırda gedən imtahan fəaliyyəti (YALNIZ-OXU, yalnız saylar).

`manage.py shell`-ə STDIN ilə ötürülür (bax prod-exam-ops.yml). Heç nə YAZMIR və şəxs məlumatı
çap etmir — yalnız aktiv cəhd / canlı sessiya saylarını göstərir ki, deploy (app konteynerlərinin
yenidən yaradılması, qısa 502 pəncərəsi) imtahanın ortasına düşməsin.
"""

from datetime import timedelta

from django.utils import timezone

from apps.exams.models import ExamAttempt
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
