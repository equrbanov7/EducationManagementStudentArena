import random
from collections import Counter

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.db.models import Count

from apps.exams.constants import LABELS
from apps.exams.models import ExamAnswer
from apps.exams.services.language_variants import effective_needed_count_for_attempt
from apps.exams.services.utils import _attempt_has_any_answer

_DIFFICULTY_ORDER = ("easy", "medium", "hard")
_QUESTION_SOFT_USAGE_CAP = 4


def _usage_cache_seconds() -> int:
    try:
        return max(0, int(getattr(settings, "EXAM_RANDOMIZER_USAGE_CACHE_SECONDS", 30)))
    except (TypeError, ValueError):
        return 30


def _cached_usage_counts(cache_key: str, builder):
    ttl = _usage_cache_seconds()
    if ttl <= 0:
        return builder()

    try:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
    except Exception:
        return builder()

    value = builder()
    try:
        cache.set(cache_key, value, ttl)
    except Exception:
        pass
    return value


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
                # Düstur/şəkil variantı (PDF idxalından) — varsa URL, yoxdursa None.
                "image": opt.image.url if getattr(opt, "image", None) else None,
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


def _build_fair_block_pick_plan(blocks, total_needed, block_usage_counts):
    if total_needed <= 0 or not blocks:
        return {}

    base, remainder = divmod(total_needed, len(blocks))
    plan = {block.id: base for block in blocks}

    ranked_blocks = sorted(
        blocks,
        key=lambda block: (
            block_usage_counts.get(block.id, 0),
            getattr(block, "order", 0),
            block.id,
        ),
    )
    for block in ranked_blocks[:remainder]:
        plan[block.id] += 1

    return plan


def _historical_question_usage(exam, attempt):
    def build_counts():
        rows = (
            ExamAnswer.objects.filter(attempt__exam=exam)
            .exclude(attempt=attempt)
            .values("question_id")
            .annotate(total=Count("attempt__user_id", distinct=True))
        )
        return {row["question_id"]: row["total"] for row in rows}

    return _cached_usage_counts(f"emsarena:exam-randomizer:question-usage:{exam.id}", build_counts)


def _historical_block_usage(exam, attempt):
    def build_counts():
        rows = (
            ExamAnswer.objects.filter(attempt__exam=exam, question__block_id__isnull=False)
            .exclude(attempt=attempt)
            .values("question__block_id")
            .annotate(total=Count("attempt__user_id", distinct=True))
        )
        return {row["question__block_id"]: row["total"] for row in rows}

    return _cached_usage_counts(f"emsarena:exam-randomizer:block-usage:{exam.id}", build_counts)


def _normalise_difficulty(value):
    value = (value or "medium").strip().lower()
    return value if value in _DIFFICULTY_ORDER else "medium"


def _build_difficulty_targets(questions, total_needed):
    if total_needed <= 0 or not questions:
        return Counter()

    pool_counts = Counter(_normalise_difficulty(question.difficulty) for question in questions)
    pool_total = sum(pool_counts.values())
    if pool_total <= 0:
        return Counter()

    targets = Counter()
    fractional_parts = []
    for difficulty in _DIFFICULTY_ORDER:
        exact = (total_needed * pool_counts.get(difficulty, 0)) / pool_total
        whole = int(exact)
        targets[difficulty] = whole
        fractional_parts.append((exact - whole, difficulty))

    remaining = total_needed - sum(targets.values())
    fractional_parts.sort(key=lambda item: (-item[0], _DIFFICULTY_ORDER.index(item[1])))

    while remaining > 0:
        progressed = False
        for _, difficulty in fractional_parts:
            if targets[difficulty] >= pool_counts.get(difficulty, 0):
                continue
            targets[difficulty] += 1
            remaining -= 1
            progressed = True
            if remaining <= 0:
                break
        if not progressed:
            break

    return targets


def _difficulty_penalty(question, difficulty_targets, use_difficulty_balance):
    if not use_difficulty_balance or not difficulty_targets:
        return 0
    if sum(max(count, 0) for count in difficulty_targets.values()) <= 0:
        return 0
    return 0 if difficulty_targets.get(_normalise_difficulty(question.difficulty), 0) > 0 else 1


def _question_rank(
    question,
    *,
    question_usage_counts,
    difficulty_targets,
    random_tiebreakers,
    use_fair_distribution,
    use_difficulty_balance,
):
    usage_count = question_usage_counts.get(question.id, 0) if use_fair_distribution else 0
    over_soft_cap = 1 if use_fair_distribution and usage_count >= _QUESTION_SOFT_USAGE_CAP else 0
    return (
        over_soft_cap,
        _difficulty_penalty(question, difficulty_targets, use_difficulty_balance),
        usage_count,
        random_tiebreakers.get(question.id, 0),
    )


def _pick_questions(
    candidates,
    take,
    *,
    selected_ids,
    question_usage_counts,
    difficulty_targets,
    use_fair_distribution,
    use_difficulty_balance,
):
    available = [question for question in candidates if question.id not in selected_ids]
    if take <= 0 or not available:
        return []

    random_tiebreakers = {question.id: random.random() for question in available}  # nosec B311
    picked = []

    while len(picked) < take and available:
        available.sort(
            key=lambda question: _question_rank(
                question,
                question_usage_counts=question_usage_counts,
                difficulty_targets=difficulty_targets,
                random_tiebreakers=random_tiebreakers,
                use_fair_distribution=use_fair_distribution,
                use_difficulty_balance=use_difficulty_balance,
            )
        )
        question = available.pop(0)
        picked.append(question)
        selected_ids.add(question.id)

        difficulty = _normalise_difficulty(question.difficulty)
        if use_difficulty_balance and difficulty_targets.get(difficulty, 0) > 0:
            difficulty_targets[difficulty] -= 1

    return picked


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

    with transaction.atomic():
        attempt = attempt.__class__.objects.select_for_update().select_related("exam").get(pk=attempt.pk)
        exam = attempt.exam

        # Əgər artıq suallar yaradılıbsa:
        if attempt.answers.exists():
            if not force_rebuild:
                return
            # force rebuild istənirsə, amma tələbə cavab yazıbsa toxunmuruq
            if _attempt_has_any_answer(attempt):
                return
            attempt.answers.all().delete()

        total_needed = effective_needed_count_for_attempt(attempt)

        # Çoxdilli imtahanda yalnız attempt-in seçilmiş dilindəki sualları
        # nəzərə alırıq. Dil seçilməyibsə (tək-dilli/legacy) bütün suallar.
        attempt_language = getattr(attempt, "language", None)
        active_question_filter = {"is_active": True}
        if attempt_language:
            active_question_filter["language"] = attempt_language

        # bütün sualları al (DB hit az olsun)
        all_qs = list(exam.questions.filter(**active_question_filter))

        if not all_qs:
            return

        use_fair_distribution = bool(getattr(exam, "fair_question_distribution_enabled", True))
        use_difficulty_balance = bool(getattr(exam, "ai_difficulty_balance_enabled", True))
        question_usage_counts = _historical_question_usage(exam, attempt) if use_fair_distribution else {}
        block_usage_counts = _historical_block_usage(exam, attempt) if use_fair_distribution else {}
        difficulty_targets = _build_difficulty_targets(all_qs, total_needed) if use_difficulty_balance else Counter()
        selected_ids = set()

        # Əgər tələb olunan say hamısından çoxdursa -> hamısını götür
        if total_needed >= len(all_qs):
            selected_qs = _pick_questions(
                all_qs,
                len(all_qs),
                selected_ids=selected_ids,
                question_usage_counts=question_usage_counts,
                difficulty_targets=difficulty_targets,
                use_fair_distribution=use_fair_distribution,
                use_difficulty_balance=use_difficulty_balance,
            )
        else:
            selected_qs = []
            blocks = list(exam.question_blocks.order_by("order", "id"))

            if blocks:
                block_question_map = {}
                non_empty_blocks = []
                for block in blocks:
                    block_qs = list(block.questions.filter(**active_question_filter))
                    if block_qs:
                        block_question_map[block.id] = block_qs
                        non_empty_blocks.append(block)

                blocks = non_empty_blocks

            if blocks:
                if use_fair_distribution:
                    block_pick_plan = _build_fair_block_pick_plan(blocks, total_needed, block_usage_counts)
                else:
                    block_pick_plan = _build_block_pick_plan(blocks, total_needed)

                # bloklardan payla
                for block in blocks:
                    take = block_pick_plan.get(block.id, 0)
                    if take <= 0:
                        continue

                    picked = _pick_questions(
                        block_question_map[block.id],
                        take,
                        selected_ids=selected_ids,
                        question_usage_counts=question_usage_counts,
                        difficulty_targets=difficulty_targets,
                        use_fair_distribution=use_fair_distribution,
                        use_difficulty_balance=use_difficulty_balance,
                    )
                    selected_qs.extend(picked)

                    if len(selected_qs) >= total_needed:
                        break

                # blokda sual çatmadısa, problem deyil – aşağıda fill edəcəyik

                # çatmayanı digər suallardan doldur
                if len(selected_qs) < total_needed:
                    selected_qs.extend(
                        _pick_questions(
                            all_qs,
                            total_needed - len(selected_qs),
                            selected_ids=selected_ids,
                            question_usage_counts=question_usage_counts,
                            difficulty_targets=difficulty_targets,
                            use_fair_distribution=use_fair_distribution,
                            use_difficulty_balance=use_difficulty_balance,
                        )
                    )

                # son dəfə də ümumi sıranı qarışdır (blok “izləri” qalmasın)
                random.shuffle(selected_qs)

            else:
                # blok yoxdursa — ümumi pool-dan seç
                selected_qs = _pick_questions(
                    all_qs,
                    total_needed,
                    selected_ids=selected_ids,
                    question_usage_counts=question_usage_counts,
                    difficulty_targets=difficulty_targets,
                    use_fair_distribution=use_fair_distribution,
                    use_difficulty_balance=use_difficulty_balance,
                )

        # ExamAnswer-ları bulk yarat
        ExamAnswer.objects.bulk_create(
            [ExamAnswer(attempt=attempt, question=q) for q in selected_qs],
            ignore_conflicts=True,
        )
