"""teacher questions paketi — sual sil/deaktiv mutasiyası və «imtahan deaktiv edilsin?» təsdiqi.

QB 2026-09-30 (sahib): seçim aktiv imtahanın BÜTÜN aktiv suallarını əhatə edəndə
müəllim dalana dirənmir:

* AJAX (``X-Requested-With``) sorğusu → 409 JSON ``exam_deactivation_required``
  + təsdiq mətnləri; UI bunu ``EMSConfirm`` dialoquna çevirir və razılıqda
  ``confirm_exam_deactivation=1`` ilə təkrar göndərir;
* JS-siz (adi form) sorğu → server tərəfi təsdiq səhifəsi (``confirm_delete.html``)
  eyni sahələrlə + təsdiq bayrağı ilə;
* imtahan hazırda istifadədədirsə (açıq cəhd / canlı sessiya / final zal) →
  səbəbi adlandıran xəta, heç nə dəyişmir.

İmtahanı deaktiv etmək ``exam.edit`` icazəsi tələb edir (``toggle_exam_active``
ilə eyni siyasət) — icazə yoxdursa təsdiq təklif olunmur.
"""

import logging

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import pgettext

from apps.exams.services.question_invariants import (
    MODE_DELETE,
    ActiveExamRequiresQuestion,
    ExamInUse,
    QuestionsHaveAnswers,
    remove_exam_questions,
)
from core.permissions import request_has_permission

from ._shared import _resequence_exam_questions

logger = logging.getLogger(__name__)

CONFIRM_FIELD = "confirm_exam_deactivation"
_GUARD_CTX = "exams.view.questions_bank.guard"
_NOT_REPLAYED_FIELDS = {"csrfmiddlewaretoken", CONFIRM_FIELD}


def wants_json(request) -> bool:
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


def finish_mutation_request(request, redirect_url):
    """Uğurlu (və ya adi mesajlı) POST-un sonu: AJAX-a JSON, adi formaya yönləndirmə."""
    if wants_json(request):
        return JsonResponse({"ok": True, "redirect_url": redirect_url})
    return redirect(redirect_url)


def _error_text(exc) -> str:
    return " ".join(str(message) for message in exc.messages)


def _refuse(request, message, redirect_url, *, code):
    if wants_json(request):
        return JsonResponse({"ok": False, "code": code, "message": message}, status=409)
    messages.error(request, message)
    return redirect(redirect_url)


def _confirmation_texts(mode) -> dict:
    if mode == MODE_DELETE:
        body = pgettext(
            _GUARD_CTX,
            "Bu imtahanın bütün aktiv sualları silinəcək — imtahan deaktiv ediləcək. Davam edilsin?",
        )
    else:
        body = pgettext(
            _GUARD_CTX,
            "Bu imtahanın bütün aktiv sualları deaktiv ediləcək — imtahan da deaktiv ediləcək. Davam edilsin?",
        )
    return {
        "title": pgettext(_GUARD_CTX, "İmtahan deaktiv ediləcək"),
        "body": body,
        "confirm_label": pgettext(_GUARD_CTX, "Bəli, davam et"),
    }


def _ask_confirmation(request, *, mode, cancel_url):
    texts = _confirmation_texts(mode)
    if wants_json(request):
        return JsonResponse(
            {
                "ok": False,
                "code": "exam_deactivation_required",
                "confirm_field": CONFIRM_FIELD,
                "confirm": texts,
            },
            status=409,
        )
    # JS-siz geri düşmə: eyni POST sahələri + təsdiq bayrağı ilə server təsdiq səhifəsi.
    hidden_fields = [
        (name, value)
        for name in request.POST
        if name not in _NOT_REPLAYED_FIELDS
        for value in request.POST.getlist(name)
    ]
    hidden_fields.append((CONFIRM_FIELD, "1"))
    return render(
        request,
        "exams/teacher/confirm_delete.html",
        {
            "confirm_title": texts["title"],
            "confirm_message": texts["body"],
            "confirm_action": request.path,
            "confirm_hidden_fields": hidden_fields,
            "confirm_submit_label": texts["confirm_label"],
            # QA 2026-09-30: deaktivasiya təsdiqində zibil qutusu ikonu yanıldırdı.
            "confirm_icon": "fa-trash-alt" if mode == MODE_DELETE else "fa-eye-slash",
            "cancel_url": cancel_url,
        },
    )


def run_question_mutation(request, exam, *, mode, question_ids, redirect_url, success_message=""):
    """Sualları sil/deaktiv et. Axın dayanmalıdırsa ``HttpResponse``, əks halda ``None``.

    ``None`` qayıdanda uğur mesajları artıq növbəyə qoyulub — çağıran
    ``finish_mutation_request`` ilə sorğunu bitirir.
    """
    # İcazə yoxlaması yalnız lazım olanda (superadmin cross-org yoxlaması audit yazır).
    confirm_requested = request.POST.get(CONFIRM_FIELD) == "1"
    confirmed = confirm_requested and request_has_permission(request, "exam.edit")
    try:
        outcome = remove_exam_questions(
            exam,
            question_ids,
            mode=mode,
            deactivate_exam=confirmed,
            by_user=request.user,
            request=request,
        )
    except ExamInUse as exc:
        return _refuse(request, _error_text(exc), redirect_url, code="exam_in_use")
    except QuestionsHaveAnswers as exc:
        return _refuse(request, _error_text(exc), redirect_url, code="questions_have_answers")
    except ActiveExamRequiresQuestion as exc:
        # Təsdiq gəlib, amma icazə yoxdur — və ya icazəsizə təsdiq təklif etmirik.
        if confirm_requested or not request_has_permission(request, "exam.edit"):
            return _refuse(request, _error_text(exc), redirect_url, code="active_exam_requires_question")
        return _ask_confirmation(request, mode=mode, cancel_url=redirect_url)
    except ValidationError as exc:
        return _refuse(request, _error_text(exc), redirect_url, code="invalid")
    except IntegrityError:
        # Əvvəllər istənilən IntegrityError «son aktiv sual» mətni ilə göstərilirdi
        # (yanıldıcı idi) — indi ümumi xəta + log.
        logger.exception("Exam question %s failed for exam %s", mode, exam.pk)
        return _refuse(
            request,
            pgettext(_GUARD_CTX, "Əməliyyat alınmadı. Səhifəni yeniləyib yenidən cəhd edin."),
            redirect_url,
            code="integrity_error",
        )

    if mode == MODE_DELETE:
        _resequence_exam_questions(exam)
    if success_message:
        messages.success(request, success_message.format(count=outcome.count))
    if outcome.exam_deactivated:
        messages.info(
            request,
            pgettext(
                _GUARD_CTX,
                "İmtahan deaktiv edildi (dərcdən çıxarıldı). Yeni suallar əlavə edib yenidən dərc edə bilərsiniz.",
            ),
        )
    return None


__all__ = ["CONFIRM_FIELD", "finish_mutation_request", "run_question_mutation", "wants_json"]
