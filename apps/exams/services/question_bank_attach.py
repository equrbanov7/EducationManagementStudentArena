"""
Sual bankından imtahana sual əlavə etmə (snapshot) servisi.

Dizayn qərarı: **snapshot-on-attach** — bank sualı (``BankQuestion``) imtahana
əlavə ediləndə məzmunu ``ExamQuestion``-a KOPYALANIR (variantları və medisı ilə
birlikdə), mənbəyə ``source_bank_question`` linki saxlanılır. Beləliklə bankdakı
sonrakı redaktələr köhnə imtahanlara təsir etmir (imtahanlar "dondurulur").

Modul həm də bank-picker üçün tenant-təhlükəsiz siyahı/filtr/say köməkçilərini
təqdim edir.
"""

import hashlib
import logging
import os

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Max, Q

from apps.exams.constants import DEFAULT_EXAM_LANGUAGE
from apps.exams.models import (
    BankQuestion,
    BankQuestionOption,
    ExamQuestion,
    ExamQuestionOption,
    QuestionBank,
)
from apps.exams.services.language_variants import ensure_default_variant
from apps.exams.services.question_bank import normalize_question_text

logger = logging.getLogger(__name__)


def _question_fingerprint(text):
    normalized = normalize_question_text(text or "")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:64]


# ---------------------------------------------------------------------------
# Bank-picker — tenant-təhlükəsiz siyahı / filtr / say
# ---------------------------------------------------------------------------
def accessible_banks(user, organization, *, include_shared=True):
    """
    İstifadəçinin görə biləcəyi aktiv banklar: öz bankları + (eyni təşkilatda
    paylaşılan banklar). Legacy (org=NULL) paylaşılan banklar tenant sızması
    olmasın deyə yalnız sahib vasitəsilə görünür.

    İMTAHAN MƏRKƏZİ istifadəçiləri bank hovuzunun idarəçisidir: təşkilatın BÜTÜN
    aktiv banklarını görür (qəbul axını istənilən org bankına yaza bilir; əvvəlki
    "yalnız öz bankları" qaydası başqa mərkəz üzvünün qəbul etdiyi bankın
    linkini 404 edirdi). Redaktə/silmə yenə yalnız sahibə açıqdır (view qatında).
    """
    from apps.exams.services.access_policy import is_exam_center_user

    visibility = Q(created_by=user)
    if is_exam_center_user(user):
        if organization is not None:
            visibility |= Q(organization=organization)
    elif include_shared and organization is not None:
        visibility |= Q(is_shared=True, organization=organization)
    return QuestionBank.objects.filter(is_active=True).filter(visibility).distinct()


def bank_questions_queryset(
    bank,
    *,
    language=None,
    difficulty=None,
    question_type=None,
    search=None,
    tags=None,
    only_active=True,
):
    """Bankın kitabxana suallarını verilmiş filtrlərə görə qaytarır."""
    qs = bank.library_questions.all()
    if only_active:
        qs = qs.filter(is_active=True)
    if language:
        qs = qs.filter(language=language)
    if difficulty:
        qs = qs.filter(difficulty=difficulty)
    if question_type:
        qs = qs.filter(question_type=question_type)
    if search:
        qs = qs.filter(text__icontains=search)
    if tags:
        for tag in tags:
            qs = qs.filter(tags__contains=tag)
    return qs.order_by("-created_at", "id")


def count_bank_questions(bank, **filters):
    return bank_questions_queryset(bank, **filters).count()


@transaction.atomic
def create_bank_questions_from_parsed(
    bank, parsed_questions, *, language=DEFAULT_EXAM_LANGUAGE, question_type="test", created_by=None, default_points=1
):
    """
    ``parse_bulk_mcq`` nəticəsindən kitabxana sualları (BankQuestion + variantlar)
    yaradır. İmtahandan asılı deyil — sonradan picker ilə imtahanlara snapshot
    kimi əlavə olunur.
    """
    language = (language or DEFAULT_EXAM_LANGUAGE).strip().lower()
    created = []
    for question in parsed_questions or []:
        options = question.get("options") or {}
        if any(label not in options for label in ("A", "B", "C", "D")):
            continue
        text = question.get("text", "")
        bank_question = BankQuestion.objects.create(
            bank=bank,
            text=text,
            question_type=question_type,
            answer_mode=question.get("answer_mode", "single"),
            difficulty="medium",
            language=language,
            points=default_points or 1,
            fingerprint=_question_fingerprint(text),
            created_by=created_by,
        )
        correct = set(question.get("correct") or [])
        option_rows = [
            BankQuestionOption(
                question=bank_question,
                label=label,
                text=options[label],
                is_correct=(label in correct),
            )
            for label in "ABCDE"
            if label in options
        ]
        if option_rows:
            BankQuestionOption.objects.bulk_create(option_rows)
        created.append(bank_question)
    return created


# ---------------------------------------------------------------------------
# Snapshot köçürmə
# ---------------------------------------------------------------------------
def _duplicate_filefield(source_fieldfile, target_instance, target_field_name, *, required=False):
    """
    Mənbə fayl sahəsinin məzmununu hədəf instansiyaya kopyalayır (snapshot).

    Adi əlavə media üçün uğursuzluq loglanır. Mətnin yerini tutan canonical
    source-render üçün isə ``required=True`` fail-closed işləyir: şəkilsiz,
    oxunaqsız snapshot yaradılmır.
    """
    if not source_fieldfile:
        if required:
            raise ValueError("Canonical sual mediası mənbədə yoxdur.")
        return
    try:
        source_fieldfile.open("rb")
        try:
            content = source_fieldfile.read()
        finally:
            source_fieldfile.close()
        name = os.path.basename(source_fieldfile.name)
        getattr(target_instance, target_field_name).save(name, ContentFile(content), save=True)
    except Exception as exc:
        logger.warning(
            "Bank sualı mediası kopyalana bilmədi (q=%s, field=%s).",
            getattr(target_instance, "id", None),
            target_field_name,
            exc_info=True,
        )
        if required:
            raise ValueError("Canonical sual mediası kopyalana bilmədi.") from exc


@transaction.atomic
def attach_bank_questions_to_exam(exam, bank_question_ids, *, block=None, created_by=None, default_points=None):
    """
    Seçilmiş bank suallarını imtahana SNAPSHOT olaraq köçürür.

    - Hər bank sualı üçün yeni ``ExamQuestion`` (+ variantlar + media) yaradılır.
    - ``source_bank_question`` mənbəyə link saxlayır; ``bank`` origin tag-i qalır.
    - Sualın dilinə uyğun ``ExamLanguageVariant`` yoxdursa avtomatik yaradılır.
    - ``order`` imtahandakı mövcud maksimumdan sonra davam edir.

    Qaytarır: yaradılmış ``ExamQuestion`` obyektlərinin siyahısı.
    """
    requested_ids = []
    for raw_id in bank_question_ids or []:
        try:
            requested_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if requested_id not in requested_ids:
            requested_ids.append(requested_id)

    questions_by_id = {
        bank_question.id: bank_question
        for bank_question in BankQuestion.objects.filter(id__in=requested_ids, is_active=True).prefetch_related(
            "options"
        )
    }
    bank_questions = [questions_by_id[question_id] for question_id in requested_ids if question_id in questions_by_id]
    if not bank_questions:
        return []

    last_order = exam.questions.aggregate(max_order=Max("order")).get("max_order") or 0
    variant_cache = {}
    created_questions = []

    for offset, bank_question in enumerate(bank_questions, start=1):
        language = bank_question.language or DEFAULT_EXAM_LANGUAGE
        if language not in variant_cache:
            variant_cache[language] = ensure_default_variant(exam, language)
        variant = variant_cache[language]

        exam_question = ExamQuestion.objects.create(
            exam=exam,
            block=block,
            bank=bank_question.bank,
            source_bank_question=bank_question,
            language=language,
            language_variant=variant,
            text=bank_question.text,
            correct_answer=bank_question.correct_answer,
            answer_mode=bank_question.answer_mode,
            difficulty=bank_question.difficulty,
            difficulty_source="manual",
            points=default_points or bank_question.points or 1,
            tags=list(bank_question.tags or []),
            explanation=bank_question.explanation,
            fingerprint=bank_question.fingerprint or "",
            order=last_order + offset,
            image_replaces_text=bank_question.image_replaces_text,
            is_active=True,
        )

        for bank_option in bank_question.options.all():
            exam_option = ExamQuestionOption.objects.create(
                question=exam_question,
                label=bank_option.label,
                text=bank_option.text,
                image_replaces_text=bank_option.image_replaces_text,
                is_correct=bank_option.is_correct,
            )
            _duplicate_filefield(
                bank_option.image,
                exam_option,
                "image",
                required=bank_option.image_replaces_text,
            )

        # Media-nı snapshot kimi DUBLİKAT et (mənbə silinsə imtahan qorunsun).
        _duplicate_filefield(
            bank_question.image,
            exam_question,
            "image",
            required=bank_question.image_replaces_text,
        )
        _duplicate_filefield(bank_question.video, exam_question, "video")

        created_questions.append(exam_question)

    return created_questions


__all__ = [
    "accessible_banks",
    "attach_bank_questions_to_exam",
    "bank_questions_queryset",
    "count_bank_questions",
    "create_bank_questions_from_parsed",
]
