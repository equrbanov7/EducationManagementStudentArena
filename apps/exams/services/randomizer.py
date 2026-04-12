import random

from apps.exams.constants import LABELS
from apps.exams.models import ExamAnswer
from apps.exams.services.utils import _attempt_has_any_answer, _effective_needed_count


# Verilmiş attempt_id və question üçün options-ları random sırada qaytarır.
def build_shuffled_options(attempt_id, question):
    opts = list(question.options.all())
    rnd = random.Random(f"{attempt_id}:{question.id}")  # nosec B311
    rnd.shuffle(opts)
    packed = []
    for i, opt in enumerate(opts):
        packed.append(
            {
                "id": opt.id,
                "label": LABELS[i] if i < len(LABELS) else "",
                "text": opt.text,
            }
        )
    return packed


def _build_block_pick_plan(blocks, total_needed):
    """
    Bloklara düşəcək sual sayını blok sırasına görə sabit paylaşdırır.

    Nümunə:
    - 5 sual / 5 blok -> [1, 1, 1, 1, 1]
    - 7 sual / 5 blok -> [2, 2, 1, 1, 1]
    - 3 sual / 5 blok -> [1, 1, 1, 0, 0]
    """
    if total_needed <= 0 or not blocks:
        return {}

    base, remainder = divmod(total_needed, len(blocks))
    plan = {block.id: base for block in blocks}

    for block in blocks[:remainder]:
        plan[block.id] += 1

    return plan


# Verilmiş attempt üçün sualları random seçir və ExamAnswer yaradır.
def generate_random_questions_for_attempt(attempt, *, force_rebuild: bool = False):
    """
    Yeni attempt üçün sualları random seçir və ExamAnswer yaradır.
    - default: 10 sual
    - 0: hamısı (amma random order)
    - blok varsa: bərabər pay + qalıq sualları blok sırasına görə paylaşdırır
    - refresh edəndə dəyişməsin deyə ExamAnswer-da sabitlənir
    """
    exam = attempt.exam

    # Əgər artıq suallar yaradılıbsa:
    if attempt.answers.exists():
        if not force_rebuild:
            return
        # force rebuild istənirsə, amma tələbə cavab yazıbsa toxunmuruq
        if _attempt_has_any_answer(attempt):
            return
        attempt.answers.all().delete()

    total_needed = _effective_needed_count(exam)

    # bütün sualları al (DB hit az olsun)
    all_qs = list(exam.questions.filter(is_active=True))

    if not all_qs:
        return

    # Əgər tələb olunan say hamısından çoxdursa -> hamısını götür
    if total_needed >= len(all_qs):
        selected_qs = all_qs[:]
        random.shuffle(selected_qs)  # “hamısı” olsa belə random sıra
    else:
        selected_qs = []
        blocks = list(exam.question_blocks.order_by("order", "id"))

        if blocks:
            block_question_map = {}
            non_empty_blocks = []
            for block in blocks:
                block_qs = list(block.questions.filter(is_active=True))
                random.shuffle(block_qs)
                if block_qs:
                    block_question_map[block.id] = block_qs
                    non_empty_blocks.append(block)

            blocks = non_empty_blocks

        if blocks:
            block_pick_plan = _build_block_pick_plan(blocks, total_needed)

            picked_ids = set()

            # bloklardan payla
            for block in blocks:
                take = block_pick_plan.get(block.id, 0)
                if take <= 0:
                    continue

                block_qs = block_question_map[block.id]
                taken_from_block = 0

                for q in block_qs:
                    if len(selected_qs) >= total_needed:
                        break
                    if q.id in picked_ids:
                        continue
                    selected_qs.append(q)
                    picked_ids.add(q.id)
                    taken_from_block += 1
                    if taken_from_block >= take:
                        break

                # blokda sual çatmadısa, problem deyil – aşağıda fill edəcəyik

            # çatmayanı digər suallardan doldur
            if len(selected_qs) < total_needed:
                remaining = [q for q in all_qs if q.id not in picked_ids]
                random.shuffle(remaining)
                selected_qs.extend(remaining[: (total_needed - len(selected_qs))])

            # son dəfə də ümumi sıranı qarışdır (blok “izləri” qalmasın)
            random.shuffle(selected_qs)

        else:
            # blok yoxdursa — ümumi pool-dan random seç
            random.shuffle(all_qs)
            selected_qs = all_qs[:total_needed]

    # ExamAnswer-ları bulk yarat
    ExamAnswer.objects.bulk_create(
        [ExamAnswer(attempt=attempt, question=q) for q in selected_qs],
        ignore_conflicts=True,
    )
