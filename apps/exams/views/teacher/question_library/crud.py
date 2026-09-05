"""question_library paketi — crud."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.db.models.functions import Lower
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme, urlencode
from django.utils.translation import pgettext

from apps.exams.constants import (
    DEFAULT_EXAM_LANGUAGE,
    EXAM_LANGUAGE_CHOICES,
    QUESTION_EXAM_KIND_VALUES,
)
from apps.exams.models import QuestionBank
from apps.exams.services.access_policy import _ensure_teacher, ensure_can_create_question_bank, is_exam_center_user
from apps.exams.services.bank_analysis import analyze_bank_questions
from apps.exams.services.question_bank_attach import accessible_banks
from core.audit import log_action
from core.constants import AuditAction
from core.tenancy import get_request_organization

from ._shared import (
    _ALLOWED_SORTS,
    _ALLOWED_STATUSES,
    _normalize_format,
)


def _resolve_bank_subject(organization, raw_subject_id):
    """Axtarışlı seçicidən gələn fənn id-sini təşkilat daxilində həll edir.

    Qaytarır: (subject_ref, subject_text). Tapılmasa (None, "").
    Xüsusi hal: "text:<ad>" — köhnə sərbəst-mətn fənni olan bankın redaktəsində
    seçim dəyişdirilməyibsə mətn olduğu kimi saxlanır (kataloq bağlantısı yox).
    """
    raw_subject_id = (raw_subject_id or "").strip()
    if not raw_subject_id or organization is None:
        return None, ""
    if raw_subject_id.startswith("text:"):
        return None, raw_subject_id[len("text:") :].strip()[:100]
    from apps.registrar.models import Subject

    try:
        subject = Subject.objects.filter(organization=organization, pk=raw_subject_id).first()
    except (ValueError, ValidationError):
        subject = None
    if subject is None:
        return None, ""
    return subject, subject.name


def _resolve_bank_teacher(organization, raw_teacher_id):
    """ "Sualı göndərən müəllim" seçimini təşkilatın müəllim üzvləri içində həll edir."""
    raw_teacher_id = (raw_teacher_id or "").strip()
    if not raw_teacher_id.isdigit() or organization is None:
        return None
    from django.contrib.auth import get_user_model

    from apps.organizations.public import organization_role_user_queryset
    from core.roles import ProfileRole

    return (
        organization_role_user_queryset(
            organization,
            {ProfileRole.TEACHER, ProfileRole.ASSISTANT_TEACHER},
            queryset=get_user_model().objects.filter(is_active=True),
        )
        .filter(pk=int(raw_teacher_id))
        .first()
    )


def _normalize_exam_kind(raw_value, user=None):
    """Bank təyinatını yoxlayır. İmtahan mərkəzi olmayan istifadəçi (müəllim)
    üçün nəticə HƏMİŞƏ «quiz»-dir — şəxsi bank final/midterm ola bilməz
    (UI yalnız quiz göstərir; bu, birbaşa POST-a qarşı server müdafiəsidir)."""
    if user is not None and not is_exam_center_user(user):
        return "quiz"
    value = (raw_value or "").strip().lower()
    return value if value in QUESTION_EXAM_KIND_VALUES else ""


@login_required
def question_bank_list(request):
    _ensure_teacher(request.user)
    organization = get_request_organization(request)
    profile_bank_url = f"{reverse('accounts:profile')}?section=question-bank"

    if request.method == "POST" and (request.POST.get("action") == "create_bank"):
        # İmtahan mərkəzi tam səlahiyyətli; müəllim yalnız ÖZÜ üçün Quiz bankı
        # yarada bilər (_normalize_exam_kind «quiz»-ə bağlayır, mənbə müəllim özüdür).
        ensure_can_create_question_bank(request.user)
        creator_is_center = is_exam_center_user(request.user)
        name = (request.POST.get("name") or "").strip()
        name_max = QuestionBank._meta.get_field("name").max_length or 255
        if not name:
            messages.error(request, pgettext("exams.view.bank.message", "Bank adı boş ola bilməz."))
        elif len(name) > name_max:
            # 255+ simvol DB DataError (500) verirdi (QA 2026-09-05 EXAMS-01).
            messages.error(
                request,
                pgettext("exams.view.bank.message", "Bank adı ən çox %(n)s simvol ola bilər.") % {"n": name_max},
            )
        else:
            subject_ref, subject_text = _resolve_bank_subject(organization, request.POST.get("subject_id"))
            QuestionBank.objects.create(
                name=name,
                subject=subject_text,
                subject_ref=subject_ref,
                exam_kind=_normalize_exam_kind(request.POST.get("exam_kind"), user=request.user),
                source_teacher=(
                    _resolve_bank_teacher(organization, request.POST.get("source_teacher_id"))
                    if creator_is_center
                    else request.user
                ),
                description=(request.POST.get("description") or "").strip(),
                language=(request.POST.get("language") or DEFAULT_EXAM_LANGUAGE).strip().lower(),
                default_question_type=_normalize_format(request.POST.get("default_question_type")),
                organization=organization,
                created_by=request.user,
                # Banklar default olaraq GİZLİDİR — "Təşkilatda paylaş" UI-dan çıxarılıb.
                is_shared=False,
            )
            messages.success(request, pgettext("exams.view.bank.message", "Sual bankı yaradıldı."))
        next_url = (request.POST.get("next") or "").strip()
        if next_url and url_has_allowed_host_and_scheme(
            next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        ):
            return redirect(next_url)
        return redirect(profile_bank_url)

    return redirect(profile_bank_url)


@login_required
def question_bank_update(request, bank_id):
    """Bankın adını/fənnini/təyinatını/dilini/formatını redaktə et (yalnız sahib).

    `is_shared` UI-dan çıxarılıb — redaktə mövcud paylaşım vəziyyətinə toxunmur.
    """
    _ensure_teacher(request.user)
    organization = get_request_organization(request)
    bank = get_object_or_404(accessible_banks(request.user, organization), id=bank_id)
    if bank.created_by_id != request.user.id:
        messages.error(request, pgettext("exams.view.bank.message", "Yalnız bankın sahibi redaktə edə bilər."))
        return redirect("exams:question_bank_detail", bank_id=bank.id)

    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        if not name:
            messages.error(request, pgettext("exams.view.bank.message", "Bank adı boş ola bilməz."))
        else:
            bank.name = name
            subject_ref, subject_text = _resolve_bank_subject(organization, request.POST.get("subject_id"))
            bank.subject_ref = subject_ref
            bank.subject = subject_text
            bank.exam_kind = _normalize_exam_kind(request.POST.get("exam_kind"), user=request.user)
            # source_teacher yalnız imtahan mərkəzi tərəfindən dəyişdirilə bilər:
            # müəllim formasında sahə yoxdur (boş POST mövcud dəyəri silərdi) və
            # müəllim başqasının adına atribusiya saxtalaşdıra bilməməlidir.
            if is_exam_center_user(request.user):
                bank.source_teacher = _resolve_bank_teacher(organization, request.POST.get("source_teacher_id"))
            bank.language = (request.POST.get("language") or bank.language).strip().lower()
            bank.default_question_type = _normalize_format(
                request.POST.get("default_question_type") or bank.default_question_type
            )
            bank.save(
                update_fields=[
                    "name",
                    "subject",
                    "subject_ref",
                    "exam_kind",
                    "source_teacher",
                    "language",
                    "default_question_type",
                    "updated_at",
                ]
            )
            messages.success(request, pgettext("exams.view.bank.message", "Bank yeniləndi."))
        next_url = (request.POST.get("next") or "").strip()
        if next_url and url_has_allowed_host_and_scheme(
            next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        ):
            return redirect(next_url)
    return redirect("exams:question_bank_detail", bank_id=bank.id)


@login_required
def question_bank_delete(request, bank_id):
    """Bütün bankı sil (yalnız sahib)."""
    _ensure_teacher(request.user)
    organization = get_request_organization(request)
    bank = get_object_or_404(accessible_banks(request.user, organization), id=bank_id)
    if bank.created_by_id != request.user.id:
        messages.error(request, pgettext("exams.view.bank.message", "Yalnız bankın sahibi silə bilər."))
        return redirect("exams:question_bank_detail", bank_id=bank.id)
    if request.method == "POST":
        bank.delete()
        messages.success(request, pgettext("exams.view.bank.message", "Sual bankı silindi."))
        next_url = (request.POST.get("next") or "").strip()
        if next_url and url_has_allowed_host_and_scheme(
            next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        ):
            return redirect(next_url)
        return redirect(f"{reverse('accounts:profile')}?section=question-bank")
    return redirect("exams:question_bank_detail", bank_id=bank.id)


def _can_mutate_bank(user, bank) -> bool:
    """Bankın MƏZMUNUNU dəyişməyə kimin haqqı var.

    2026-09-02 audit, P0-2: ``question_bank_detail`` POST budağı yalnız OXU
    görünürlüyünə (``accessible_banks``) söykənirdi.  Həmin köməkçi imtahan
    mərkəzi rollarına başqa müəllimin bankını GÖSTƏRİR — nəticədə
    ``bulk_action=delete`` ilə yad müəllimin sualları HARD-DELETE olunurdu
    (audit sətri də yazılmırdı).  Mutasiya artıq sahibliyə bağlıdır.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if bank.created_by_id == user.id:
        return True
    if getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False):
        return True
    organization = getattr(bank, "organization", None)
    return organization is not None and getattr(organization, "owner_id", None) == user.id


def _ensure_bank_mutation_allowed(request, bank, action: str):
    """Sahib deyilsə: rədd et + audit yaz (səssiz keçid YOXDUR)."""
    if _can_mutate_bank(request.user, bank):
        return
    log_action(
        AuditAction.DENY,
        user=request.user,
        organization=getattr(bank, "organization", None),
        obj=bank,
        reason=f"question bank mutation refused (not owner): bulk_action={action or '-'}",
        request=request,
        resource_type="exams.QuestionBank",
        resource_id=str(bank.pk),
        resource_repr=bank.name[:500],
    )
    raise PermissionDenied(pgettext("exams.view.bank.message", "Yalnız bankın sahibi bu əməliyyatı edə bilər."))


@login_required
def question_bank_detail(request, bank_id):
    _ensure_teacher(request.user)
    organization = get_request_organization(request)
    bank = get_object_or_404(accessible_banks(request.user, organization), id=bank_id)

    # ---- POST: toplu/tək aktiv-deaktiv-sil ----
    if request.method == "POST":
        action = (request.POST.get("bulk_action") or "").strip().lower()
        # HƏR mutasiya budağı üçün eyni qapı — oxu görünürlüyü kifayət etmir.
        _ensure_bank_mutation_allowed(request, bank, action)

        # Dil üzrə bütün sualları sil (yalnız bank sahibi)
        if action == "delete_language":
            lang = (request.POST.get("language") or "").strip().lower()
            qs = bank.library_questions.all()
            if lang:
                qs = qs.filter(language=lang)
            deleted = qs.count()
            qs.delete()
            log_action(
                AuditAction.DELETE,
                user=request.user,
                organization=getattr(bank, "organization", None),
                obj=bank,
                reason=f"question bank bulk delete_language: language={lang or 'all'}, count={deleted}",
                request=request,
                resource_type="exams.QuestionBank",
                resource_id=str(bank.pk),
                resource_repr=bank.name[:500],
            )
            messages.success(
                request, pgettext("exams.view.bank.message", "{count} sual silindi.").format(count=deleted)
            )
            redirect_params = {}
            keep_lang = (request.POST.get("language") or "").strip()
            if keep_lang:
                redirect_params["language"] = keep_lang
            redirect_url = reverse("exams:question_bank_detail", kwargs={"bank_id": bank.id})
            if redirect_params:
                redirect_url = f"{redirect_url}?{urlencode(redirect_params)}"
            return redirect(redirect_url)

        selected_ids = [int(item) for item in request.POST.getlist("selected_question_ids") if item.isdigit()]
        selected_qs = bank.library_questions.filter(id__in=selected_ids)
        count = selected_qs.count()

        if count == 0:
            messages.warning(request, pgettext("exams.view.bank.message", "Ən azı bir sual seçin."))
        elif action == "deactivate":
            updated = selected_qs.update(is_active=False)
            messages.success(
                request, pgettext("exams.view.bank.message", "{count} sual deaktiv edildi.").format(count=updated)
            )
        elif action == "activate":
            updated = selected_qs.update(is_active=True)
            messages.success(
                request, pgettext("exams.view.bank.message", "{count} sual aktiv edildi.").format(count=updated)
            )
        elif action == "delete":
            deleted_ids = sorted(selected_qs.values_list("id", flat=True))
            selected_qs.delete()
            log_action(
                AuditAction.DELETE,
                user=request.user,
                organization=getattr(bank, "organization", None),
                obj=bank,
                changes={"deleted_question_ids": deleted_ids},
                reason=f"question bank bulk delete: count={count}",
                request=request,
                resource_type="exams.QuestionBank",
                resource_id=str(bank.pk),
                resource_repr=bank.name[:500],
            )
            messages.success(request, pgettext("exams.view.bank.message", "{count} sual silindi.").format(count=count))
        else:
            messages.error(request, pgettext("exams.view.bank.message", "Yanlış əməliyyat."))

        redirect_params = {}
        for key in ("q", "status", "sort", "language", "flag", "page"):
            value = (request.POST.get(key) or "").strip()
            if value:
                redirect_params[key] = value
        url = reverse("exams:question_bank_detail", kwargs={"bank_id": bank.id})
        if redirect_params:
            url = f"{url}?{urlencode(redirect_params)}"
        return redirect(url)

    # ---- GET: filtr + siyahı ----
    allowed_flags = {"has-error", "has-warning", "has-dup", "has-structure", "has-balance", "is-clean"}
    search_query = (request.GET.get("q") or "").strip()[:120]
    status_filter = (request.GET.get("status") or "all").strip().lower()
    sort_filter = (request.GET.get("sort") or "newest").strip().lower()
    language_filter = (request.GET.get("language") or "").strip().lower()
    flag_filter = (request.GET.get("flag") or "").strip().lower()
    if status_filter not in _ALLOWED_STATUSES:
        status_filter = "all"
    if sort_filter not in _ALLOWED_SORTS:
        sort_filter = "newest"
    if flag_filter not in allowed_flags:
        flag_filter = ""

    # Keyfiyyət analizi — seçilmiş dil üzrə (dublikat/xəbərdarlıq/struktur/balans).
    analysis = analyze_bank_questions(bank, language=language_filter or None)
    analysis_enabled = analysis.total_analyzed > 0
    active_flag = flag_filter if (flag_filter and analysis_enabled) else ""

    # Excel keyfiyyət hesabatı (test bankı view-dakı builder təkrar istifadə olunur).
    if analysis_enabled and request.GET.get("export") == "report":
        from types import SimpleNamespace

        from apps.exams.views.teacher.question_bank import _build_question_bank_report_xlsx

        try:
            return _build_question_bank_report_xlsx(
                exam=SimpleNamespace(title=bank.name),
                raw_text="",
                parsed=analysis.parsed_for_report,
                test_level_warnings=[],
                category_counts=analysis.category_counts,
                warning_count=analysis.warning_count,
                duplicate_count=analysis.duplicate_count,
                error_count=analysis.error_count,
            )
        except RuntimeError as exc:
            messages.error(request, str(exc))

    questions = bank.library_questions.prefetch_related("options")
    if search_query:
        matched_ids = (
            bank.library_questions.filter(Q(text__icontains=search_query) | Q(options__text__icontains=search_query))
            .values_list("id", flat=True)
            .distinct()
        )
        questions = questions.filter(id__in=matched_ids)
    if status_filter == "active":
        questions = questions.filter(is_active=True)
    elif status_filter == "inactive":
        questions = questions.filter(is_active=False)
    if language_filter:
        questions = questions.filter(language=language_filter)
    if active_flag:
        questions = questions.filter(id__in=analysis.flagged_ids.get(active_flag, set()))

    if sort_filter == "oldest":
        questions = questions.order_by("created_at", "id")
    elif sort_filter == "az":
        questions = questions.order_by(Lower("text"), "id")
    elif sort_filter == "za":
        questions = questions.order_by(Lower("text").desc(), "id")
    else:
        questions = questions.order_by("-created_at", "-id")

    paginator = Paginator(questions, 12)
    page_obj = paginator.get_page(request.GET.get("page"))

    # Cari səhifədəki suallara analiz nəticəsini bağla (badge/warning üçün)
    if analysis_enabled:
        for question in page_obj.object_list:
            entry = analysis.analysis_by_id.get(question.id)
            question.analysis_meta = entry["meta"] if entry else None
            question.analysis_warnings = entry["warnings"] if entry else []

    # Statistika seçilmiş dilə görə dəyişir
    scoped = bank.library_questions.all()
    if language_filter:
        scoped = scoped.filter(language=language_filter)
    total_questions = scoped.count()
    active_questions = scoped.filter(is_active=True).count()
    inactive_questions = max(total_questions - active_questions, 0)

    base_params = {}
    if search_query:
        base_params["q"] = search_query
    if status_filter != "all":
        base_params["status"] = status_filter
    if sort_filter != "newest":
        base_params["sort"] = sort_filter
    if language_filter:
        base_params["language"] = language_filter
    if active_flag:
        base_params["flag"] = active_flag
    filters_params = {key: value for key, value in base_params.items() if key != "flag"}
    profile_bank_url = f"{reverse('accounts:profile')}?section=question-bank"

    context = {
        "exam": None,
        "bank": bank,
        "page_obj": page_obj,
        "search_query": search_query,
        "status_filter": status_filter,
        "sort_filter": sort_filter,
        "language_filter": language_filter,
        "active_flag": active_flag,
        "total_questions": total_questions,
        "active_questions": active_questions,
        "inactive_questions": inactive_questions,
        "pagination_query": urlencode(base_params),
        "filters_query": urlencode(filters_params),
        "analysis_enabled": analysis_enabled,
        "category_counts": analysis.category_counts,
        "error_count": analysis.error_count,
        "warning_count": analysis.warning_count,
        "duplicate_count": analysis.duplicate_count,
        "clean_count": analysis.clean_count,
        "analyzed_total": analysis.total_analyzed,
        "qm_show_report": True,
        "language_choices": EXAM_LANGUAGE_CHOICES,
        "navigation_from_section": "",
        "navigation_return_to": "",
        # Ortaq idarəetmə partial konteksti
        "qm_context": "bank",
        "qm_title": bank.name,
        "qm_subtitle": pgettext(
            "exams.template.question_bank_detail",
            "Bankın suallarını idarə et: axtar, redaktə et, aktiv/deaktiv et, sil.",
        ),
        "qm_base_url": reverse("exams:question_bank_detail", kwargs={"bank_id": bank.id}),
        "qm_back_url": profile_bank_url,
        "qm_back_label": pgettext("exams.template.question_bank_detail", "Banklar"),
        "qm_bulk_add_url": reverse("exams:question_bank_bulk_add", kwargs={"bank_id": bank.id}),
        "qm_bulk_add_label": pgettext("exams.template.question_bank_detail", "Toplu sual əlavə et"),
        "qm_add_single_url": reverse("exams:bank_question_add", kwargs={"bank_id": bank.id}),
        "qm_show_language_filter": True,
        # Bank redaktə/sil (yalnız sahib)
        "qm_is_owner": bank.created_by_id == request.user.id,
        "qm_default_type_choices": QuestionBank.DEFAULT_QUESTION_TYPE_CHOICES,
        "qm_update_url": reverse("exams:question_bank_update", kwargs={"bank_id": bank.id}),
        "qm_delete_url": reverse("exams:question_bank_delete", kwargs={"bank_id": bank.id}),
        # Word export — bankın suallarını import-uyğun .docx kimi endir.
        "qm_word_export_url": reverse("exams:question_bank_word_export", kwargs={"bank_id": bank.id}),
    }
    return render(request, "exams/teacher/question_bank_detail.html", context)
