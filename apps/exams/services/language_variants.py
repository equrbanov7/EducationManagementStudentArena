"""
Çoxdilli imtahan üçün servis qatı.

Bu modul imtahanın dil variantları ilə işləyən bütün məntiqi mərkəzləşdirir:
- mövcud dillərin siyahısı (student modalı + "hansı dillər var" göstərişi üçün),
- seçilmiş dilə görə sual scope-u (randomizer/take bunu istifadə edir),
- attempt üçün effektiv sual sayı (variant override nəzərə alınmaqla),
- müəllim üçün variant CRUD köməkçiləri.

Geriyə uyğunluq: imtahanın aktiv dil variantı yoxdursa və ya yalnız bir dil
varsa, axın köhnə (tək-dilli) davranışla eyni qalır.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils.translation import pgettext

from apps.exams.constants import DEFAULT_EXAM_LANGUAGE, EXAM_LANGUAGE_CHOICES, EXAM_LANGUAGE_VALUES
from apps.exams.models import ExamLanguageVariant, ExamQuestion, ExamQuestionOption
from apps.exams.services.utils import _effective_needed_count

EXAM_LANGUAGE_LABELS = dict(EXAM_LANGUAGE_CHOICES)


def language_label(code):
    return EXAM_LANGUAGE_LABELS.get(code, code)


def active_variants(exam):
    """İmtahanın aktiv dil variantları (dil kodu üzrə sıralı)."""
    return exam.language_variants.filter(is_active=True).order_by("language")


def get_active_variant(exam, language):
    if not language:
        return None
    return exam.language_variants.filter(language=language, is_active=True).first()


def scoped_active_questions(exam, language=None):
    """
    İmtahanın aktiv sualları, opsional olaraq dilə görə süzülmüş.

    `language=None` olduqda bütün aktiv suallar qaytarılır (tək-dilli/legacy axın).
    """
    qs = exam.questions.filter(is_active=True)
    if language:
        qs = qs.filter(language=language)
    return qs


def available_language_options(exam):
    """
    Student-ə təqdim oluna bilən dillərin siyahısı.

    Bir dil yalnız o halda "mövcud"dur ki, ona uyğun AKTİV variant olsun və həmin
    dildə ən azı bir aktiv sual mövcud olsun (boş dil təklif edilmir).
    """
    options = []
    for variant in active_variants(exam):
        count = exam.questions.filter(is_active=True, language=variant.language).count()
        if count <= 0:
            continue
        options.append(
            {
                "language": variant.language,
                "label": language_label(variant.language),
                "display_name": variant.display_name or language_label(variant.language),
                "count": count,
                "variant_id": variant.id,
            }
        )
    return options


def exam_is_multilingual(exam):
    """İmtahanın student-ə görünən birdən çox dili varmı?"""
    return len(available_language_options(exam)) > 1


def resolve_requested_language(exam, requested):
    """İstənilən dil kodunu yalnız mövcud variantlardan biri olduqda qaytarır."""
    requested = (requested or "").strip().lower()
    if not requested:
        return None
    for option in available_language_options(exam):
        if option["language"] == requested:
            return requested
    return None


def auto_language_for_attempt(exam):
    """
    Yalnız bir dil mövcuddursa onun kodunu qaytarır (modal göstərmədən avtomatik
    seçim). 0 və ya çox dil olduqda None qaytarır.
    """
    options = available_language_options(exam)
    if len(options) == 1:
        return options[0]["language"]
    return None


def effective_needed_count_for_attempt(attempt):
    """
    Bu attempt üçün veriləcək sual sayı.

    Dil variantında `question_count_override` varsa o, əks halda imtahanın ümumi
    effektiv sual sayı istifadə olunur.
    """
    variant = getattr(attempt, "language_variant", None)
    if variant is not None and variant.question_count_override:
        return variant.question_count_override
    return _effective_needed_count(attempt.exam)


# ---------------------------------------------------------------------------
# Müəllim tərəfi — variant CRUD (Faza 4 view-ları bunları istifadə edəcək)
# ---------------------------------------------------------------------------
def create_variant(exam, language, *, display_name="", question_count_override=None, is_active=True):
    """
    İmtahana yeni dil variantı əlavə edir (mövcuddursa qaytarır/yeniləyir).

    Validasiya: dil kodu icazəli olmalı; (exam, language) cütü unikaldır
    (DB-də UniqueConstraint var, burada istifadəçiyə aydın mesaj veririk).
    """
    language = (language or "").strip().lower()
    if language not in EXAM_LANGUAGE_VALUES:
        raise ValidationError(pgettext("exams.service.language.error", "invalid_language"))

    variant, created = exam.language_variants.get_or_create(
        language=language,
        defaults={
            "display_name": display_name or "",
            "question_count_override": question_count_override,
            "is_active": is_active,
        },
    )
    if not created:
        # Mövcud variantı yeniləyirik (idempotent davranış).
        variant.display_name = display_name or variant.display_name
        if question_count_override is not None:
            variant.question_count_override = question_count_override
        variant.is_active = is_active
        variant.save(update_fields=["display_name", "question_count_override", "is_active", "updated_at"])
    return variant


def set_variant_active(variant, is_active):
    variant.is_active = bool(is_active)
    variant.save(update_fields=["is_active", "updated_at"])
    return variant


def ensure_default_variant(exam, language=DEFAULT_EXAM_LANGUAGE):
    """İmtahanın ən azı bir dil variantı olmasını təmin edir (default `az`)."""
    variant, _ = exam.language_variants.get_or_create(
        language=language,
        defaults={"is_active": True},
    )
    return variant


@transaction.atomic
def create_questions_for_variant(exam, language, parsed_questions, *, default_points=1):
    """
    ``parse_bulk_mcq`` nəticəsindən bu dil üçün test sualları (ExamQuestion +
    variantlar) yaradır. Suallar avtomatik olaraq dilin variantına bağlanır.

    Qaytarır: yaradılmış ``ExamQuestion`` siyahısı.
    """
    language = (language or "").strip().lower()
    if language not in EXAM_LANGUAGE_VALUES:
        raise ValidationError(pgettext("exams.service.language.error", "invalid_language"))

    variant = ensure_default_variant(exam, language)
    start_order = (exam.questions.aggregate(max_order=Max("order")).get("max_order") or 0) + 1

    rows = []
    option_payloads = []
    for question in parsed_questions or []:
        options = question.get("options") or {}
        # Minimum A–D variant şərti (process_question_bank ilə eyni qayda).
        if any(label not in options for label in ("A", "B", "C", "D")):
            continue
        rows.append(
            ExamQuestion(
                exam=exam,
                language=language,
                language_variant=variant,
                text=question.get("text", ""),
                answer_mode=question.get("answer_mode", "single"),
                order=start_order,
                points=default_points or 1,
            )
        )
        option_payloads.append((options, set(question.get("correct") or [])))
        start_order += 1

    created = ExamQuestion.objects.bulk_create(rows, batch_size=100)

    option_rows = []
    for exam_question, (options, correct) in zip(created, option_payloads):
        for label in "ABCDE":
            if label in options:
                option_rows.append(
                    ExamQuestionOption(
                        question=exam_question,
                        label=label,
                        text=options[label],
                        is_correct=(label in correct),
                    )
                )
    if option_rows:
        ExamQuestionOption.objects.bulk_create(option_rows, batch_size=500)

    return created


__all__ = [
    "EXAM_LANGUAGE_LABELS",
    "active_variants",
    "auto_language_for_attempt",
    "available_language_options",
    "create_questions_for_variant",
    "create_variant",
    "effective_needed_count_for_attempt",
    "ensure_default_variant",
    "exam_is_multilingual",
    "get_active_variant",
    "language_label",
    "resolve_requested_language",
    "scoped_active_questions",
    "set_variant_active",
]
