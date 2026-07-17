import logging
import time
import uuid
from contextlib import contextmanager

from django.conf import settings
from django.contrib import messages
from django.core.cache import caches
from django.db import IntegrityError, transaction
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import pgettext

from apps.exams.constants import ATTEMPT_FINISHED_STATUSES
from apps.exams.metrics import record_attempt_started
from apps.exams.models import Exam, ExamAttempt
from apps.exams.navigation import append_return_to as _append_return_to
from apps.exams.navigation import current_return_to
from apps.exams.services.language_variants import (
    available_language_options,
    effective_needed_count_for_attempt,
    get_active_variant,
    resolve_requested_language,
)
from apps.exams.services.randomizer import generate_random_questions_for_attempt
from apps.exams.services.utils import _attempt_has_any_answer
from core.settings_utils import safe_float_setting as _safe_float_setting
from core.settings_utils import safe_int_setting as _safe_int_setting

logger = logging.getLogger(__name__)


class ExamStartBusy(Exception):
    """Raised when too many students are trying to build attempts at once."""


def _exam_start_cache():
    return caches[getattr(settings, "REQUEST_QUEUE_CACHE_ALIAS", "default")]


def _exam_start_wait_timeout() -> float:
    return _safe_float_setting("EXAM_START_WAIT_TIMEOUT_SECONDS", 30.0, minimum=0.0)


def _exam_start_poll_interval() -> float:
    return _safe_float_setting("EXAM_START_POLL_INTERVAL_SECONDS", 0.05, minimum=0.01)


def _exam_start_lock_lease_seconds() -> int:
    return _safe_int_setting("EXAM_START_LOCK_LEASE_SECONDS", 120, minimum=1)


def _release_capacity_counter(cache, key: str) -> None:
    try:
        value = cache.decr(key)
        if value <= 0:
            cache.delete(key)
    except ValueError:
        cache.delete(key)
    except Exception:
        logger.warning("Exam start capacity counter release failed.", exc_info=True)


def _try_acquire_capacity_counter(cache, key: str, limit: int, lease_seconds: int) -> str:
    if limit <= 0:
        return "disabled"

    try:
        cache.add(key, 0, timeout=lease_seconds)
        value = cache.incr(key)
        try:
            cache.touch(key, lease_seconds)
        except Exception:
            pass

        if value <= limit:
            return "acquired"

        _release_capacity_counter(cache, key)
        return "busy"
    except Exception:
        logger.warning("Exam start capacity counter failed; bypassing the gate.", exc_info=True)
        return "bypass"


@contextmanager
def _exam_start_actor_lock(exam_id: int, user_id: int):
    cache_key = f"emsarena:exam-start:actor:{exam_id}:{user_id}"
    token = uuid.uuid4().hex
    lease_seconds = _exam_start_lock_lease_seconds()
    timeout = _exam_start_wait_timeout()
    deadline = time.monotonic() + timeout
    acquired = False
    cache = None

    try:
        cache = _exam_start_cache()
        while True:
            if cache.add(cache_key, token, timeout=lease_seconds):
                acquired = True
                break

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ExamStartBusy
            time.sleep(min(_exam_start_poll_interval(), remaining))
    except ExamStartBusy:
        raise
    except Exception:
        logger.warning("Exam start actor lock failed; continuing without the per-user lock.", exc_info=True)
        yield
        return

    try:
        yield
    finally:
        try:
            if acquired and cache is not None and cache.get(cache_key) == token:
                cache.delete(cache_key)
        except Exception:
            logger.warning("Exam start actor lock release failed.", exc_info=True)


@contextmanager
def _exam_start_capacity_gate(exam_id: int):
    limits = (
        ("global", _safe_int_setting("EXAM_START_GLOBAL_CONCURRENCY", 12, minimum=0)),
        (f"exam:{exam_id}", _safe_int_setting("EXAM_START_PER_EXAM_CONCURRENCY", 6, minimum=0)),
    )
    if all(limit <= 0 for _, limit in limits):
        yield
        return

    try:
        cache = _exam_start_cache()
    except Exception:
        logger.warning("Exam start capacity cache unavailable; continuing without the capacity gate.", exc_info=True)
        yield
        return

    lease_seconds = _exam_start_lock_lease_seconds()
    timeout = _exam_start_wait_timeout()
    deadline = time.monotonic() + timeout
    acquired_keys: list[str] = []

    try:
        while True:
            acquired_keys = []
            blocked = False

            for suffix, limit in limits:
                key = f"emsarena:exam-start:capacity:{suffix}"
                result = _try_acquire_capacity_counter(cache, key, limit, lease_seconds)
                if result == "busy":
                    blocked = True
                    break
                if result == "acquired":
                    acquired_keys.append(key)

            if not blocked:
                break

            for key in acquired_keys:
                _release_capacity_counter(cache, key)
            acquired_keys = []

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ExamStartBusy
            time.sleep(min(_exam_start_poll_interval(), remaining))

        yield
    finally:
        for key in acquired_keys:
            _release_capacity_counter(cache, key)


def get_active_attempt_for_user(exam, user):
    for attempt in exam.attempts.filter(user=user, status__in=["draft", "in_progress"]).order_by("-started_at"):
        if attempt.expire_if_time_limit_reached():
            continue
        return attempt
    return None


def get_finished_attempts_for_user(exam, user):
    return exam.attempts.filter(user=user, status__in=ATTEMPT_FINISHED_STATUSES).order_by("-started_at")


def sweep_overdue_attempts(queryset=None):
    """Vaxtı bitmiş (deadline-ı keçmiş) draft/in_progress cəhdləri avtomatik
    bitirir — tələbənin brauzeri bağlı olsa belə imtahan «yarımçıq/gözləmədə»
    qalmasın; nəzarətçi, müəllim və nəticə ekranlarında dərhal bitmiş görünsün.

    Cəhd ``expired`` kimi bağlanır, saxlanmış cavablar qorunur (test balı
    oxuma zamanı ``score_percent`` ilə hesablanır, ona görə tələbənin o ana
    qədər yazdığı avtomatik sayılır). Qlobal periodik Celery sweep-dən və lazy
    monitor oxumalarından təhlükəsiz çağırıla bilər. Bitirilən cəhd sayını
    qaytarır.

    Tenant izolyasiyası: çağıran org-skoplu ``queryset`` ötürür; skopsuz
    default yalnız qlobal periodik sweep üçündür və hər cəhd öz imtahanının
    ``organization``-una yazılır.
    """
    if queryset is None:
        queryset = ExamAttempt.objects.all()

    candidates = queryset.filter(status__in=["draft", "in_progress"], is_trial=False).select_related(
        "exam", "exam__organization", "user"
    )
    expired = 0
    for attempt in candidates.iterator():
        if attempt.expire_if_time_limit_reached():
            expired += 1
    return expired


def can_user_start_new_attempt(exam, user):
    active_attempt = get_active_attempt_for_user(exam, user)
    if active_attempt:
        return False, "active_attempt_exists"

    # Qrant-şüurlu: attempts_left_for() qlobal max_attempts_per_user-in üstünə
    # həmin tələbəyə verilmiş əlavə cəhdləri (StudentExamAttemptGrant) də sayır.
    # None = limitsiz. Köhnə versiya yalnız qlobal limiti yoxlayır və müəllimin
    # verdiyi "ikinci şans"ı görmürdü.
    attempts_left = exam.attempts_left_for(user)
    if attempts_left is not None and attempts_left <= 0:
        return False, "max_attempts_reached"

    return True, "ok"


def get_effective_max_attempts(exam, user):
    """Bu tələbə üçün EFFEKTİV maksimal cəhd sayı = qlobal limit + qrant(lar).

    Mesajlarda ("ən çox N cəhd") düzgün rəqəmin göstərilməsi üçün — müəllim əlavə
    cəhd veribsə, tələbənin real haqqı qlobal ``max_attempts_per_user``-dan çoxdur.
    Limitsizdirsə (limit 0/None) None qaytarır.
    """
    if not exam.max_attempts_per_user:
        return None
    extra = exam.attempt_grants.filter(student=user).values_list("extra_attempts", flat=True).first() or 0
    return exam.max_attempts_per_user + extra


def _next_attempt_number(exam, user) -> int:
    last_attempt = exam.attempts.filter(user=user).order_by("-attempt_number").first()
    return (last_attempt.attempt_number + 1) if last_attempt else 1


def _create_attempt_or_get_active(exam, user, **extra_fields):
    """Create a new in_progress attempt; on a constraint race return the
    existing active attempt instead of raising.

    The DB constraints (uniq_active_attempt_per_user_exam,
    uniq_attempt_number_per_user_exam) are the last line of defence when two
    parallel start requests slip past the cache-based actor lock.  Returns a
    tuple ``(attempt, created)``.
    """
    try:
        with transaction.atomic():
            return (
                ExamAttempt.objects.create(
                    user=user,
                    exam=exam,
                    attempt_number=_next_attempt_number(exam, user),
                    status="in_progress",
                    **extra_fields,
                ),
                True,
            )
    except IntegrityError:
        existing = get_active_attempt_for_user(exam, user)
        if existing is not None:
            logger.info(
                "Duplicate exam start blocked by DB constraint: user=%s exam=%s -> reusing attempt=%s",
                user.pk,
                exam.pk,
                existing.pk,
            )
            return existing, False
        # No active attempt: the collision was on attempt_number (a parallel
        # request finished in between).  Recompute and retry once.
        return (
            ExamAttempt.objects.create(
                user=user,
                exam=exam,
                attempt_number=_next_attempt_number(exam, user),
                status="in_progress",
                **extra_fields,
            ),
            True,
        )


@transaction.atomic
def create_exam_attempt(exam, user):
    attempt, _created = _create_attempt_or_get_active(exam, user)
    return attempt


@transaction.atomic
def submit_exam_attempt(attempt):
    if getattr(attempt.exam, "exam_type", None) == "test":
        from apps.exams.services.result_calculation import sync_test_attempt_counts

        sync_test_attempt_counts(attempt)
    attempt.mark_finished(status="submitted")
    return attempt


def _build_exam_result_url(exam, attempt, return_to):
    return _append_return_to(
        reverse("exams:exam_result", kwargs={"slug": exam.slug, "attempt_id": attempt.id}),
        return_to,
    )


def get_attempt_limit_result_redirect_url(request, exam: Exam, user):
    if not exam.max_attempts_per_user or not exam.is_active or exam.is_before_start() or exam.is_after_end():
        return ""

    return_to = current_return_to(request)

    if get_active_attempt_for_user(exam, user):
        return ""

    # Qrant-şüurlu limit yoxlaması: müəllimin verdiyi əlavə cəhd(lər) qlobal
    # limitin üstünə gəlir. attempts_left_for None (limitsiz) və ya >0 qaytarırsa
    # tələbənin hələ cəhd haqqı var — köhnə nəticə səhifəsinə atmırıq. Əvvəl bu
    # helper yalnız finished-count >= max_attempts yoxlayırdı və qrantı gözardı
    # edib "ikinci şans" verilmiş tələbəni geri atırdı (can_user_start icazə
    # versə belə).
    attempts_left = exam.attempts_left_for(user)
    if attempts_left is None or attempts_left > 0:
        return ""

    last_attempt = get_finished_attempts_for_user(exam, user).first()
    if not last_attempt:
        return ""

    return _build_exam_result_url(exam, last_attempt, return_to)


def _start_or_resume_attempt(request, exam: Exam):
    """
    İstifadəçi üçün attempt yaradır və ya mövcud attempt-ə yönləndirir.
    """
    user = request.user
    return_to = current_return_to(request)

    # Müəllim "Sınaq keç" düyməsi ilə öz imtahanını yoxlaya bilər — bu cəhd
    # yalnız imtahan müəllifinə açıqdır və nəticələrə sayılmır (is_trial).
    is_trial = (request.GET.get("trial") == "1" or request.POST.get("trial") == "1") and user == exam.author

    # ── Çoxdilli imtahan: yeni attempt üçün dil seçimi ──────────────────────
    # Mövcud aktiv attempt varsa, dil onsuz da seçilib — resume zamanı sormuruq.
    # Yalnız bir dil varsa avtomatik seçilir; birdən çox dil varsa və seçim
    # gəlməyibsə, attempt yaratmadan siyahıya qaytarılır (modal seçim göndərməlidir).
    chosen_language = None
    if get_active_attempt_for_user(exam, user) is None:
        language_options = available_language_options(exam)
        if len(language_options) == 1:
            chosen_language = language_options[0]["language"]
        elif len(language_options) > 1:
            chosen_language = resolve_requested_language(
                exam, request.GET.get("language") or request.POST.get("language")
            )
            if chosen_language is None:
                messages.warning(
                    request,
                    pgettext("exams.service.attempt.message", "language_required_for_multilingual_exam"),
                )
                return redirect(_append_return_to(reverse("exams:student_exam_list"), return_to))

    try:
        with _exam_start_actor_lock(exam.id, user.id), _exam_start_capacity_gate(exam.id):
            current = get_active_attempt_for_user(exam, user)
            if current:
                desired = effective_needed_count_for_attempt(current)
                current_count = current.answers.count()

                if current_count != desired and not _attempt_has_any_answer(current):
                    generate_random_questions_for_attempt(current, force_rebuild=True)

                return redirect(
                    _append_return_to(
                        reverse("exams:take_exam", kwargs={"slug": exam.slug, "attempt_id": current.id}),
                        return_to,
                    )
                )

            # Mesaj üçün effektiv limit (qlobal + qrant) — bounce yalnız effektiv
            # limit dolduqda baş verir, ona görə tələbəyə real haqqını göstərək.
            max_attempts = get_effective_max_attempts(exam, user) or exam.max_attempts_per_user
            attempt_limit_result_url = get_attempt_limit_result_redirect_url(request, exam, user)
            if attempt_limit_result_url:
                messages.info(
                    request,
                    pgettext("exams.service.attempt.message", "max_attempts_reached").format(max_attempts=max_attempts),
                )
                return redirect(attempt_limit_result_url)

            attempt, created = _create_attempt_or_get_active(
                exam,
                user,
                language=chosen_language,
                language_variant=get_active_variant(exam, chosen_language) if chosen_language else None,
                is_trial=is_trial,
            )
            if not created:
                # A parallel request already created the attempt (DB constraint
                # caught the race) — just resume it.
                return redirect(
                    _append_return_to(
                        reverse("exams:take_exam", kwargs={"slug": exam.slug, "attempt_id": attempt.id}),
                        return_to,
                    )
                )

            generate_random_questions_for_attempt(attempt)
            record_attempt_started(exam.exam_type)
    except ExamStartBusy:
        messages.warning(
            request,
            pgettext(
                "exams.service.attempt.message",
                "Server hazırda çox imtahan start sorğusu emal edir. Bir neçə saniyə sonra yenidən yoxlayın.",
            ),
        )
        return redirect(_append_return_to(reverse("exams:student_exam_list"), return_to))

    messages.success(
        request,
        pgettext("exams.service.attempt.message", "exam_started").format(attempt_number=attempt.attempt_number),
    )
    return redirect(
        _append_return_to(reverse("exams:take_exam", kwargs={"slug": exam.slug, "attempt_id": attempt.id}), return_to)
    )
