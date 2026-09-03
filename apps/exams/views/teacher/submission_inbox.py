"""
Sual göndərişi view-ları.

Müəllim tərəfi: yeni göndəriş (preview → göndər), öz göndərişinin detalı,
düzəldib yenidən göndərmə. İmtahan mərkəzi tərəfi: qutu (inbox) və baxış
(qəbul → banka yaz / rədd → qeyd).
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST

from apps.exams.constants import EXAM_LANGUAGE_CHOICES
from apps.exams.models import QuestionSubmission
from apps.exams.services.access_policy import _ensure_teacher, is_exam_center_user
from apps.exams.services.question_submission import (
    resubmit_question_set,
    submit_question_set,
)
from apps.exams.views.teacher.submission_meta import (
    _form_state,
    _teacher_groups,
    _teacher_subjects,
    _validate_submission_meta,
    annotate_preview_flags,
)
from apps.exams.views.teacher.submission_workbench import (
    build_workbench_context,
    initial_workbench_state,
    process_workbench_post,
)
from core.tenancy import get_request_organization


def _profile_section_url(section):
    return f"{reverse('accounts:profile')}?section={section}"


def _require_organization(request):
    organization = get_request_organization(request)
    if organization is None:
        raise PermissionDenied(
            pgettext("exams.view.question_submission.permission", "Aktiv təşkilat konteksti tapılmadı.")
        )
    return organization


# ---------------------------------------------------------------------------
# Müəllim: yeni göndəriş (toplu sual workbench dizaynı ilə)
# ---------------------------------------------------------------------------
@login_required
def question_submission_create(request):
    """
    Yeni göndəriş — sual bankı "toplu əlavə" workbench-i ilə EYNİ UI:
    fayl yüklə (PDF/TXT/PNG/JPG), redaktor, AI generasiya, önizləmə + xəta/
    xəbərdarlıq kartları, sual seçimi. Fərq: sonda "İmtahan mərkəzinə göndər".
    """
    _ensure_teacher(request.user)
    organization = _require_organization(request)
    groups = list(_teacher_groups(request, organization))

    from apps.exams.views.teacher.question_library._shared import _empty_analysis

    state = {
        "analysis": _empty_analysis(),
        "parsed": [],
        "selected": set(),
        "raw_text": "",
        "math_token": (request.POST.get("math_token") or "").strip(),
    }
    form_state = {
        "title": "",
        "subject": "",
        "exam_kind": "",  # default seçim YOX — imtahan növü şüurlu seçilməlidir
        "group_ids": [],
        "group_id": "",
        "group_label": "",
        "teacher_note": "",
        "language_raw": "",  # default seçim YOX — dil məcburi şüurlu seçilməlidir
        "language": "",
        "raw_text": "",
    }

    if request.method == "POST":
        form_state = _form_state(request)
        state = process_workbench_post(request, organization, form_state)

        if state["action"] == "save":
            _err, chosen_groups, group_label, subject_obj = _validate_submission_meta(
                form_state,
                groups=groups,
                subjects=_teacher_subjects(request, organization, groups=groups),
            )

            if _err:
                messages.error(request, _err)
            else:
                try:
                    submission = submit_question_set(
                        teacher=request.user,
                        organization=organization,
                        title=form_state["title"],
                        subject=subject_obj.name,
                        subject_ref=subject_obj,
                        exam_kind=form_state["exam_kind"],
                        student_group=chosen_groups[0],
                        group_label=group_label,
                        language=form_state["language"],
                        raw_text=state["raw_text"],
                        groups=chosen_groups,
                        parsed=state["chosen"],
                        teacher_note=form_state["teacher_note"],
                        import_token=state["math_token"],
                    )
                except ValidationError as exc:
                    messages.error(request, exc.messages[0])
                else:
                    messages.success(
                        request,
                        pgettext(
                            "exams.view.question_submission.message",
                            "Göndəriş kafedra müdirinin təsdiqinə göndərildi ({count} sual, {groups} qrup).",
                        ).format(count=submission.question_count, groups=len(chosen_groups)),
                    )
                    return redirect("exams:question_submission_detail", submission_id=submission.id)

    context = build_workbench_context(
        request,
        organization,
        groups,
        form_state,
        analysis=state["analysis"],
        parsed=state["parsed"],
        selected=state["selected"],
        raw_text=state["raw_text"],
        math_token=state["math_token"],
        title=pgettext("exams.template.question_submission", "Kafedra təsdiqinə sual göndər"),
        subtitle=pgettext(
            "exams.template.question_submission",
            "Sualları yazın və ya fayl yükləyin, önizləyin — xəbərdarlıqları görün, sonra kafedra "
            "müdirinə göndərin; təsdiqdən sonra İmtahan Mərkəzinə çatacaq.",
        ),
        save_label=pgettext("exams.template.question_submission", "Kafedra müdirinə göndər"),
    )
    context.update(
        {
            # Profil örtüyü: sidebar solda qalsın, workbench sağda göstərilsin.
            "embed_active_section": "question-submissions",
            # Profil header-i (embed): başlıq + mobil sidebar düyməsi.
            "embed_section_title": pgettext("exams.template.question_submission", "Sual göndərişi"),
        }
    )
    return render(request, "exams/teacher/question_submission_form.html", context)


@login_required
@require_POST
def ai_generate_submission_questions(request):
    """Göndəriş workbench-inin AI kartı — bank/imtahan AI axını ilə eyni mexanizm."""
    _ensure_teacher(request.user)
    _require_organization(request)

    from apps.exams.views.teacher.extract_jobs import start_ai_generation_job

    payload = {
        "exam_title": pgettext("exams.view.question_submission.ai", "Sual göndərişi"),
        "exam_type": "test",
        "prompt_text": request.POST.get("prompt", ""),
        "source_text": (request.POST.get("source_text") or "").strip(),
        "question_count": request.POST.get("question_count") or 5,
        "difficulty": request.POST.get("difficulty") or "medium",
        "block_name": "",
        "language_code": request.LANGUAGE_CODE,
        "user_id": request.user.pk,
    }
    return start_ai_generation_job(
        request,
        payload=payload,
        uploaded=request.FILES.get("source_file") or request.FILES.get("ai_source_file"),
        service_error_message=pgettext(
            "exams.view.question_submission.ai", "AI sual yaratma alınmadı. Bir az sonra yenidən yoxlayın."
        ),
    )


# ---------------------------------------------------------------------------
# Müəllim: detal + düzəlt/yenidən göndər
# ---------------------------------------------------------------------------
@login_required
def question_submission_detail(request, submission_id):
    _ensure_teacher(request.user)
    organization = _require_organization(request)
    submission = get_object_or_404(QuestionSubmission, id=submission_id, organization=organization)

    # Mərkəz göndərişi YALNIZ kafedra təsdiqindən sonra görür (mövcudluq
    # sızmasın deyə əks halda 404 — «var, amma icazən yoxdur» demirik).
    is_reviewer = is_exam_center_user(request.user) and submission.has_reached_center
    if submission.teacher_id != request.user.id and not is_reviewer:
        raise Http404()

    can_edit = submission.teacher_id == request.user.id and submission.can_be_edited_by_teacher

    # Redaktə YENİ GÖNDƏRİŞLƏ EYNİ workbench UI-dadır (fayl yüklə, AI, önizləmə
    # kartları, sual seçimi) — action=save yenidən göndərmə deməkdir.
    if request.method == "POST":
        if not can_edit:
            raise PermissionDenied(
                pgettext("exams.view.question_submission.permission", "Bu göndəriş dəyişdirilə bilməz.")
            )
        form_state = _form_state(request)
        _groups = list(_teacher_groups(request, organization))
        state = process_workbench_post(request, organization, form_state)

        if state["action"] == "save":
            _err, chosen_groups, group_label, subject_obj = _validate_submission_meta(
                form_state,
                groups=_groups,
                subjects=_teacher_subjects(request, organization, groups=_groups),
            )
            if _err:
                messages.error(request, _err)
            else:
                try:
                    submission = resubmit_question_set(
                        submission,
                        title=form_state["title"],
                        subject=subject_obj.name,
                        subject_ref=subject_obj,
                        exam_kind=form_state["exam_kind"],
                        student_group=chosen_groups[0],
                        group_label=group_label,
                        language=form_state["language"],
                        raw_text=state["raw_text"],
                        groups=chosen_groups,
                        parsed=state["chosen"],
                        teacher_note=form_state["teacher_note"],
                        import_token=state["math_token"],
                    )
                except ValidationError as exc:
                    messages.error(request, exc.messages[0])
                else:
                    messages.success(
                        request,
                        pgettext(
                            "exams.view.question_submission.message",
                            "Göndəriş yeniləndi və kafedra müdirinin təsdiqinə təkrar göndərildi.",
                        ),
                    )
                    return redirect("exams:question_submission_detail", submission_id=submission.id)

        # Preview (və ya xəta ilə yarımçıq save) — workbench vəziyyəti ilə render.
        context = _detail_context(submission, can_edit=can_edit, is_reviewer=is_reviewer)
        context.update(_detail_workbench_context(request, organization, _groups, submission, form_state, state))
        return render(request, "exams/teacher/question_submission_detail.html", context)

    context = _detail_context(submission, can_edit=can_edit, is_reviewer=is_reviewer)
    if can_edit:
        _groups = list(_teacher_groups(request, organization))
        state = initial_workbench_state(
            request,
            organization,
            raw_text=submission.raw_text,
            math_token=submission.import_token,
        )
        context.update(
            _detail_workbench_context(request, organization, _groups, submission, context["form_state"], state)
        )
    return render(request, "exams/teacher/question_submission_detail.html", context)


def _detail_workbench_context(request, organization, groups, submission, form_state, state):
    """Detal redaktəsinin workbench konteksti — yeni göndərişlə eyni qurucu,
    yalnız başlıq/etiketlər fərqlidir."""
    if submission.status == QuestionSubmission.STATUS_REJECTED:
        save_label = pgettext("exams.template.question_submission", "Düzəlt və yenidən göndər")
    else:
        save_label = pgettext("exams.template.question_submission", "Yenidən göndər")
    context = build_workbench_context(
        request,
        organization,
        groups,
        form_state,
        analysis=state["analysis"],
        parsed=state["parsed"],
        selected=state["selected"],
        raw_text=state["raw_text"],
        math_token=state["math_token"],
        title=pgettext("exams.template.question_submission", "Göndərişi redaktə et"),
        subtitle=pgettext(
            "exams.template.question_submission",
            "Sualları düzəldin və ya yenidən yükləyin, önizləyin — sonra təkrar göndərin.",
        ),
        save_label=save_label,
    )
    # Detal səhifəsinin öz qb-header-i (üst sağda «Göndərişlərə qayıt») var —
    # workbench-in daxili header-i eyni linki TƏKRARLAYIRDI. Yalnız geri-link
    # gizlədilir (wb_hide_header YOX: o, canlı parse statistikalarını da aparardı).
    context["wb_hide_back_link"] = True
    return context


@login_required
@require_POST
def question_submission_delete(request, submission_id):
    """Müəllim öz göndərişini silir (yalnız hələ baxılmamış «pending» və ya geri
    qaytarılmış «rejected» göndəriş). Qəbul olunmuş göndəriş silinə bilməz."""
    _ensure_teacher(request.user)
    organization = _require_organization(request)
    submission = get_object_or_404(QuestionSubmission, id=submission_id, organization=organization)
    if submission.teacher_id != request.user.id:
        raise Http404()
    if not submission.can_be_edited_by_teacher:
        messages.error(
            request,
            pgettext(
                "exams.view.question_submission.error",
                "Qəbul olunmuş göndəriş silinə bilməz.",
            ),
        )
        return redirect("exams:question_submission_detail", submission_id=submission.id)
    import_token = submission.import_token
    submission.delete()
    if import_token:
        from apps.exams.services.import_media import clear_stash

        clear_stash(import_token)
    messages.success(
        request,
        pgettext("exams.view.question_submission.message", "Göndəriş silindi."),
    )
    return redirect(_profile_section_url("question-submissions"))


def _detail_context(submission, *, can_edit, is_reviewer):
    return {
        "embed_active_section": "question-submissions",
        "embed_section_title": submission.title,
        "submission": submission,
        "submission_events": list(submission.events.select_related("actor")),
        "parsed_questions": annotate_preview_flags(list(submission.parsed_snapshot or [])),
        "can_edit": can_edit,
        "is_reviewer": is_reviewer,
        "language_choices": EXAM_LANGUAGE_CHOICES,
        "form_state": {
            "title": submission.title,
            # Fənn seçimi pk ilə işləyir; köhnə (ref-siz) göndərişdə boş qalır —
            # müəllim yenidən göndərərkən fənnini təzədən seçir.
            "subject": str(submission.subject_ref_id or ""),
            "exam_kind": submission.exam_kind,
            "group_ids": [str(g.id) for g in submission.student_groups.all()]
            or [str(submission.student_group_id or "")],
            "group_id": str(submission.student_group_id or ""),
            "group_label": submission.group_label,
            "teacher_note": submission.teacher_note,
            "language_raw": submission.language,
            "language": submission.language,
            "raw_text": submission.raw_text,
        },
        "back_url": _profile_section_url("question-submissions"),
    }


__all__ = [
    "ai_generate_submission_questions",
    "question_submission_create",
    "question_submission_delete",
    "question_submission_detail",
]
