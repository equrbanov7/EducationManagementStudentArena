"""Göndəriş workbench-inin ORTAQ emalı və konteksti.

Eyni workbench UI-ı (fayl yüklə, redaktor, AI, önizləmə kartları, seçim) iki
yerdə işləyir: yeni göndəriş (``question_submission_create``) və mövcud
göndərişin redaktəsi/yenidən göndərilməsi (``question_submission_detail``,
can_edit). Upload + parse + vizual manifest bağlama + seçim oxunuşu və wb_*
kontekst açarları burada mərkəzləşir ki, iki view eyni davranışı bölüşsün.
"""

from django.contrib import messages
from django.urls import reverse
from django.utils.translation import pgettext

from apps.exams.constants import EXAM_LANGUAGE_CHOICES, QUESTION_EXAM_KIND_CHOICES
from apps.exams.services.bulk_workbench import (
    analyze_mcq_bulk,
    parse_points_payload,
    parse_selected_indices,
)
from apps.exams.services.visual_import_upload import prepare_question_upload
from apps.exams.views.teacher.submission_meta import _teacher_subjects


def process_workbench_post(request, organization, form_state):
    """POST (preview|save) emalı: fayl yükləmə, analiz, manifest, seçim.

    Qaytarır dict:
      action (yükləmə/manifest xətasında "preview"-a endirilir), raw_text,
      math_token, analysis, parsed, selected, chosen (yalnız save üçün —
      seçilmiş suallar, ballar tətbiq olunmuş halda).
    """
    action = (request.POST.get("action") or "preview").strip()
    math_token = (request.POST.get("math_token") or "").strip()
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

    chosen = []
    if action == "save":
        points_payload = parse_points_payload(request.POST)
        for index, question in enumerate(parsed, start=1):
            if index not in selected:
                continue
            raw_points = str(points_payload.get(str(index)) or "").strip()
            if raw_points.isdigit() and int(raw_points) > 0:
                question["points"] = int(raw_points)
            chosen.append(question)

    return {
        "action": action,
        "raw_text": raw_text,
        "math_token": math_token,
        "analysis": analysis,
        "parsed": parsed,
        "selected": selected,
        "chosen": chosen,
    }


def initial_workbench_state(request, organization, *, raw_text, math_token):
    """GET (detal redaktəsi) üçün mövcud mətnin analizi.

    Vizual göndərişdə manifest yenidən bağlanır ki, kartlarda şəkil preview-ları
    görünsün; bağlana bilmirsə (stash silinib/uyğunsuzdur) vizuallar səssizcə
    söndürülür — mətn redaktəsi yenə işləyir.
    """
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
        except (OSError, ValueError):
            math_token = ""
    return {
        "analysis": analysis,
        "parsed": parsed,
        "selected": set(range(1, len(parsed) + 1)),
        "math_token": math_token,
        "raw_text": raw_text,
    }


def build_workbench_context(
    request,
    organization,
    groups,
    form_state,
    *,
    analysis,
    parsed,
    selected,
    raw_text,
    math_token,
    title,
    subtitle,
    save_label,
):
    """Workbench + göndəriş meta kartı üçün ortaq template konteksti."""
    return {
        "exam": None,
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
        # Meta sahələri (workbench-dən kənar kart). Fənn dəyərləri Subject pk-dır.
        "teacher_groups": groups,
        "teacher_group_subjects": {
            str(group.id): [
                {"value": str(subject.pk), "label": f"{subject.code} — {subject.name}"}
                for subject in group.subjects.all()
            ]
            for group in groups
        },
        # Fənn müəllimin ÖZ fənlərindən (qrupdan asılı deyil); qrup çox-seçimli.
        "teacher_subjects": [
            {"value": str(s.pk), "label": f"{s.code} — {s.name}"}
            for s in _teacher_subjects(request, organization, groups=groups)
        ],
        "submission_languages": EXAM_LANGUAGE_CHOICES,
        "submission_exam_kinds": QUESTION_EXAM_KIND_CHOICES,
        "form_state": form_state,
        # Workbench konteksti
        "wb_workbench_key": "question-submission",
        "wb_title": title,
        "wb_subtitle": subtitle,
        "wb_back_url": f"{reverse('accounts:profile')}?section=question-submissions",
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
        "wb_save_label": save_label,
    }


__all__ = ["build_workbench_context", "initial_workbench_state", "process_workbench_post"]
