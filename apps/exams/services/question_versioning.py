"""Cavablanmış sualın «yeni versiya» ilə dəyişdirilməsi (sahib 2026-11-11).

Sahib: «sualları siləndə belə bir hal olur ki, o suallardan kimsə imtahan verib, amma mən onu dəyişməliyəm;
silmək olmur — necə edək?»

Vəziyyət (araşdırma):

* SİLMƏK — ``question_invariants._guard_delete_history`` cavabı / apellyasiyası olan sualı buraxmır
  (``ExamAnswer.question`` CASCADE-dir: sual silinsə təqdim olunmuş cavablar da silinər);
* REDAKTƏ — əvvəllər sual YERİNDƏ dəyişirdi. Bal ``question_snapshot`` ilə qorunsa da, keçmiş cəhdin
  baxışında / apellyasiyada / statistikada tələbənin görmədiyi mətn və variantlar görünürdü, snapshot-suz
  (köhnə) cavablar isə yeni açarla yenidən hesablanırdı.

Yol: tarixçəsi olan sual heç vaxt dəyişdirilmir. Redaktə forması saxlananda

1. köhnə sual sətri və variantları OLDUĞU KİMİ qalır, yalnız ``is_active=False`` olur;
2. redaktə olunmuş məzmunla YENİ sual yaradılır (``replaces`` → köhnə sual), aktivdir və eyni sıra
   nömrəsini daşıyır — gələcək cəhdlər onu alır;
3. audit sətri yazılır (kim, köhnə → yeni sual, cavab sayı).

Keçmiş cəhdlərin balı dəyişmir. Keçmiş cəhdlər üçün düzgün cavabın düzəlişi ayrıca axındır —
``apps.appeals`` «Cavab açarı düzəlişi» (``AnswerKeyCorrection``); burada təkrarlanmır.

Kodlaşdırma imtahanında (``exam_type == "coding"``) sualın test halları ayrıca cədvəldədir və təqdimatlar
ona bağlıdır — orada versiyalama tətbiq olunmur (redaktə əvvəlki kimi yerindədir).
"""

from __future__ import annotations

from django.db import transaction
from django.db.models import Exists, OuterRef, Q

AUDIT_RESOURCE = "exam_question_version"
AUDIT_REASON = "exam_question_new_version"
_COPIED_OPTION_FIELDS = ("image", "image_replaces_text")


def history_question_ids(question_ids) -> set[int]:
    """Verilmiş suallardan tarixçəsi (cavab / apellyasiya / açar düzəlişi) olanların ID-ləri."""
    from apps.exams.models import ExamQuestion

    ids = list(question_ids)
    if not ids:
        return set()
    # TƏK sorğu: hər əlaqə üçün korrelyasiyalı EXISTS (``question_id`` indeksləri) — JOIN + DISTINCT yox.
    # Apellyasiya modelləri əks əlaqədən götürülür (exams → appeals birbaşa importu yoxdur).
    condition = Q()
    for relation in ("answers", "appeal_items", "answer_key_corrections"):
        related_model = ExamQuestion._meta.get_field(relation).related_model
        condition |= Exists(related_model._base_manager.filter(question_id=OuterRef("pk")))
    return set(ExamQuestion.objects.filter(pk__in=ids).filter(condition).order_by().values_list("pk", flat=True))


def question_has_history(question) -> bool:
    return bool(question.pk) and question.pk in history_question_ids([question.pk])


def versioning_applies(exam, question) -> bool:
    """Bu sualın redaktəsi yeni versiya yaratmalıdırmı?"""
    return exam.exam_type != "coding" and question_has_history(question)


@transaction.atomic
def save_question_as_new_version(exam, form, *, by_user=None, request=None, prepare=None):
    """Doğrulanmış redaktə formasını YENİ sual kimi saxla; köhnə sual toxunulmaz qalıb deaktiv olunur.

    ``form.instance`` — köhnə sualın yaddaşdakı (forma tərəfindən artıq dəyişdirilmiş) surətidir; bazadakı
    sətir dəyişməyib. ``prepare(question)`` — saxlamadan əvvəl view-in öz tənzimləmələri (dil variantı və s.).
    Qaytarır: ``(new_question, old_question_id)``.
    """
    from apps.exams.models import ExamAnswer, ExamQuestion, ExamQuestionOption

    exam_model = type(exam)
    exam_model.objects.select_for_update().get(pk=exam.pk)  # kilid sırasının kökü (publish / sual mutasiyaları)
    old_id = form.instance.pk
    source = ExamQuestion.objects.select_for_update().get(pk=old_id, exam_id=exam.pk)
    source_options = list(source.options.order_by("id"))

    question = form.save(commit=False)
    question.pk = None
    question.id = None
    question._state.adding = True
    question.exam = exam
    question.replaces = source
    question.is_active = True
    question.created_at = None
    question.usage_count = 0
    if prepare is not None:
        prepare(question)
    # Əvvəl yenisi yaradılır, sonra köhnəsi deaktiv olunur — aktiv imtahan bir an da aktiv sualsız qalmır.
    question.save()

    if exam.exam_type == "test":
        labels = ["A", "B", "C", "D", "E"]
        options = []
        for position, option in enumerate(form._get_cleaned_options(form.cleaned_data)):
            source_index = option["index"] - 1
            previous = source_options[source_index] if source_index < len(source_options) else None
            new_option = ExamQuestionOption(
                question=question,
                label=labels[position] if position < len(labels) else None,
                text=option["text"],
                is_correct=option["is_correct"],
            )
            if previous is not None:  # variant şəkli (import mediası) yeni versiyada da qalır
                for field in _COPIED_OPTION_FIELDS:
                    setattr(new_option, field, getattr(previous, field))
            options.append(new_option)
        ExamQuestionOption.objects.bulk_create(options)

    ExamQuestion.objects.filter(pk=source.pk).update(is_active=False)

    from apps.audit.public import log_action
    from core.constants import AuditAction

    log_action(
        action=AuditAction.UPDATE,
        user=by_user,
        organization=exam.organization,
        resource_type=AUDIT_RESOURCE,
        resource_id=str(exam.pk),
        resource_repr=str(exam.title)[:200],
        changes={
            "exam_slug": exam.slug,
            "old_question_id": source.pk,
            "new_question_id": question.pk,
            "order": source.order,
            "old_was_active": bool(source.is_active),
            "answers_kept": ExamAnswer.objects.filter(question_id=source.pk).count(),
        },
        reason=AUDIT_REASON,
        request=request,
    )
    return question, source.pk


__all__ = [
    "AUDIT_REASON",
    "AUDIT_RESOURCE",
    "history_question_ids",
    "question_has_history",
    "save_question_as_new_version",
    "versioning_applies",
]
