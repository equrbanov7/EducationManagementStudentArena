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

from apps.exams.constants import EXAM_LANGUAGE_CHOICES, EXAM_LANGUAGE_VALUES
from apps.exams.models import QuestionBank, QuestionSubmission, StudentGroup
from apps.exams.services.access_policy import _ensure_teacher, is_exam_center_user
from apps.exams.services.bulk_workbench import (
    analyze_mcq_bulk,
    parse_points_payload,
    parse_selected_indices,
)
from apps.exams.services.question_submission import (
    accept_submission,
    analyze_submission_text,
    ensure_can_review_submission,
    reject_submission,
    resubmit_question_set,
    submit_question_set,
)
from apps.exams.services.visual_import_upload import prepare_question_upload
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


def _normalize_language(raw_value):
    value = (raw_value or "").strip().lower()
    return value if value in EXAM_LANGUAGE_VALUES else "az"


def _form_state(request):
    raw_language = (request.POST.get("language") or "").strip().lower()
    return {
        "title": (request.POST.get("title") or "").strip(),
        "subject": (request.POST.get("subject") or "").strip(),
        # Çox qrup seçimi: `group_ids` (getlist). `group_id` geriyə-uyğunluq üçün.
        "group_ids": [g for g in request.POST.getlist("group_ids") if str(g).strip().isdigit()],
        "group_id": (request.POST.get("group_id") or "").strip(),
        "group_label": (request.POST.get("group_label") or "").strip(),
        "teacher_note": (request.POST.get("teacher_note") or "").strip(),
        # Xam dil (validasiya üçün) + normalizə olunmuş dəyər (saxlama üçün).
        "language_raw": raw_language,
        "language": _normalize_language(raw_language),
        "raw_text": request.POST.get("raw_text") or "",
    }


def _teacher_groups(request, organization):
    """Müəllimin bu təşkilatdakı qrupları (dropdown üçün) — fənlərlə birlikdə."""
    from django.db.models import Q

    return (
        StudentGroup.objects.filter(organization=organization)
        .filter(Q(teacher=request.user) | Q(teachers=request.user))
        .prefetch_related("subjects")
        .distinct()
        .order_by("name")
    )


def _teacher_subjects(request, organization, *, groups=None):
    """Müəllimin ÖZ fənləri — təyin olunduğu qrupların fənlərinin birləşməsi
    (registrar.Subject). Sual göndərişində fənn seçimi bu siyahıdan gəlir
    (qrupdan asılı deyil — 2026-07 dəyişikliyi)."""
    from apps.registrar.models import Subject

    group_ids = [g.id for g in (groups if groups is not None else _teacher_groups(request, organization))]
    if not group_ids:
        return Subject.objects.none()
    return (
        Subject.objects.filter(organization=organization, student_groups__in=group_ids)
        .distinct()
        .order_by("code", "name")
    )


def _resolve_groups(form_state, groups):
    """Formadan seçilmiş qrupları həll edir (çox qrup). Yalnız müəllimə təyin
    olunmuş qruplar qəbul edilir. Qaytarır: (seçilmiş qruplar, birləşdirilmiş etiket)."""
    ids = {str(g) for g in form_state.get("group_ids", [])}
    if not ids and form_state.get("group_id"):  # geriyə-uyğunluq (tək seçim)
        ids = {form_state["group_id"]}
    chosen = [g for g in groups if str(g.id) in ids]
    return chosen, ", ".join(g.name for g in chosen)


def annotate_preview_flags(questions):
    """Önizləmə partialı üçün hər suala has_error/has_warning bayraqları qoyur."""
    for question in questions or []:
        severities = {(w.get("severity") or "warning") for w in (question.get("warnings") or [])}
        question["has_error"] = "error" in severities
        question["has_warning"] = bool(severities - {"error"})
        question["has_visual_source"] = isinstance(question.get("source_index"), int)
    return questions


def _preview_context(raw_text):
    """Preview üçün parse nəticəsi + say xülasəsi (müəllim və mərkəz eyni şeyi görür)."""
    parsed, counts = analyze_submission_text(raw_text)
    return {"preview_parsed": annotate_preview_flags(parsed), "preview_counts": counts}


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

    raw_text = ""
    math_token = (request.POST.get("math_token") or "").strip()
    parsed = []
    selected = set()
    from apps.exams.views.teacher.question_library._shared import _empty_analysis

    analysis = _empty_analysis()
    form_state = {
        "title": "",
        "subject": "",
        "group_ids": [],
        "group_id": "",
        "group_label": "",
        "teacher_note": "",
        "language_raw": "",  # default seçim YOX — dil məcburi şüurlu seçilməlidir
        "language": "",
        "raw_text": "",
    }

    if request.method == "POST":
        action = (request.POST.get("action") or "preview").strip()
        form_state = _form_state(request)

        if action in ("preview", "save"):
            raw_text = form_state["raw_text"]
            uploaded = request.FILES.get("upload_file")
            upload_failed = False
            if uploaded:
                try:
                    raw_text, math_token = prepare_question_upload(
                        uploaded,
                        previous_token=math_token,
                        owner_id=request.user.pk,
                        organization_id=organization.pk,
                    )
                    form_state["raw_text"] = raw_text
                except Exception as exc:  # noqa: BLE001
                    upload_failed = True
                    messages.error(
                        request,
                        pgettext("exams.view.question_submission.message", "Fayl oxunmadı: {error}").format(error=exc),
                    )

            analysis = analyze_mcq_bulk(raw_text)
            parsed = analysis["parsed"]
            if math_token:
                from apps.exams.services.import_media import bind_import_manifest

                try:
                    bind_import_manifest(
                        math_token,
                        parsed,
                        owner_id=request.user.pk,
                        organization_id=organization.pk,
                    )
                except (OSError, ValueError) as exc:
                    messages.error(request, str(exc))
                    action = "preview"
            if upload_failed:
                action = "preview"

            selected_from_request = parse_selected_indices(request.POST)
            selected = set(range(1, len(parsed) + 1)) if selected_from_request is None else selected_from_request

            if action == "save":
                points_payload = parse_points_payload(request.POST)
                chosen = []
                for index, question in enumerate(parsed, start=1):
                    if index not in selected:
                        continue
                    raw_points = str(points_payload.get(str(index)) or "").strip()
                    if raw_points.isdigit() and int(raw_points) > 0:
                        question["points"] = int(raw_points)
                    chosen.append(question)

                chosen_groups, group_label = _resolve_groups(form_state, groups)
                subject_names = {s.name for s in _teacher_subjects(request, organization, groups=groups)}
                _err = None
                if not form_state["language_raw"]:
                    _err = pgettext("exams.view.question_submission.error", "İmtahan dilini seçin (məcburidir).")
                elif not form_state["subject"]:
                    _err = pgettext("exams.view.question_submission.error", "Fənni seçin (məcburidir).")
                elif subject_names and form_state["subject"] not in subject_names:
                    _err = pgettext(
                        "exams.view.question_submission.error", "Seçilmiş fənn sizin fənləriniz arasında deyil."
                    )
                elif not chosen_groups:
                    _err = pgettext("exams.view.question_submission.error", "Ən azı bir qrup seçin (məcburidir).")

                if _err:
                    messages.error(request, _err)
                else:
                    try:
                        submission = submit_question_set(
                            teacher=request.user,
                            organization=organization,
                            title=form_state["title"],
                            subject=form_state["subject"],
                            student_group=chosen_groups[0],
                            group_label=group_label,
                            language=form_state["language"],
                            raw_text=raw_text,
                            parsed=chosen,
                            teacher_note=form_state["teacher_note"],
                            import_token=math_token,
                        )
                        submission.student_groups.set(chosen_groups)
                    except ValidationError as exc:
                        messages.error(request, exc.messages[0])
                    else:
                        messages.success(
                            request,
                            pgettext(
                                "exams.view.question_submission.message",
                                "Göndəriş imtahan mərkəzinə çatdırıldı ({count} sual, {groups} qrup).",
                            ).format(count=submission.question_count, groups=len(chosen_groups)),
                        )
                        return redirect("exams:question_submission_detail", submission_id=submission.id)

    context = {
        "exam": None,
        # Profil örtüyü: sidebar solda qalsın, workbench sağda göstərilsin.
        "embed_active_section": "question-submissions",
        "raw_text": raw_text,
        "parsed": parsed,
        "selected": selected,
        "category_counts": analysis["category_counts"],
        "warning_count": analysis["warning_count"],
        "duplicate_count": analysis["duplicate_count"],
        "error_count": analysis["error_count"],
        "test_level_warnings": analysis["test_level_warnings"],
        "rq_value": "",
        "dp_value": "1",
        "math_token": math_token,
        # Meta sahələri (workbench-dən kənar kart)
        "teacher_groups": groups,
        "teacher_group_subjects": {
            str(group.id): [
                {"value": subject.name, "label": f"{subject.code} — {subject.name}"} for subject in group.subjects.all()
            ]
            for group in groups
        },
        # Fənn müəllimin ÖZ fənlərindən (qrupdan asılı deyil); qrup çox-seçimli.
        "teacher_subjects": [
            {"value": s.name, "label": f"{s.code} — {s.name}"}
            for s in _teacher_subjects(request, organization, groups=groups)
        ],
        "submission_languages": EXAM_LANGUAGE_CHOICES,
        "form_state": form_state,
        # Workbench konteksti
        "wb_workbench_key": "question-submission",
        "wb_title": pgettext("exams.template.question_submission", "İmtahan mərkəzinə sual göndər"),
        "wb_subtitle": pgettext(
            "exams.template.question_submission",
            "Sualları yazın və ya fayl yükləyin, önizləyin — xəbərdarlıqları görün, sonra göndərin.",
        ),
        "wb_back_url": _profile_section_url("question-submissions"),
        "wb_back_label": pgettext("exams.template.question_submission", "Göndərişlərə qayıt"),
        "wb_show_settings": False,
        "wb_ai_url": reverse("exams:ai_generate_submission_questions"),
        "wb_ai_context": "test",
        # Dil workbench-də YOX — göndəriş meta kartında məcburi select kimidir.
        "wb_show_language": False,
        "wb_languages": EXAM_LANGUAGE_CHOICES,
        "wb_selected_language": form_state["language"],
        "wb_show_format": False,
        "wb_format": "test",
        "wb_show_report": False,
        "wb_templates": [],
        "wb_save_label": pgettext("exams.template.question_submission", "İmtahan mərkəzinə göndər"),
    }
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

    is_reviewer = is_exam_center_user(request.user)
    if submission.teacher_id != request.user.id and not is_reviewer:
        raise Http404()

    can_edit = submission.teacher_id == request.user.id and submission.can_be_edited_by_teacher

    if request.method == "POST":
        if not can_edit:
            raise PermissionDenied(
                pgettext("exams.view.question_submission.permission", "Bu göndəriş dəyişdirilə bilməz.")
            )
        action = (request.POST.get("action") or "").strip()
        form_state = _form_state(request)

        _groups = list(_teacher_groups(request, organization))
        if action == "preview":
            context = _detail_context(submission, can_edit=can_edit, is_reviewer=is_reviewer)
            context["teacher_groups"] = _groups
            context["teacher_subjects"] = [
                {"value": s.name, "label": f"{s.code} — {s.name}"}
                for s in _teacher_subjects(request, organization, groups=_groups)
            ]
            context["submission_languages"] = EXAM_LANGUAGE_CHOICES
            context["form_state"] = form_state
            try:
                context.update(_preview_context(form_state["raw_text"]))
            except ValidationError as exc:
                messages.error(request, exc.messages[0])
            return render(request, "exams/teacher/question_submission_detail.html", context)

        if action == "resubmit":
            chosen_groups, group_label = _resolve_groups(form_state, _groups)
            subject_names = {s.name for s in _teacher_subjects(request, organization, groups=_groups)}
            _err = None
            if not form_state["language_raw"]:
                _err = pgettext("exams.view.question_submission.error", "İmtahan dilini seçin (məcburidir).")
            elif not form_state["subject"]:
                _err = pgettext("exams.view.question_submission.error", "Fənni seçin (məcburidir).")
            elif subject_names and form_state["subject"] not in subject_names:
                _err = pgettext(
                    "exams.view.question_submission.error", "Seçilmiş fənn sizin fənləriniz arasında deyil."
                )
            elif not chosen_groups:
                _err = pgettext("exams.view.question_submission.error", "Ən azı bir qrup seçin (məcburidir).")
            if _err:
                messages.error(request, _err)
                return redirect("exams:question_submission_detail", submission_id=submission.id)
            try:
                submission = resubmit_question_set(
                    submission,
                    title=form_state["title"],
                    subject=form_state["subject"],
                    student_group=chosen_groups[0],
                    group_label=group_label,
                    language=form_state["language"],
                    raw_text=form_state["raw_text"],
                    teacher_note=form_state["teacher_note"],
                )
                submission.student_groups.set(chosen_groups)
            except ValidationError as exc:
                messages.error(request, exc.messages[0])
            else:
                messages.success(
                    request,
                    pgettext(
                        "exams.view.question_submission.message",
                        "Göndəriş yeniləndi və imtahan mərkəzinə təkrar çatdırıldı.",
                    ),
                )
            return redirect("exams:question_submission_detail", submission_id=submission.id)

    context = _detail_context(submission, can_edit=can_edit, is_reviewer=is_reviewer)
    if can_edit:
        _groups = list(_teacher_groups(request, organization))
        context["teacher_groups"] = _groups
        context["teacher_subjects"] = [
            {"value": s.name, "label": f"{s.code} — {s.name}"}
            for s in _teacher_subjects(request, organization, groups=_groups)
        ]
        context["submission_languages"] = EXAM_LANGUAGE_CHOICES
    return render(request, "exams/teacher/question_submission_detail.html", context)


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
        "submission": submission,
        "parsed_questions": annotate_preview_flags(list(submission.parsed_snapshot or [])),
        "can_edit": can_edit,
        "is_reviewer": is_reviewer,
        "language_choices": EXAM_LANGUAGE_CHOICES,
        "form_state": {
            "title": submission.title,
            "subject": submission.subject,
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


# ---------------------------------------------------------------------------
# İmtahan mərkəzi: baxış (köhnə "qutu" səhifəsi profil bölməsinə köçüb)
# ---------------------------------------------------------------------------
@login_required
def question_submission_inbox(request):
    """Köhnə ayrıca qutu (inbox) səhifəsi ləğv edilib — göndərişlər indi profil
    bölməsində inline filtrlənir (axtarış + fakültə/kafedra/müəllim/dövr/dil).
    Route köhnə bookmark/linklər üçün yönləndirmə kimi saxlanılır."""
    return redirect(_profile_section_url("question-submissions"))


@login_required
def question_submission_review(request, submission_id):
    _ensure_teacher(request.user)
    organization = _require_organization(request)
    submission = get_object_or_404(
        QuestionSubmission.objects.select_related("teacher", "accepted_bank"),
        id=submission_id,
        organization=organization,
    )
    ensure_can_review_submission(request.user, submission)

    banks = QuestionBank.objects.filter(organization=organization, default_question_type="test").order_by("-created_at")

    return render(
        request,
        "exams/teacher/question_submission_review.html",
        {
            "submission": submission,
            "parsed_questions": annotate_preview_flags(list(submission.parsed_snapshot or [])),
            "banks": banks,
            "back_url": _profile_section_url("question-submissions"),
        },
    )


@login_required
@require_POST
def question_submission_decide(request, submission_id):
    _ensure_teacher(request.user)
    organization = _require_organization(request)
    submission = get_object_or_404(QuestionSubmission, id=submission_id, organization=organization)
    ensure_can_review_submission(request.user, submission)

    decision = (request.POST.get("decision") or "").strip()
    note = (request.POST.get("note") or "").strip()

    try:
        if decision == "accept":
            bank = None
            bank_id = (request.POST.get("bank_id") or "").strip()
            if bank_id:
                bank = get_object_or_404(QuestionBank, id=bank_id, organization=organization)
            bank, created_count = accept_submission(
                submission,
                reviewer=request.user,
                bank=bank,
                new_bank_name=request.POST.get("new_bank_name") or "",
                note=note,
            )
            messages.success(
                request,
                pgettext(
                    "exams.view.question_submission.message",
                    'Göndəriş qəbul edildi — {count} sual "{bank}" bankına əlavə olundu.',
                ).format(count=created_count, bank=bank.name),
            )
        elif decision == "reject":
            if not note:
                messages.error(
                    request,
                    pgettext(
                        "exams.view.question_submission.message",
                        "Rədd üçün müəllimə qeyd yazın — nəyi düzəltməlidir.",
                    ),
                )
                return redirect("exams:question_submission_review", submission_id=submission.id)
            reject_submission(submission, reviewer=request.user, note=note)
            messages.success(
                request,
                pgettext("exams.view.question_submission.message", "Göndəriş rədd edildi və müəllimə bildirildi."),
            )
        else:
            messages.error(request, pgettext("exams.view.question_submission.message", "Yanlış əməliyyat."))
            return redirect("exams:question_submission_review", submission_id=submission.id)
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
        return redirect("exams:question_submission_review", submission_id=submission.id)

    return redirect(_profile_section_url("question-submissions"))


__all__ = [
    "ai_generate_submission_questions",
    "question_submission_create",
    "question_submission_decide",
    "question_submission_detail",
    "question_submission_inbox",
    "question_submission_review",
]
