"""Sorğu qurucusu (2026-09-30) — sorğunun yaradılması, ayarları və həyat dövrü (atomik, auditli).

Qaydalar (nəticə bütövlüyü üçün):

* Növ yaradılanda seçilir; ``teacher_evaluation`` ilə digərləri arasında keçid YOXDUR (sual
  növləri və analitika fərqlidir). Ümumi növlər (ümumi / fənn rəyi / tədbir) bir-birinə
  cavab gəlməyənə qədər keçə bilər.
* Anonimlik, auditoriya və açılış tarixi dərcdən SONRA dəyişmir (bildiriş artıq gedib,
  anonimlik vədi verilib) — dəyişmək üçün dublikat yaradılır. Bağlanma tarixi, məcburilik,
  qapı siyasəti və möhlət istənilən vaxt dəyişə bilər (qapı xülasəsi yenilənir).
* k-həddi ilk nəticə dərcindən sonra dəyişmir (Audit 2026-09-28 SV-2 ruhu).
* Müəllim qiymətləndirməsi dəsti üçün «dərc» = kampaniyalarda istifadəyə hazır; «defolt» =
  yeni kampaniyalar bu dəsti götürür. Açıq kampaniyanın dəsti arxivlənmir.
"""

from __future__ import annotations

import datetime
import secrets

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import pgettext

from ..constants import (
    AUDIT_SURVEY_RESOURCE,
    DESCRIPTION_MAX_LENGTH,
    MAX_CAMPAIGN_DAYS,
    MAX_DEFER_DAYS,
    MIN_GROUP_SIZE_CEIL,
    MIN_GROUP_SIZE_FLOOR,
    TITLE_MAX_LENGTH,
    Audience,
    CampaignStatus,
    GatePolicy,
    SurveyKind,
    SurveyStatus,
)
from ..models import Survey, SurveyCampaign, SurveyPage, SurveyQuestion, SurveyTemplate
from .audience import normalize_filter
from .gate_snapshot import sync_gate_snapshot

_CTX = "surveys.builder"
GENERIC_SURVEY_KINDS = (SurveyKind.GENERAL, SurveyKind.COURSE_FEEDBACK, SurveyKind.EVENT)


class BuilderError(ValidationError):
    """İstifadəçiyə göstərilə bilən qurucu xətası."""


def audit(survey, *, by_user, action, changes=None, request=None):
    from core.audit import log_action
    from core.constants import AuditAction

    log_action(
        AuditAction.CREATE if action == "create" else AuditAction.UPDATE,
        user=by_user if getattr(by_user, "pk", None) else None,
        organization=survey.organization,
        obj=None,
        reason=f"survey_{action}",
        request=request,
        resource_type=AUDIT_SURVEY_RESOURCE,
        resource_id=str(survey.pk),
        resource_repr=f"{action} · {survey.title[:120]}",
        changes={"action": action, **{key: str(value) for key, value in (changes or {}).items()}},
    )


def has_answers(survey) -> bool:
    """Sorğuya cavab gəlibmi (struktur kilidi) — ümumi sorğu: iştirak; müəllim dəsti: kampaniya."""
    if survey.is_teacher_evaluation:
        return (
            SurveyCampaign.objects.filter(template_id=survey.template_id).exclude(status=CampaignStatus.DRAFT).exists()
        )
    return survey.participations.exists() or survey.pending_submissions.exists() or survey.submissions.exists()


def _locked(survey_id):
    return Survey.objects.select_for_update().select_related("organization", "template").get(pk=survey_id)


def _template_name(title) -> str:
    return f"{(title or '').strip()[:150]} · {secrets.token_hex(4)}"


def _clean_title(title) -> str:
    title = (title or "").strip()
    if not title:
        raise BuilderError(pgettext(_CTX, "Sorğunun adı boş ola bilməz."))
    if len(title) > TITLE_MAX_LENGTH:
        raise BuilderError(pgettext(_CTX, "Ad %(limit)s simvoldan uzun ola bilməz.") % {"limit": TITLE_MAX_LENGTH})
    return title


def _seed_teacher_questions(organization, template):
    from ..defaults import DEFAULT_QUESTIONS

    SurveyQuestion.objects.bulk_create(
        SurveyQuestion(
            organization=organization,
            template=template,
            code=code,
            section=section,
            kind=kind,
            text=text,
            help_text=help_text,
            required=required,
            in_index=in_index,
            order=(index + 1) * 10,
        )
        for index, (code, section, kind, text, help_text, required, in_index) in enumerate(DEFAULT_QUESTIONS)
    )


def create_survey(organization, *, kind, title, audience=Audience.STUDENTS, by_user=None, request=None) -> Survey:
    """Yeni QARALAMA sorğu (öz sual dəsti ilə). Müəllim dəsti defolt suallarla başlayır
    (auditoriyası həmişə tələbələrdir — kampaniya ilə)."""
    title = _clean_title(title)
    if kind not in SurveyKind.values:
        raise BuilderError(pgettext(_CTX, "Sorğu növü seçilməlidir."))
    if audience not in Audience.values:
        raise BuilderError(pgettext(_CTX, "Auditoriya seçilməlidir."))
    with transaction.atomic():
        template = SurveyTemplate.objects.create(
            organization=organization, name=_template_name(title), version=1, is_active=True, is_default=False
        )
        teacher = kind == SurveyKind.TEACHER_EVALUATION
        survey = Survey.objects.create(
            organization=organization,
            template=template,
            kind=kind,
            title=title,
            anonymous=True,
            audience=Audience.STUDENTS if teacher else audience,
            created_by=by_user if getattr(by_user, "pk", None) else None,
        )
        if teacher:
            _seed_teacher_questions(organization, template)
        else:
            SurveyPage.objects.create(organization=organization, template=template, order=10)
        audit(survey, by_user=by_user, action="create", changes={"kind": kind}, request=request)
    return survey


def _validate_dates(opens_on, closes_on):
    if opens_on and closes_on:
        if closes_on < opens_on:
            raise BuilderError(pgettext(_CTX, "Bağlanma tarixi açılış tarixindən əvvəl ola bilməz."))
        if (closes_on - opens_on).days > MAX_CAMPAIGN_DAYS:
            raise BuilderError(pgettext(_CTX, "Sorğu %(days)s gündən uzun ola bilməz.") % {"days": MAX_CAMPAIGN_DAYS})


def _bounded(value, low, high, message):
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise BuilderError(message) from exc
    if not low <= number <= high:
        raise BuilderError(message)
    return number


def update_settings(survey, values: dict, *, by_user=None, request=None) -> Survey:
    """``values`` — yalnız DƏYİŞƏN sahələr (``views.builder`` təmizləyir). Kilid qaydaları modul sənədindədir."""
    with transaction.atomic():
        survey = _locked(survey.pk)
        teacher = survey.is_teacher_evaluation
        answered = has_answers(survey)
        draft = survey.status == SurveyStatus.DRAFT
        new = {}
        if "title" in values:
            new["title"] = _clean_title(values["title"])
        if "description" in values:
            description = (values["description"] or "").strip()
            if len(description) > DESCRIPTION_MAX_LENGTH:
                raise BuilderError(
                    pgettext(_CTX, "Təsvir %(limit)s simvoldan uzun ola bilməz.") % {"limit": DESCRIPTION_MAX_LENGTH}
                )
            new["description"] = description
        if not teacher:
            new.update(_generic_values(survey, values, draft=draft, answered=answered))
        changes = {key: value for key, value in new.items() if getattr(survey, key) != value}
        if not changes:
            return survey
        _validate_dates(changes.get("opens_on", survey.opens_on), changes.get("closes_on", survey.closes_on))
        for key, value in changes.items():
            setattr(survey, key, value)
        survey.save(update_fields=[*changes, "updated_at"])
        if teacher and "title" in changes:
            SurveyTemplate.objects.filter(pk=survey.template_id).update(name=_template_name(survey.title))
        if survey.status == SurveyStatus.PUBLISHED:
            if survey.anonymous and survey.effective_status(timezone.localdate()) == SurveyStatus.CLOSED:
                from .survey_buffer import publish_results

                publish_results(survey.pk)  # bağlanma keçmişə çəkildi — nəticə indi dondurulur
            sync_gate_snapshot(survey.organization)
            from .survey_notify import notify_if_due

            notify_if_due(survey)  # açılış bu günə çəkilibsə — bildiriş (bir dəfə)
        audit(survey, by_user=by_user, action="update", changes=changes, request=request)
    return survey


def _generic_values(survey, values, *, draft, answered) -> dict:
    new = {}
    if "kind" in values and values["kind"] != survey.kind:
        if values["kind"] not in GENERIC_SURVEY_KINDS or answered:
            raise BuilderError(pgettext(_CTX, "Bu sorğunun növünü dəyişmək olmaz."))
        new["kind"] = values["kind"]
    frozen = not draft
    for key in ("anonymous", "audience", "audience_filter"):
        if key not in values:
            continue
        value = normalize_filter(values[key]) if key == "audience_filter" else values[key]
        if key == "audience" and value not in Audience.values:
            raise BuilderError(pgettext(_CTX, "Auditoriya seçilməlidir."))
        current = normalize_filter(survey.audience_filter) if key == "audience_filter" else getattr(survey, key)
        if value != current and frozen:
            raise BuilderError(
                pgettext(_CTX, "Dərc olunmuş sorğunun anonimliyi və auditoriyası dəyişmir — dublikat yaradın.")
            )
        new[key] = bool(value) if key == "anonymous" else value
    if "opens_on" in values and values["opens_on"] != survey.opens_on:
        if frozen and survey.opens_on and survey.opens_on <= timezone.localdate():
            raise BuilderError(pgettext(_CTX, "Artıq açılmış sorğunun açılış tarixi dəyişmir."))
        new["opens_on"] = values["opens_on"]
    if "closes_on" in values:
        if values["closes_on"] is None and not draft:
            raise BuilderError(pgettext(_CTX, "Dərc olunmuş sorğunun bağlanma tarixi olmalıdır."))
        new["closes_on"] = values["closes_on"]
    if "mandatory" in values:
        new["mandatory"] = bool(values["mandatory"])
    if "gate_policy" in values:
        if values["gate_policy"] not in GatePolicy.values:
            raise BuilderError(pgettext(_CTX, "Qapı siyasəti seçilməlidir."))
        new["gate_policy"] = values["gate_policy"]
    if "defer_days" in values:
        new["defer_days"] = _bounded(
            values["defer_days"],
            0,
            MAX_DEFER_DAYS,
            pgettext(_CTX, "Möhlət 0 ilə %(high)s gün arasında olmalıdır.") % {"high": MAX_DEFER_DAYS},
        )
    if "min_group_size" in values:
        k = _bounded(
            values["min_group_size"],
            MIN_GROUP_SIZE_FLOOR,
            MIN_GROUP_SIZE_CEIL,
            pgettext(_CTX, "Minimum qrup ölçüsü %(low)s ilə %(high)s arasında olmalıdır.")
            % {"low": MIN_GROUP_SIZE_FLOOR, "high": MIN_GROUP_SIZE_CEIL},
        )
        if k != survey.min_group_size and survey.results_published_at:
            raise BuilderError(pgettext(_CTX, "Nəticələr dərc olunandan sonra k-həddi dəyişmir."))
        new["min_group_size"] = k
    return new


# ── Həyat dövrü ─────────────────────────────────────────────────────────────


def publish(survey, *, by_user=None, request=None) -> Survey:
    """Qaralama → dərc. Ümumi sorğu: ən azı bir sual, bağlanma tarixi; açılış boşdursa bu gün."""
    from .survey_notify import notify_if_due

    today = timezone.localdate()
    with transaction.atomic():
        survey = _locked(survey.pk)
        if survey.status != SurveyStatus.DRAFT:
            raise BuilderError(pgettext(_CTX, "Yalnız qaralama sorğu dərc oluna bilər."))
        if not survey.template.questions.exists():
            raise BuilderError(pgettext(_CTX, "Dərc etmək üçün ən azı bir sual əlavə edin."))
        fields = ["status", "published_at", "updated_at"]
        if not survey.is_teacher_evaluation:
            if survey.opens_on is None or survey.opens_on < today:
                survey.opens_on = today
                fields.append("opens_on")
            if survey.closes_on is None:
                raise BuilderError(pgettext(_CTX, "Dərc etmək üçün bağlanma tarixini seçin."))
            if survey.closes_on < survey.opens_on:
                raise BuilderError(pgettext(_CTX, "Bağlanma tarixi açılış tarixindən əvvəl ola bilməz."))
            _validate_dates(survey.opens_on, survey.closes_on)
        survey.status = SurveyStatus.PUBLISHED
        survey.published_at = timezone.now()
        survey.save(update_fields=fields)
        audit(survey, by_user=by_user, action="publish", changes={"closes_on": survey.closes_on}, request=request)
        sync_gate_snapshot(survey.organization)
        notify_if_due(survey)
    return survey


def close(survey, *, by_user=None, request=None) -> Survey:
    with transaction.atomic():
        survey = _locked(survey.pk)
        if survey.is_teacher_evaluation or survey.status != SurveyStatus.PUBLISHED:
            raise BuilderError(pgettext(_CTX, "Yalnız dərc olunmuş sorğu bağlana bilər."))
        survey.status = SurveyStatus.CLOSED
        survey.closed_at = timezone.now()
        survey.save(update_fields=["status", "closed_at", "updated_at"])
        if survey.anonymous:
            from .survey_buffer import publish_results

            publish_results(survey.pk)
        audit(survey, by_user=by_user, action="close", request=request)
        sync_gate_snapshot(survey.organization)
    return survey


def reopen(survey, *, closes_on, by_user=None, request=None) -> Survey:
    today = timezone.localdate()
    with transaction.atomic():
        survey = _locked(survey.pk)
        if survey.status != SurveyStatus.CLOSED:
            raise BuilderError(pgettext(_CTX, "Yalnız bağlı sorğu yenidən açıla bilər."))
        if not closes_on or closes_on < today:
            raise BuilderError(pgettext(_CTX, "Yenidən açmaq üçün gələcək bağlanma tarixi seçin."))
        _validate_dates(survey.opens_on, closes_on)
        survey.status = SurveyStatus.PUBLISHED
        survey.closes_on = closes_on
        survey.closed_at = None
        survey.save(update_fields=["status", "closes_on", "closed_at", "updated_at"])
        audit(survey, by_user=by_user, action="reopen", changes={"closes_on": closes_on}, request=request)
        sync_gate_snapshot(survey.organization)
    return survey


def archive(survey, *, by_user=None, request=None) -> Survey:
    with transaction.atomic():
        survey = _locked(survey.pk)
        if survey.status == SurveyStatus.ARCHIVED:
            return survey
        if survey.is_teacher_evaluation:
            template = survey.template
            if template.is_default:
                raise BuilderError(pgettext(_CTX, "Defolt sual dəsti arxivlənmir — əvvəl başqa dəsti defolt edin."))
            if SurveyCampaign.objects.filter(template=template, status=CampaignStatus.OPEN).exists():
                raise BuilderError(pgettext(_CTX, "Açıq kampaniyanın sual dəsti arxivlənmir."))
            SurveyTemplate.objects.filter(pk=template.pk).update(is_active=False)
        elif survey.status == SurveyStatus.PUBLISHED and survey.anonymous:
            from .survey_buffer import publish_results

            publish_results(survey.pk)
        survey.status = SurveyStatus.ARCHIVED
        survey.archived_at = timezone.now()
        survey.save(update_fields=["status", "archived_at", "updated_at"])
        audit(survey, by_user=by_user, action="archive", request=request)
        sync_gate_snapshot(survey.organization)
    return survey


def restore(survey, *, by_user=None, request=None) -> Survey:
    """Arxivdən çıxarış: heç dərc olunmayıbsa qaralama, əks halda bağlı (müəllim dəsti — hazır)."""
    with transaction.atomic():
        survey = _locked(survey.pk)
        if survey.status != SurveyStatus.ARCHIVED:
            raise BuilderError(pgettext(_CTX, "Sorğu arxivdə deyil."))
        if survey.is_teacher_evaluation:
            SurveyTemplate.objects.filter(pk=survey.template_id).update(is_active=True)
            survey.status = SurveyStatus.PUBLISHED if survey.published_at else SurveyStatus.DRAFT
        else:
            survey.status = SurveyStatus.CLOSED if survey.published_at else SurveyStatus.DRAFT
        survey.archived_at = None
        survey.save(update_fields=["status", "archived_at", "updated_at"])
        audit(survey, by_user=by_user, action="restore", request=request)
    return survey


def delete_draft(survey, *, by_user=None, request=None) -> None:
    with transaction.atomic():
        survey = _locked(survey.pk)
        if survey.status != SurveyStatus.DRAFT or survey.published_at or has_answers(survey):
            raise BuilderError(pgettext(_CTX, "Yalnız heç dərc olunmamış qaralama silinə bilər."))
        if SurveyCampaign.objects.filter(template_id=survey.template_id).exists():
            raise BuilderError(pgettext(_CTX, "Kampaniyada istifadə olunan dəst silinmir."))
        audit(survey, by_user=by_user, action="delete", request=request)
        template_id = survey.template_id
        survey.delete()
        SurveyTemplate.objects.filter(pk=template_id).delete()


def set_default(survey, *, by_user=None, request=None) -> Survey:
    """Müəllim qiymətləndirməsi: yeni kampaniyalar bu dəsti götürsün (təşkilatda BİR defolt)."""
    with transaction.atomic():
        survey = _locked(survey.pk)
        if not survey.is_teacher_evaluation or survey.status != SurveyStatus.PUBLISHED:
            raise BuilderError(pgettext(_CTX, "Defolt yalnız dərc olunmuş müəllim qiymətləndirməsi dəsti ola bilər."))
        SurveyTemplate.objects.filter(organization=survey.organization, is_default=True).exclude(
            pk=survey.template_id
        ).update(is_default=False)
        SurveyTemplate.objects.filter(pk=survey.template_id).update(is_default=True, is_active=True)
        audit(survey, by_user=by_user, action="set_default", request=request)
    return survey


def duplicate(survey, *, by_user=None, request=None) -> Survey:
    """Dəstin tam nüsxəsi (bölmələr + suallar + parametrlər, KODLAR saxlanır) — yeni qaralama."""
    suffix = pgettext(_CTX, "nüsxə")
    title = f"{survey.title[: TITLE_MAX_LENGTH - len(suffix) - 3]} ({suffix})"
    with transaction.atomic():
        source = survey.template
        template = SurveyTemplate.objects.create(
            organization=survey.organization, name=_template_name(title), version=1, is_active=True
        )
        pages = {}
        for page in source.pages.all():
            pages[page.pk] = SurveyPage.objects.create(
                organization=survey.organization,
                template=template,
                title=page.title,
                description=page.description,
                order=page.order,
            )
        SurveyQuestion.objects.bulk_create(
            SurveyQuestion(
                organization=survey.organization,
                template=template,
                code=question.code,
                section=question.section,
                kind=question.kind,
                text=question.text,
                help_text=question.help_text,
                required=question.required,
                in_index=question.in_index,
                order=question.order,
                page=pages.get(question.page_id),
                options=question.options or {},
            )
            for question in source.questions.all()
        )
        clone = Survey.objects.create(
            organization=survey.organization,
            template=template,
            kind=survey.kind,
            title=title,
            description=survey.description,
            anonymous=survey.anonymous,
            audience=survey.audience,
            audience_filter=survey.audience_filter or {},
            mandatory=survey.mandatory,
            gate_policy=survey.gate_policy,
            defer_days=survey.defer_days,
            min_group_size=survey.min_group_size,
            created_by=by_user if getattr(by_user, "pk", None) else None,
        )
        audit(clone, by_user=by_user, action="create", changes={"duplicate_of": survey.pk}, request=request)
    return clone


def default_close_date(today=None):
    today = today or timezone.localdate()
    return today + datetime.timedelta(days=14)
