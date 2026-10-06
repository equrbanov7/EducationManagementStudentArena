from django.urls import reverse
from django.utils import timezone

# Faza 5 (audit 2026-07-02): URL/redirect köməkçiləri apps/exams/navigation-a
# köçürüldü (servis qatı ilə ortaq istifadə). Aşağıdakı re-exportlar mövcud
# `from ._helpers import ...` çağırışlarının import səthini qoruyur.
from apps.exams.navigation import (  # noqa: F401
    append_query_params,
    append_return_to,
    build_exam_history_url,
    build_exam_result_url,
    current_return_to,
    safe_same_origin_redirect_path,
)
from core.helpers import REVIEW_EDIT_LOCK_WINDOW
from core.tenancy import request_has_active_organization_context, restore_request_organization_from_profile


def ensure_student_exam_tenant_context(request):
    if request_has_active_organization_context(request):
        return True
    return restore_request_organization_from_profile(request, profile=getattr(request.user, "profile", None))


def resolve_exam_failure_redirect(request):
    """İmtahan başlamayanda tələbəni gəldiyi siyahıya qaytarır."""
    explicit_next = safe_same_origin_redirect_path(request, request.GET.get("next") or request.POST.get("next"))
    if explicit_next:
        return explicit_next

    source_section = (request.GET.get("from_section") or request.POST.get("from_section") or "").strip()
    if source_section == "assigned-exams":
        assigned_type = (request.GET.get("assigned_type") or request.POST.get("assigned_type") or "all").strip().lower()
        allowed_types = {"all", "exams", "courses", "assignments", "labs", "independent"}
        if assigned_type not in allowed_types:
            assigned_type = "all"
        return f"{reverse('accounts:profile')}?section=assigned-exams&assigned_type={assigned_type}"

    return reverse("exams:student_exam_list")


def resolve_author_failure_redirect(request, exam):
    """İmtahanın müəllifini öz idarəetmə səhifəsinə, tələbəni siyahıya qaytarır."""
    if exam.author_id == request.user.id:
        return reverse("exams:teacher_exam_detail", kwargs={"slug": exam.slug})
    return resolve_exam_failure_redirect(request)


def are_exam_results_hidden_from_student(exam):
    return bool(getattr(exam, "results_hidden_from_students", False))


def annotate_attempt_result_visibility(attempts, *, current_time=None):
    now = current_time or timezone.now()
    prepared_attempts = []

    for attempt in attempts:
        result_hidden_by_teacher = are_exam_results_hidden_from_student(attempt.exam)
        can_view_result = not result_hidden_by_teacher and attempt.exam.exam_type in {"test", "coding"}
        review_available_in_seconds = 0

        if result_hidden_by_teacher:
            can_view_result = False
        elif attempt.exam.exam_type not in {"test", "coding"}:
            if attempt.checked_by_teacher:
                if attempt.teacher_checked_at:
                    reveal_at = attempt.teacher_checked_at + REVIEW_EDIT_LOCK_WINDOW
                    can_view_result = now >= reveal_at
                    if not can_view_result:
                        review_available_in_seconds = max(0, int((reveal_at - now).total_seconds()))
                else:
                    can_view_result = True
            else:
                can_view_result = True

        attempt.can_view_result = can_view_result
        attempt.review_available_in_seconds = review_available_in_seconds
        attempt.result_hidden_by_teacher = result_hidden_by_teacher
        prepared_attempts.append(attempt)

    return prepared_attempts


def posted_autosave_question_ids(request, *, action):
    """Autosave POST-undakı dəyişmiş sual id-ləri (yoxdursa None = full save)."""
    if action != "autosave":
        return None
    raw_ids = request.POST.getlist("changed_questions[]") or request.POST.getlist("changed_questions")
    parsed_ids = set()
    for raw_id in raw_ids:
        try:
            parsed_ids.add(int(raw_id))
        except (TypeError, ValueError):
            continue
    return parsed_ids


def finish_skips_absent_question(request, question_id, *, form_has_presence_markers):
    """EXAM-P1-05: finish zamanı timer-expired (q_present markeri absent) sualı
    ötür ki, boş POST saxlanmış cavabı silməsin. Markersiz (köhnə/keşlənmiş)
    formada köhnə davranış qalır (geriyə-uyğun)."""
    return form_has_presence_markers and request.POST.get(f"q_present_{question_id}") != "1"


def autosave_occ_conflict_response(request, attempt, action):
    """EXAM-P1-06: autosave optimistic concurrency yoxlaması.

    Client öz bildiyi ``autosave_revision``-u göndərir. Server daha yenidirsə
    (başqa tab yazıb) stale yazını rədd edən 409 JsonResponse qaytarır; əks
    halda (uyğun və ya base yoxdur) None. base_revision yoxdursa geriyə-uyğun.
    """
    from django.http import JsonResponse
    from django.utils.translation import pgettext

    from apps.exams.metrics import record_autosave

    base_raw = (request.POST.get("autosave_revision") or "").strip()
    if not base_raw:
        return None
    try:
        base_revision = int(base_raw)
    except (TypeError, ValueError):
        return None
    if base_revision == attempt.autosave_revision:
        return None
    replay = _autosave_replay_response(request, attempt, action, base_revision)
    if replay is not None:
        return replay
    if action == "autosave":
        record_autosave("conflict")
    message = pgettext(
        "exams.view.access.message",
        "Bu imtahan başqa bir tab/pəncərədə yenilənib. Ən son cavabları görmək üçün səhifəni yeniləyin.",
    )
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        from django.contrib import messages
        from django.shortcuts import redirect

        messages.error(request, message)
        return redirect(request.get_full_path())
    return JsonResponse(
        {
            "success": False,
            "conflict": True,
            "server_revision": attempt.autosave_revision,
            "message": message,
        },
        status=409,
    )


# Tutum testi 2026-10-05: yük altında autosave serverdə yazılır, amma cavab klientə
# çatmır (nginx 504 / şəbəkə). Klient eyni cavabları KÖHNƏ revision ilə təkrar göndərir
# və 409 alır → autosave «səhifəni yeniləyin» ilə donur. Son uğurlu autosave-in
# barmaq izi saxlanır; eyni məzmunlu, düz bir revision geridə qalan təkrar yazısız
# uğur sayılır (server vəziyyəti həmin sorğunun nəticəsinin özüdür).
_AUTOSAVE_REPLAY_TTL = 600


def _autosave_replay_key(attempt):
    return f"exam:autosave:last:{attempt.pk}"


def _autosave_fingerprint(request):
    import hashlib

    items = sorted(
        (key, tuple(request.POST.getlist(key)))
        for key in request.POST.keys()
        if key.startswith("q_") or key == "changed_questions[]"
    )
    return hashlib.sha256(repr(items).encode()).hexdigest()


def remember_autosave_write(request, attempt, action):
    """Uğurlu autosave-in (revision, barmaq izi) qeydi — təkrar göndərişi tanımaq üçün."""
    if action != "autosave" or request.FILES:
        return
    from django.core.cache import cache

    try:
        cache.set(
            _autosave_replay_key(attempt),
            {"rev": attempt.autosave_revision, "fp": _autosave_fingerprint(request)},
            _AUTOSAVE_REPLAY_TTL,
        )
    except Exception:  # noqa: BLE001 — keş əlçatmazdırsa sadəcə köhnə davranış (409)
        pass


def _autosave_replay_response(request, attempt, action, base_revision):
    if action != "autosave" or request.FILES or base_revision != attempt.autosave_revision - 1:
        return None
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        return None
    from django.core.cache import cache
    from django.http import JsonResponse

    try:
        last = cache.get(_autosave_replay_key(attempt))
    except Exception:  # noqa: BLE001
        return None
    if not last or last.get("rev") != attempt.autosave_revision or last.get("fp") != _autosave_fingerprint(request):
        return None
    from apps.exams.metrics import record_autosave

    record_autosave("success")
    return JsonResponse(
        {"success": True, "finished": False, "server_revision": attempt.autosave_revision, "replayed": True}
    )


def bump_autosave_revision(attempt):
    """Uğurlu yazıdan sonra attempt-in autosave revision-unu atomik artır.

    Perf 2026-10-06: PostgreSQL-də ``UPDATE … RETURNING`` — yeni dəyər eyni
    round-trip-də qayıdır (əvvəl UPDATE + ``refresh_from_db`` SELECT-i idi).
    Artım yenə DB tərəfində (``col + 1``) olur; nəticə DB-nin öz dəyəridir.
    """
    from django.db import connections, router
    from django.db.models import F

    model = type(attempt)
    connection = connections[router.db_for_write(model, instance=attempt)]
    if connection.vendor == "postgresql":
        quote = connection.ops.quote_name
        column = quote(model._meta.get_field("autosave_revision").column)
        with connection.cursor() as cursor:
            cursor.execute(
                f"UPDATE {quote(model._meta.db_table)} SET {column} = {column} + 1 "
                f"WHERE {quote(model._meta.pk.column)} = %s RETURNING {column}",
                [attempt.pk],
            )
            row = cursor.fetchone()
        if row is not None:
            attempt.autosave_revision = row[0]
            return
    model.objects.filter(pk=attempt.pk).update(autosave_revision=F("autosave_revision") + 1)
    attempt.refresh_from_db(fields=["autosave_revision"])


def build_take_exam_question_payload(exam, attempt, questions):
    """take_exam slide payload-u: hər sual üçün {q, opts, server_delivery}.

    EXAM-P1-04 strict delivery: yeni-protokol attempt-də vaxtlı test sualının
    məzmunu (mətn/variant/media/düzgün cavab) İLK GET-də səhifə mənbəyinə düşmür
    — ``server_delivery`` işarələnir, variantlar boş buraxılır və məzmun timer
    serverdə başlayandan sonra ``question-seen`` ilə gəlir.
    """
    from apps.exams.services.option_tokens import option_token
    from apps.exams.services.question_timer import question_timer_start_required
    from apps.exams.services.randomizer import build_shuffled_options

    payload = []
    for question in questions:
        opts = []
        strict_delivery = exam.exam_type == "test" and question_timer_start_required(attempt, question)
        if not strict_delivery and exam.exam_type == "test" and question.answer_mode in ("single", "multiple"):
            opts = build_shuffled_options(attempt.id, question)
            # Audit 2026-09-28 EX28-01: input ``value``-su xam id deyil, token.
            # ``id`` yalnız server tərəfdə ``checked`` müqayisəsi üçün qalır.
            for opt in opts:
                opt["token"] = option_token(attempt.id, opt["id"])
        payload.append({"q": question, "opts": opts, "server_delivery": strict_delivery})
    return payload


def _request_attempt_id(request, attempt=None):
    """Token xəritələməsi üçün attempt id-si: açıq ötürülən attempt, yoxsa URL."""
    if attempt is not None:
        return getattr(attempt, "pk", attempt)
    resolver_match = getattr(request, "resolver_match", None)
    kwargs = getattr(resolver_match, "kwargs", None) or {}
    return kwargs.get("attempt_id")


def selected_option_ids_from_request(request, question, attempt=None):
    """POST-dan bir sual üçün seçilmiş option id-lərini (single/multi) parse et.

    Audit 2026-09-28 EX28-01: tələbə xam ``option.id`` deyil, attempt-ə bağlı
    token göndərir (``services/option_tokens.py``); burada sualın öz
    variantları arasında geri xəritələnir. Qaytarır: ``set[int]`` və ya
    ``None`` — dəyər göndərilib, amma heç biri tanınmayıb (saxta/köhnə səhifə);
    ``_save_test_answer_if_changed`` ``None``-u "seçimi dəyişmə" kimi oxuyur.
    """
    from apps.exams.services.option_tokens import option_ids_from_tokens

    field_name = f"q_{question.id}"
    if question.answer_mode == "single":
        raw_values = [request.POST.get(field_name) or ""]
    else:
        raw_values = request.POST.getlist(field_name)
    if not any(str(value).strip() for value in raw_values):
        return set()

    attempt_id = _request_attempt_id(request, attempt)
    if attempt_id is None:
        return None
    option_ids = [option.id for option in question.options.all()]
    return option_ids_from_tokens(attempt_id, option_ids, raw_values)
