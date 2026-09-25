"""Defolt şablonun «tənbəl» əkilməsi — ``ensure_default_template(org)``.

Kampaniya açılanda (siqnal, əmr və ya bölmə) çağırılır; yeni təşkilat üçün də
ayrıca miqrasiya lazım deyil. İdempotentdir: eyni ad + versiya varsa yenisi
yaradılmır, çatışmayan suallar isə tamamlanır (tenantın dəyişdiyi mətnə
TOXUNULMUR). Sual dəsti kodda dəyişəndə ``DEFAULT_TEMPLATE_VERSION`` artırılır —
köhnə kampaniyalar öz şablonunda qalır.
"""

from __future__ import annotations

from django.db import IntegrityError, transaction

from ..defaults import DEFAULT_QUESTIONS, DEFAULT_TEMPLATE_NAME, DEFAULT_TEMPLATE_VERSION
from ..models import SurveyQuestion, SurveyTemplate


def ensure_default_template(organization) -> SurveyTemplate:
    template = SurveyTemplate.objects.filter(
        organization=organization, name=DEFAULT_TEMPLATE_NAME, version=DEFAULT_TEMPLATE_VERSION
    ).first()
    if template is None:
        # Tenantın ÖZ defolt şablonu varsa ona toxunulmur; yalnız kod şablonunun
        # köhnə versiyası defoltdursa defolt yeni versiyaya keçir.
        current = SurveyTemplate.objects.filter(organization=organization, is_default=True).first()
        take_default = current is None or current.name == DEFAULT_TEMPLATE_NAME
        try:
            with transaction.atomic():
                if take_default and current is not None:
                    SurveyTemplate.objects.filter(pk=current.pk).update(is_default=False)
                template = SurveyTemplate.objects.create(
                    organization=organization,
                    name=DEFAULT_TEMPLATE_NAME,
                    version=DEFAULT_TEMPLATE_VERSION,
                    is_active=True,
                    is_default=take_default,
                )
        except IntegrityError:  # paralel çağırış — digəri artıq yaradıb
            template = SurveyTemplate.objects.get(
                organization=organization, name=DEFAULT_TEMPLATE_NAME, version=DEFAULT_TEMPLATE_VERSION
            )
    existing = set(template.questions.values_list("code", flat=True))
    missing = [
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
        if code not in existing
    ]
    if missing:
        SurveyQuestion.objects.bulk_create(missing, ignore_conflicts=True)
    return template


def default_template_for(organization) -> SurveyTemplate:
    """Təşkilatın defolt şablonu (yoxdursa kod dəsti əkilir)."""
    template = SurveyTemplate.objects.filter(organization=organization, is_default=True, is_active=True).first()
    return template or ensure_default_template(organization)


def template_questions(template, *, section=None) -> list:
    queryset = template.questions.all()
    if section:
        queryset = queryset.filter(section=section)
    return list(queryset.order_by("order", "code"))
