import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext

from apps.exams.constants import ATTEMPT_FINISHED_STATUSES
from apps.exams.domain.attempt_deadline import write_window_closed
from apps.exams.features import exam_supervision_enabled, practical_exam_disabled_message, practical_exams_enabled
from apps.exams.metrics import record_autosave
from apps.exams.models import Exam, ExamAnswer, ExamAttempt
from apps.exams.services.attempts import (
    _start_or_resume_attempt,
    generate_random_questions_for_attempt,
    get_active_attempt_for_user,
    get_attempt_limit_result_redirect_url,
    get_effective_max_attempts,
)
from apps.exams.services.question_timer import question_timer_expired
from apps.exams.services.start_intent import has_valid_start_intent
from apps.exams.views.shared.tenant import tenant_scoped_exams

from ._answer_writes import TestAnswerWriteBatch, _save_test_answer_if_changed, _save_written_answer_if_changed
from ._final_device import final_device_guarded
from ._helpers import (
    annotate_attempt_result_visibility,
    append_return_to,
    build_exam_history_url,
    build_exam_result_url,
    build_take_exam_question_payload,
    bump_autosave_revision,
    current_return_to,
    ensure_student_exam_tenant_context,
    finish_skips_absent_question,
    posted_autosave_question_ids,
    remember_autosave_write,
    resolve_author_failure_redirect,
    resolve_exam_failure_redirect,
    selected_option_ids_from_request,
)
from ._take_post_lock import finished_attempt_response, run_locked_take_exam_post
from ._timer_write_guard import reject_unstarted_timed_write
from .access_guard import USER_EXCLUDED_ANNOTATION, ensure_active_attempt_access, user_exclusion_annotation
from .script_data import take_exam_script_data


def _attempt_answers_queryset(attempt, *, question_ids=None, with_options=True, with_files=True):
    """
    Return the answers (with question + optional options/files prefetch) for `attempt`.

    P2.E — when `question_ids` is provided (autosave fast-path) the queryset is
    narrowed to only the changed questions so we don't load the full answer set
    for every autosave request.

    Perf 2026-10-06: variantlar/seçimlər yalnız test imtahanında oxunur
    (`with_options`), cavab faylları isə yalnız yazılı imtahan səhifəsində
    göstərilir (`with_files`) — POST yolu faylları heç oxumur (əvəzləmə
    `answer.files.all().delete()` öz sorğusudur).
    """
    prefetch = []
    if with_options:
        prefetch += ["question__options", "selected_options"]
    if with_files:
        prefetch.append("files")
    qs = attempt.answers.select_related("question", "question__exam", "question__block")
    if prefetch:
        qs = qs.prefetch_related(*prefetch)
    qs = qs.order_by("id")
    if question_ids is not None:
        qs = qs.filter(question_id__in=list(question_ids))
    return qs


def _answers_by_question_id(answers, *, with_options):
    """`{question_id: {"answer", "selected_option_ids"}}` — seçimlər yalnız prefetch olunubsa."""
    return {
        a.question_id: {
            "answer": a,
            "selected_option_ids": {option.id for option in a.selected_options.all()} if with_options else set(),
        }
        for a in answers
    }


def _marked_question_ids_from_request(request, valid_question_ids):
    raw_payload = (request.POST.get("marked_question_ids") or "").strip()
    if not raw_payload:
        return None

    try:
        parsed_payload = json.loads(raw_payload)
    except (TypeError, ValueError):
        parsed_payload = raw_payload.split(",")

    if not isinstance(parsed_payload, (list, tuple, set)):
        return []
    if not parsed_payload:
        # Perf 2026-10-06: klient hər autosave-də «[]» göndərir — boş siyahının
        # validasiyası üçün attempt-in sual id-lərini oxumağa ehtiyac yoxdur.
        return []

    valid_question_ids = {int(question_id) for question_id in valid_question_ids}
    marked_question_ids = []
    seen_question_ids = set()
    for raw_question_id in parsed_payload:
        try:
            question_id = int(raw_question_id)
        except (TypeError, ValueError):
            continue
        if question_id not in valid_question_ids or question_id in seen_question_ids:
            continue
        marked_question_ids.append(question_id)
        seen_question_ids.add(question_id)
    return marked_question_ids


def _save_marked_question_ids_from_request(request, attempt, *, loaded_question_ids=None):
    # `loaded_question_ids` — çağıran attempt-in BÜTÜN cavablarını artıq yükləyibsə
    # onların sual id-ləri (eyni çoxluq; ayrıca `values_list` sorğusu getmir).
    valid_question_ids = (
        loaded_question_ids
        if loaded_question_ids is not None
        else attempt.answers.values_list("question_id", flat=True)
    )
    marked_question_ids = _marked_question_ids_from_request(request, valid_question_ids)
    if marked_question_ids is None:
        return
    current_marked_question_ids = list(getattr(attempt, "marked_question_ids", None) or [])
    if current_marked_question_ids == marked_question_ids:
        return
    attempt.marked_question_ids = marked_question_ids
    attempt.save(update_fields=["marked_question_ids"])


def _previous_attempts_for_context(request, exam, attempt):
    # P2.D — select_related ile exam-ı tək sorğuda gətir; annotate_attempt_result_visibility
    # `attempt.exam.*` field-lərinə müraciət edir.
    previous_attempts = annotate_attempt_result_visibility(
        list(
            ExamAttempt.objects.filter(
                exam=exam,
                user=request.user,
                status__in=ATTEMPT_FINISHED_STATUSES,
            )
            .exclude(id=attempt.id)
            .select_related("exam")
            .order_by("-started_at")
        )
    )
    current_path = request.get_full_path()
    for previous_attempt in previous_attempts:
        previous_attempt.result_url = build_exam_result_url(previous_attempt, return_to=current_path)
    return previous_attempts


@login_required
def start_exam(request, slug):
    """
    İmtahan başlatma view-ı
    """
    ensure_student_exam_tenant_context(request)
    # Deaktiv (qaralama) imtahan hamı üçün 404 olaraq qalır — YALNIZ imtahanın
    # öz müəllifi istisnadır: o, "Sınaq keç" düyməsindən bura gəlir və boş 404
    # əvəzinə səbəbi izah edən mesaj almalıdır. Tenant scope-u və soft-delete
    # filtri `tenant_scoped_exams`-də olduğu kimi qalır.
    exam = get_object_or_404(tenant_scoped_exams(request, Exam.objects.all()), slug=slug)
    if not exam.is_active:
        if exam.author_id != request.user.id:
            raise Http404("Exam is not active.")
        messages.error(request, pgettext("exams.view.access.message", "exam_inactive_trial_blocked"))
        return redirect(resolve_author_failure_redirect(request, exam))

    # İcazə yoxlaması
    can_start, reason = exam.can_user_start(request.user, code=None)
    if not can_start:
        attempt_limit_result_url = get_attempt_limit_result_redirect_url(request, exam, request.user)
        if attempt_limit_result_url:
            messages.info(
                request,
                pgettext("exams.service.attempt.message", "max_attempts_reached").format(
                    max_attempts=get_effective_max_attempts(exam, request.user) or exam.max_attempts_per_user
                ),
            )
            return redirect(attempt_limit_result_url)
        messages.error(request, reason or pgettext("exams.view.access.message", "exam_start_not_allowed"))
        return redirect(resolve_exam_failure_redirect(request))

    if not exam.questions.filter(is_active=True).exists():
        messages.error(request, pgettext("exams.view.access.message", "exam_has_no_questions"))
        # Müəllimi tələbə siyahısına atmaq mənasızdır — o, sualı elə imtahanın
        # öz səhifəsindən əlavə edir.
        return redirect(resolve_author_failure_redirect(request, exam))

    # Elektron jurnal buraxılış qapısı: qayıb limiti keçilibsə start olmaz (no-op if unlinked).
    from apps.exams.services.journal_sync import registrar_block_reason

    block_reason = registrar_block_reason(request, exam)
    if block_reason:
        messages.error(request, block_reason)
        return redirect(resolve_exam_failure_redirect(request))

    # EXAMQA R1 (2026-10-01): YENİ cəhd yalnız POST (CSRF) və ya platformanın öz linkindəki imzalı
    # niyyət tokeni ilə yaranır — kənar link vaxtlı cəhdi başlada bilməz. Davam edən cəhdə qayıtmaq
    # (resume) tokensiz də işləyir. Bax apps/exams/services/start_intent.py.
    if (
        request.method != "POST"
        and not has_valid_start_intent(request, exam)
        and get_active_attempt_for_user(exam, request.user) is None
    ):
        context = {"exam": exam, "back_url": resolve_exam_failure_redirect(request)}
        return render(request, "exams/student/exam_start_confirm.html", context)
    return _start_or_resume_attempt(request, exam)


def _handle_take_exam_post(request, *, attempt, action, is_ajax, return_to):
    """Kilid altında cavab yazıları + finish (çağıran: `run_locked_take_exam_post`).

    Attempt artıq `FOR UPDATE` ilə yüklənib, giriş/nəzarət/OCC yoxlamaları
    keçilib (bax `_take_post_lock.py`); burada atomic blok daxilindəyik.
    """
    exam = attempt.exam

    # Re-check the deadline while holding the attempt row lock. This keeps
    # final submit, autosave, and timer-expiry paths from racing each other.
    # Audit 2026-09-28 EX28-07: deadline `end_datetime` ilə kəsilir; müddətsiz
    # imtahanda `end_datetime` keçibsə də vaxt bitmiş sayılır (grace daxilində yazı saxlanır).
    is_time_up = write_window_closed(attempt, at_time=timezone.now())

    autosave_question_ids_for_fetch = posted_autosave_question_ids(request, action=action)
    with_options = exam.exam_type == "test"
    answers_qs_kwargs = {"question_ids": autosave_question_ids_for_fetch, "with_options": with_options}
    answers = list(_attempt_answers_queryset(attempt, with_files=False, **answers_qs_kwargs))

    if not answers:
        if not attempt.answers.exists():
            generate_random_questions_for_attempt(attempt)
        answers = list(_attempt_answers_queryset(attempt, with_files=False, **answers_qs_kwargs))

    if not answers and autosave_question_ids_for_fetch is None:
        if is_ajax:
            return JsonResponse(
                {
                    "success": False,
                    "error": pgettext("exams.view.access.message", "exam_start_failed"),
                },
                status=400,
            )
        message_key = (
            "exam_has_no_questions" if not exam.questions.filter(is_active=True).exists() else "exam_start_failed"
        )
        messages.error(request, pgettext("exams.view.access.message", message_key))
        return redirect(resolve_exam_failure_redirect(request))

    # Tam yükləmədə (`question_ids is None`) `answers` attempt-in BÜTÜN cavablarıdır.
    full_answer_set = autosave_question_ids_for_fetch is None
    questions = [a.question for a in answers]
    answers_by_qid = _answers_by_question_id(answers, with_options=with_options)

    _save_marked_question_ids_from_request(
        request, attempt, loaded_question_ids=[a.question_id for a in answers] if full_answer_set else None
    )

    autosave_changed_question_ids = autosave_question_ids_for_fetch
    form_has_presence_markers = any(key.startswith("q_present_") for key in request.POST)

    # Perf auditi 2026-09-13 F-05: test cavablarının yazıları döngüdə
    # deyil, sonda TOPLU gedir (bax `TestAnswerWriteBatch`) — sorğu sayı
    # sual sayından asılı olmur. Erkən `return`-lardan əvvəl də `flush()`
    # çağırılır ki, əvvəlki sualların yazısı (köhnə davranış) itməsin.
    write_batch = TestAnswerWriteBatch()

    for q in questions:
        if autosave_changed_question_ids is not None and q.id not in autosave_changed_question_ids:
            continue
        if autosave_changed_question_ids is None and finish_skips_absent_question(
            request, q.id, form_has_presence_markers=form_has_presence_markers
        ):
            continue
        timer_guard = reject_unstarted_timed_write(
            request, attempt, q, exam_type=exam.exam_type, action=action, is_ajax=is_ajax
        )
        if timer_guard is not None:
            write_batch.flush()
            return timer_guard
        # Server deadline keçmiş sualın yazısı saxlanmır.
        if question_timer_expired(attempt, q):
            continue

        answer_data = answers_by_qid.get(q.id) or {}
        ans = answer_data.get("answer")
        if ans is None:
            # Müdafiə qolu: `questions` elə `answers`-dən çıxarılır, yəni
            # praktikada bura düşülmür (F-05 ölçüsündə 0 dəfə).
            ans, _ = ExamAnswer.objects.get_or_create(attempt=attempt, question=q)
            answer_data = {"answer": ans, "selected_option_ids": set()}
            full_answer_set = False  # yeni cavab `answers`-də yoxdur — bal hesabı təkrar oxusun

        if exam.exam_type == "test" and q.answer_mode in ("single", "multiple"):
            _save_test_answer_if_changed(
                ans,
                q,
                selected_option_ids_from_request(request, q),
                answer_data.get("selected_option_ids", set()),
                batch=write_batch,
            )
        else:
            try:
                _save_written_answer_if_changed(
                    request,
                    ans,
                    q,
                    allow_binary_uploads=(action != "autosave" or settings.EXAM_AUTOSAVE_BINARY_UPLOADS_ENABLED),
                )
            except ValidationError as exc:
                write_batch.flush()
                if is_ajax:
                    return JsonResponse({"success": False, "error": exc.messages[0]}, status=400)
                messages.error(request, exc.messages[0])
                return redirect(
                    append_return_to(
                        reverse("exams:take_exam", kwargs={"slug": exam.slug, "attempt_id": attempt.id}),
                        return_to,
                    )
                )

    write_batch.flush()

    finishing = action == "finish" or is_time_up
    finish_extra_fields = None
    if exam.exam_type == "test" and (action != "autosave" or is_time_up):
        # Perf 2026-10-06: tam cavab dəsti artıq yüklənib (yazılar seçim
        # snapshot-unu instansda yeniləyib) — bal hesabı onu təkrar oxumur.
        # Finish-də say sahələri `mark_finished`-in TƏK UPDATE-inə qatılır.
        attempt.recalculate_score(answers=answers if full_answer_set else None, save=not finishing)
        if finishing:
            finish_extra_fields = ["correct_count", "wrong_count"]

    # EXAM-P1-06: uğurlu yazıdan sonra revision-u artır (OCC).
    bump_autosave_revision(attempt)
    remember_autosave_write(request, attempt, action)

    if finishing:
        status = "expired" if is_time_up else "submitted"
        attempt.mark_finished(status=status, extra_update_fields=finish_extra_fields)
        if is_ajax:
            return JsonResponse(
                {
                    "success": True,
                    "finished": True,
                    "redirect_url": build_exam_result_url(attempt, return_to=return_to),
                }
            )
        return redirect(build_exam_result_url(attempt, return_to=return_to))

    if action == "save_draft" and attempt.status != "draft":
        attempt.status = "draft"
        attempt.save(update_fields=["status"])

    if action == "autosave":
        record_autosave("success")
    if is_ajax:
        return JsonResponse({"success": True, "finished": False, "server_revision": attempt.autosave_revision})

    return redirect(
        append_return_to(reverse("exams:take_exam", kwargs={"slug": exam.slug, "attempt_id": attempt.id}), return_to)
    )


@login_required
@final_device_guarded
def take_exam(request, slug, attempt_id):
    ensure_student_exam_tenant_context(request)
    if request.method == "POST":
        # Perf 2026-10-06: test/yazılı POST-u attempt-i TƏK dəfə, sətir kilidi
        # altında yükləyir və bütün yoxlamaları orada edir (bax `_take_post_lock`).
        # `None` → coding attempt (və ya tapılmadı) — aşağıdakı köhnə yol.
        response = run_locked_take_exam_post(
            request, slug=slug, attempt_id=attempt_id, write_answers=_handle_take_exam_post
        )
        if response is not None:
            return response
    # P2.D — select_related ile attempt + exam + user + exam.author/course-u tək
    # sorğuda yüklə (əvvəlcə hər biri ayrı round-trip idi). Perf 2026-10-06:
    # nəzarət konfiqi (reverse one-to-one) və exclusion EXISTS də eyni sorğuda.
    attempt = get_object_or_404(
        ExamAttempt.objects.select_related(
            "exam",
            "exam__author",
            "exam__course",
            "exam__organization",
            "exam__supervision_config",
            "user",
        ).annotate(**user_exclusion_annotation(request.user)),
        id=attempt_id,
        exam__in=tenant_scoped_exams(request),
        exam__slug=slug,
        user=request.user,
    )
    exam = attempt.exam
    ensure_active_attempt_access(
        attempt, request.user, request=request, user_excluded=getattr(attempt, USER_EXCLUDED_ANNOTATION)
    )
    return_to = current_return_to(request)
    history_url = build_exam_history_url(exam, return_to=return_to)
    supervision_feature_enabled = exam_supervision_enabled()

    if exam.exam_type == "coding" and not practical_exams_enabled():
        messages.error(request, practical_exam_disabled_message())
        return redirect(resolve_exam_failure_redirect(request))

    is_manual_supervision_lock = bool(
        supervision_feature_enabled and attempt.supervision_manual_lock and attempt.supervision_status == "locked"
    )
    if not is_manual_supervision_lock:
        # Audit 2026-09-13 EX-05 (P2) / 2026-09-28 EX28-04, EX28-07: GET də
        # grace-i gözləyir (`now − grace`) — ikinci tab / reload cəhdi grace
        # daxilində bağlayıb son təhvili itirməsin. Test/yazılı POST eyni
        # yoxlamanı kilid altında `_take_post_lock`-da edir.
        if request.method == "POST":
            attempt.expire_if_write_window_closed()
        else:
            attempt.expire_if_time_limit_reached()
    # If the resume window already lapsed before the student got here, finish now.
    if supervision_feature_enabled:
        attempt.expire_if_resume_window_expired()
    if attempt.is_finished:
        return finished_attempt_response(request, attempt, return_to=return_to)

    # Student is actually back in the exam → clear the pending "resumed" state
    # so the periodic sweep does not auto-finish an active student.
    if supervision_feature_enabled and attempt.supervision_status == "resumed":
        from apps.exams.services.supervision import mark_student_returned

        mark_student_returned(attempt)

    if request.method == "POST" and exam.exam_type != "coding":
        # Test/yazılı POST-u yuxarıdakı kilidli yol emal edir; buraya yalnız iki
        # sorğu arasında attempt-in tipi dəyişəndə düşülə bilər.
        raise Http404("Attempt changed during the request.")

    # Coding attempt-də cavablar yalnız «hələ yaradılmayıb?» yoxlaması üçündür;
    # variant/seçim yalnız test, fayllar yalnız yazılı səhifədə göstərilir.
    with_options = exam.exam_type == "test"
    answers_qs_kwargs = {"with_options": with_options, "with_files": exam.exam_type not in ("test", "coding")}
    answers = list(_attempt_answers_queryset(attempt, **answers_qs_kwargs))

    # P2 cleanup — attempt üçün hələ heç bir cavab yoxdursa (nadir: start-dan
    # sonra generate yarımçıq qalıb) generate-i bir dəfə çağır və yenidən yüklə.
    if not answers:
        if not attempt.answers.exists():
            generate_random_questions_for_attempt(attempt)
        answers = list(_attempt_answers_queryset(attempt, **answers_qs_kwargs))

    if not answers:
        message_key = (
            "exam_has_no_questions" if not exam.questions.filter(is_active=True).exists() else "exam_start_failed"
        )
        messages.error(request, pgettext("exams.view.access.message", message_key))
        return redirect(resolve_exam_failure_redirect(request))

    # Server tərəfli Vaxt Hesablaması
    # Audit 2026-09-28 EX28-07: `deadline_at` = min(start + müddət, end_datetime).
    remaining_seconds = None
    deadline = attempt.deadline_at
    if deadline is not None:
        remaining_seconds = max(0, int((deadline - timezone.now()).total_seconds()))

    if exam.exam_type == "coding":
        from apps.exams.services.supervision import get_attempt_supervision_status
        from apps.exams.views.student.coding import take_coding_exam

        return take_coding_exam(
            request,
            exam=exam,
            attempt=attempt,
            remaining_seconds=remaining_seconds,
            history_url=history_url,
            previous_attempts=_previous_attempts_for_context(request, exam, attempt),
            supervision=get_attempt_supervision_status(attempt),
        )

    questions = [a.question for a in answers]

    # ✅ Hər cavab üçün seçilmiş option ID-lərini set olaraq saxla
    answers_by_qid = _answers_by_question_id(answers, with_options=with_options)

    # GET sorğusu
    # Load supervision status
    from apps.exams.services.supervision import get_attempt_supervision_status

    supervision_data = get_attempt_supervision_status(attempt)

    # If attempt is locked/removed by supervision, show the locked state
    if attempt.supervision_status in ("locked", "removed") and not attempt.is_finished:
        pass  # Template will handle the locked overlay

    previous_attempts = _previous_attempts_for_context(request, exam, attempt)
    q_payload = build_take_exam_question_payload(exam, attempt, questions)

    context = {
        "exam": exam,
        "attempt": attempt,
        "questions": questions,
        "q_payload": q_payload,
        "answers_by_qid": answers_by_qid,
        "remaining_seconds": remaining_seconds,
        "history_url": history_url,
        "previous_attempts": previous_attempts,
        "previous_attempts_count": len(previous_attempts),
        "supervision": supervision_data,
        "exam_autosave_interval_ms": settings.EXAM_AUTOSAVE_INTERVAL_MS,
        "exam_autosave_jitter_ms": settings.EXAM_AUTOSAVE_JITTER_MS,
        "exam_autosave_binary_uploads_enabled": settings.EXAM_AUTOSAVE_BINARY_UPLOADS_ENABLED,
        "marked_question_ids_json": json.dumps(getattr(attempt, "marked_question_ids", None) or []),
        "autosave_revision": getattr(attempt, "autosave_revision", 0),
        "take_exam_script_data": take_exam_script_data(remaining_seconds),
    }
    return render(request, "exams/student/take_exam.html", context)
