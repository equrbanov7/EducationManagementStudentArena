"""results paketi — «Nəticəni sil (cəhdi sıfırla)» və «Qrup cəhdlərini sıfırla» (sahib 2026-11-04).

Yalnız RİM rəhbəri / imtahan mərkəzi rəhbəri / superadmin (``attempt_reset.can_reset_exam_attempts``);
müəllim (imtahanın müəllifi olsa belə) 403 alır — onun üçün köhnə «yalnız sınaq cəhdləri silinir»
(retention) qaydası ``delete_exam_attempts``-da dəyişmədən qalır. Səbəb məcburidir və audit sətrinə yazılır.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import pgettext
from django.views.decorators.http import require_GET, require_POST

from apps.exams.services import attempt_reset
from apps.exams.services.exam_attempt_purge import AUDIT_RESOURCE_TYPE
from apps.exams.views.shared.tenant import get_result_viewable_exam_or_404
from core.permissions import request_has_permission
from core.roles import is_superadmin_user

from ._group_index import build_group_index, resolve_group_options
from ._helpers import _append_query_params, _safe_same_origin_redirect_path

_CTX = "exams.attempt_reset"


def _blocker_label(code: str) -> str:
    labels = {
        "journal_locked": pgettext(_CTX, "jurnal bağlanıb (təsdiqlənib / dərc olunub) — əvvəl jurnalı açın"),
        "retake_links": pgettext(_CTX, "bu cəhdə 25% (yenidən imtahan) müraciəti bağlıdır"),
        "final_manual_restore_required": pgettext(
            _CTX, "əvvəlki sənədli imtahan balının bərpası ayrıca yoxlanmalıdır — cəhd silinmədi"
        ),
        "midterm_manual_restore_required": pgettext(
            _CTX, "əvvəlki sənədli midterm balının bərpası ayrıca yoxlanmalıdır — cəhd silinmədi"
        ),
        attempt_reset.FAILED_BLOCKER: pgettext(
            _CTX, "gözlənilməz texniki xəta — cəhd dəyişmədi, xəta qeydə alındı; RİM-ə bildirin"
        ),
    }
    return labels.get(code, code)


def _resettable_exam(request, slug):
    """Tenant daxilində imtahan + rol qapısı (müəllim → 403)."""
    exam = get_result_viewable_exam_or_404(request, slug=slug)
    if not attempt_reset.can_reset_exam_attempts(request.user, exam.organization):
        raise PermissionDenied(pgettext(_CTX, "Nəticəni yalnız RİM rəhbəri və imtahan mərkəzi rəhbəri silə bilər."))
    return exam


def _redirect_url(request, exam) -> str:
    return _safe_same_origin_redirect_path(request, request.POST.get("next")) or reverse(
        "exams:teacher_exam_results", kwargs={"slug": exam.slug}
    )


def _attempts_queryset(exam):
    return exam.attempts.select_related("exam", "exam__organization", "user").order_by("pk")


def _group_option(exam, raw):
    """Bu imtahanın qrup seçimlərindən biri («Qrupsuz» istisna) → ``(option, index)`` və ya ``(None, None)``."""
    index = build_group_index(exam)
    picked = [option for option in resolve_group_options(index, [raw]) if not option.is_none]
    return (picked[0], index) if picked else (None, None)


def _group_attempts(exam, option, index):
    return _attempts_queryset(exam).filter(user_id__in=index.user_ids_for(option)).exclude(is_trial=True)


def _report(request, summary) -> None:
    """Toplu nəticənin toast mesajları: sıfırlanan, rədd olunan (səbəbi ilə), tapılmayan, açılan biletlər."""
    if summary.reset_count:
        messages.success(
            request,
            pgettext(_CTX, "%(count)s cəhd sıfırlandı (nəticə silindi) — imtahanı yenidən vermək olar.")
            % {"count": summary.reset_count},
        )
    if summary.tickets_reset:
        messages.info(
            request,
            pgettext(
                _CTX,
                "%(count)s zal bileti yeni PIN ilə yenidən açıldı — PIN imtahan mərkəzinin oturum səhifəsindədir.",
            )
            % {"count": summary.tickets_reset},
        )
    for code, count in sorted(summary.blocker_counts.items()):
        messages.error(
            request,
            pgettext(_CTX, "%(count)s cəhd sıfırlanmadı: %(reason)s.")
            % {"count": count, "reason": _blocker_label(code)},
        )
    if summary.failed_ids:
        messages.error(
            request,
            pgettext(_CTX, "Sıfırlanmayan cəhdlər: %(ids)s.")
            % {"ids": ", ".join(f"#{pk}" for pk in summary.failed_ids)},
        )
    if summary.missing_count:
        messages.warning(
            request,
            pgettext(_CTX, "%(count)s cəhd tapılmadı (artıq silinib).") % {"count": summary.missing_count},
        )


#: ``bigint`` sərhədi — daha böyük «id» ``pk__in``-də ``DataError`` (500) verirdi.
_MAX_PK = 2**63 - 1


def _parse_attempt_ids(raw_ids) -> list[int]:
    """Yalnız ASCII rəqəmli, ``bigint`` daxilindəki id-lər (``"²".isdigit()`` → ``int`` xətası idi)."""
    ids = set()
    for raw in raw_ids:
        value = str(raw or "").strip()
        if value.isascii() and value.isdigit() and 0 < int(value) <= _MAX_PK:
            ids.add(int(value))
    return sorted(ids)


def _all_matching_attempt_ids(exam, post):
    """«Bütün N nəticəni seç»: cari süzgəcə uyğun cəhdləri SERVER özü müəyyən edir (bu imtahan daxilində).

    Klient ID siyahısı göndərmir — yalnız nəticələr səhifəsinin süzgəc sorğusunu (``filter_query``); eyni
    süzgəc funksiyası (``_apply_results_filters_from_params``) tətbiq olunur, ona görə seçim heç vaxt
    imtahanın və süzgəcin əhatəsindən kənara çıxa bilməz. Sınaq cəhdləri siyahıda yoxdur (səhifədəki kimi).
    """
    from django.http import QueryDict

    from ._helpers import _apply_results_filters_from_params

    params = QueryDict((post.get("filter_query") or "")[:4000])
    attempts, _state = _apply_results_filters_from_params(exam, params)
    return list(attempts.order_by().values_list("pk", flat=True))


@login_required
@require_POST
def reset_exam_attempts(request, slug):
    """Tək cəhd (``attempt_id``), seçilmişlər (``attempt_ids``) və ya süzgəcə uyğun hamısı — səbəblə sıfırla."""
    exam = _resettable_exam(request, slug)
    redirect_url = _redirect_url(request, exam)
    if (request.POST.get("select_scope") or "").strip() == "all_matching":
        attempt_ids = _all_matching_attempt_ids(exam, request.POST)
        expected = (request.POST.get("expected_count") or "").strip()
        # Təsdiq modalında göstərilən say ilə server sayı fərqlidirsə (siyahı arada dəyişib) — heç nə silinmir.
        if expected.isdigit() and int(expected) != len(attempt_ids):
            messages.error(
                request,
                pgettext(
                    _CTX,
                    "Siyahı dəyişib: təsdiqlədiyiniz %(expected)s nəticə əvəzinə indi %(actual)s nəticə uyğundur. "
                    "Heç nə silinmədi — səhifəni yoxlayıb yenidən cəhd edin.",
                )
                % {"expected": expected, "actual": len(attempt_ids)},
            )
            return redirect(redirect_url)
    else:
        raw_ids = request.POST.getlist("attempt_ids") + [request.POST.get("attempt_id") or ""]
        attempt_ids = _parse_attempt_ids(raw_ids)
    if not attempt_ids:
        messages.warning(request, pgettext(_CTX, "Sıfırlamaq üçün cəhd seçin."))
        return redirect(redirect_url)
    try:
        summary = attempt_reset.reset_attempts(
            list(_attempts_queryset(exam).filter(pk__in=attempt_ids)),
            actor=request.user,
            reason=request.POST.get("reason"),
            request=request,
        )
    except attempt_reset.ResetReasonError as error:
        messages.error(request, str(error))
        return redirect(redirect_url)
    if not summary.results:
        messages.warning(request, pgettext(_CTX, "Cəhd tapılmadı."))
    _report(request, summary)
    return redirect(redirect_url)


@login_required
@require_GET
def reset_group_preview(request, slug):
    """Yazısız ön baxış (JSON): seçilmiş qrupun neçə cəhdi sıfırlanacaq, neçəsi niyə bloklanıb."""
    exam = _resettable_exam(request, slug)
    option, index = _group_option(exam, request.GET.get("group"))
    if option is None:
        return JsonResponse({"ok": False, "error": pgettext(_CTX, "Qrup seçin.")}, status=400)
    preview = attempt_reset.preview_attempts(_group_attempts(exam, option, index))
    blockers = [
        {"code": code, "label": _blocker_label(code), "count": count}
        for code, count in sorted(preview.pop("blockers").items())
    ]
    return JsonResponse({"ok": True, "group": option.name, **preview, "blocker_list": blockers})


@login_required
@require_POST
def reset_group_attempts(request, slug):
    """Seçilmiş qrupun bütün (sınaq olmayan) cəhdləri — hər biri ayrıca tranzaksiyada."""
    exam = _resettable_exam(request, slug)
    redirect_url = _redirect_url(request, exam)
    option, index = _group_option(exam, request.POST.get("group"))
    if option is None:
        messages.warning(request, pgettext(_CTX, "Qrup seçin."))
        return redirect(redirect_url)
    try:
        summary = attempt_reset.reset_attempts(
            list(_group_attempts(exam, option, index)),
            actor=request.user,
            reason=request.POST.get("reason"),
            request=request,
        )
    except attempt_reset.ResetReasonError as error:
        messages.error(request, str(error))
        return redirect(redirect_url)
    if not summary.results:
        messages.info(request, pgettext(_CTX, "Bu qrupda sıfırlanacaq cəhd yoxdur."))
    _report(request, summary)
    return redirect(redirect_url)


def reset_page_context(request, exam) -> dict:
    """Nəticələr səhifəsi üçün: düymələr, qrup seçimi, səbəb qaydası və sıfırlama tarixçəsi (yalnız icazəlilərə)."""
    if exam.is_deleted or not attempt_reset.can_reset_exam_attempts(request.user, exam.organization):
        return {"can_reset_attempts": False}
    show_audit = is_superadmin_user(request.user) or request_has_permission(request, "audit.view")
    audit_url = ""
    if show_audit:
        audit_url = _append_query_params(
            reverse("accounts:profile"),
            section="audit-log",
            al_resource=f"rt:{AUDIT_RESOURCE_TYPE}",
            al_range="all",
            al_q=exam.slug,
        )
    return {
        "can_reset_attempts": True,
        "reset_reason_min": attempt_reset.REASON_MIN_LENGTH,
        "reset_reason_max": attempt_reset.REASON_MAX_LENGTH,
        "reset_history": attempt_reset.exam_reset_history(exam),
        "reset_audit_url": audit_url,
    }


__all__ = ["reset_exam_attempts", "reset_group_attempts", "reset_group_preview", "reset_page_context"]
