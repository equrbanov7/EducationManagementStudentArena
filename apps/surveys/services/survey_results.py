"""Sorğu qurucusu (2026-09-30) — ümumi sorğunun nəticələri, iştirak, respondentlər.

AÇIQLAMA NƏZARƏTİ (anonim sorğu; müəllim qiymətləndirməsinin M-1/M-2 qaydaları ilə eyni ruh):

* CANLI NƏTİCƏ YOXDUR: nəticə yalnız ilk dərcdən sonra (``results_published_at`` — bağlanma /
  ``closes_on`` keçəndən sonra ilk baxış); davam edən sorğuda yalnız iştirak göstərilir.
* ``n < k`` → bütün nəticə gizli; sualın özünün cavab sayı ``< k`` (məcburi olmayan sual) → o sual
  gizli. Paylanmalar yalnız FAİZLƏ (xam say yoxdur), saylar səbətlə (``count_bucket``), iştirak
  faizi 5-ə yuvarlaq (``round5``).
* Mətn cavabları yalnız sualın cavab sayı ``≥ k`` olanda, identifikatorsuz, TƏSADÜFİ sırada.
* Respondentlər (ad, tarix) YALNIZ şəxsli sorğuda və yalnız ``survey.manage`` daşıyana.
"""

from __future__ import annotations

import random
from collections import Counter, defaultdict

from django.contrib.auth import get_user_model
from django.db.models import Count
from django.utils import timezone
from django.utils.translation import pgettext

from ..constants import CHOICE_KINDS, DEFAULT_MIN_GROUP_SIZE, TEXT_KINDS, QuestionKind
from ..defaults import LIKERT_LABELS
from ..models import SurveyParticipation, SurveySubmission, SurveySubmissionAnswer
from .analytics_guard import count_bucket, round5
from .audience import audience_user_ids, normalize_filter, unit_rows, user_locations
from .survey_buffer import publish_if_due

_RANDOM = random.SystemRandom()
TEXT_LIMIT = 300


def k_of(survey) -> int:
    if not survey.anonymous:
        return 1
    return max(int(survey.min_group_size or DEFAULT_MIN_GROUP_SIZE), DEFAULT_MIN_GROUP_SIZE)


def results_state(survey, today=None) -> str:
    """``ready`` | ``live`` (anonim, dərc gözləyir) | ``draft``."""
    today = today or timezone.localdate()
    if survey.status == "draft":
        return "draft"
    if not survey.anonymous:
        return "ready"
    publish_if_due(survey, today)
    return "ready" if survey.results_published_at else "live"


def _pct(part, whole, anonymous=False):
    """Faiz — anonim sorğuda 5-ə yuvarlaq (Audit 2026-09-28 SV-4: tam faizlər ``n``-i açırdı)."""
    if not whole:
        return 0
    return round5(part / whole) if anonymous else round(100.0 * part / whole)


def likert_labels(question) -> list:
    options = question.options if isinstance(question.options, dict) else {}
    custom = options.get("labels") or []
    return [
        (custom[index] if index < len(custom) and custom[index] else pgettext("surveys.scale", label))
        for index, (_score, label) in enumerate(LIKERT_LABELS)
    ]


def _number_card(question, counts, n, anonymous):
    low, high = {QuestionKind.LIKERT5: (1, 5), QuestionKind.NPS: (0, 10), QuestionKind.YESNO: (0, 1)}.get(
        question.kind, (1, 10)
    )
    total = sum(counts.values())
    labels = {}
    if question.kind == QuestionKind.LIKERT5:
        labels = dict(zip(range(1, 6), likert_labels(question), strict=True))
    elif question.kind == QuestionKind.YESNO:
        labels = {1: pgettext("surveys.respond", "Bəli"), 0: pgettext("surveys.respond", "Xeyr")}
    order = [1, 0] if question.kind == QuestionKind.YESNO else list(range(low, high + 1))
    buckets = [
        {
            "label": labels.get(score, str(score)),
            "score": score,
            "pct": _pct(counts.get(score, 0), total, anonymous),
            "count": None if anonymous else counts.get(score, 0),
        }
        for score in order
    ]
    card = {"buckets": buckets}
    if total and question.kind in (QuestionKind.LIKERT5, QuestionKind.NPS, QuestionKind.SCALE10):
        card["avg"] = round(sum(score * c for score, c in counts.items()) / total, 1 if anonymous else 2)
    if total and question.kind == QuestionKind.NPS:
        promoters = sum(c for score, c in counts.items() if score >= 9)
        detractors = sum(c for score, c in counts.items() if score <= 6)
        promoters_pct, detractors_pct = _pct(promoters, total, anonymous), _pct(detractors, total, anonymous)
        card["nps"] = {
            "score": promoters_pct - detractors_pct,
            "promoters": promoters_pct,
            "passives": max(100 - promoters_pct - detractors_pct, 0),
            "detractors": detractors_pct,
        }
    return card


def _choice_card(question, choice_counts, respondents, anonymous):
    options = question.options if isinstance(question.options, dict) else {}
    rows = []
    for item in options.get("choices") or []:
        count = choice_counts.get(item.get("key"), 0)
        rows.append(
            {
                "label": item.get("label", ""),
                "pct": _pct(count, respondents, anonymous),
                "count": None if anonymous else count,
            }
        )
    return {"buckets": rows}


def question_results(survey, *, with_identity=False) -> dict:
    """``{"k", "n", "n_label", "suppressed", "questions": [...]}`` — bax modul sənədi."""
    k = k_of(survey)
    anonymous = survey.anonymous
    submissions = SurveySubmission.objects.filter(survey=survey)
    n = submissions.count()
    suppressed = anonymous and n < k
    questions = list(survey.template.questions.select_related("page").order_by("order", "code"))
    result = {"k": k, "n": None if anonymous else n, "n_label": count_bucket(n), "suppressed": suppressed}
    if suppressed:
        result["questions"] = []
        return result
    answers = SurveySubmissionAnswer.objects.filter(submission__survey=survey)
    answered = dict(answers.values("question_id").annotate(c=Count("id")).values_list("question_id", "c"))
    numbers: dict = defaultdict(Counter)
    for question_id, number, count in (
        answers.filter(number__isnull=False)
        .values("question_id", "number")
        .annotate(c=Count("id"))
        .values_list("question_id", "number", "c")
    ):
        numbers[question_id][number] = count
    choice_ids = [q.pk for q in questions if q.kind in CHOICE_KINDS]
    choices: dict = defaultdict(Counter)
    for question_id, keys in answers.filter(question_id__in=choice_ids).values_list("question_id", "choices"):
        choices[question_id].update(keys or [])
    text_ids = [q.pk for q in questions if q.kind in TEXT_KINDS]
    texts: dict = defaultdict(list)
    text_rows = answers.filter(question_id__in=text_ids).exclude(text="")
    if with_identity and not anonymous:
        user_model = get_user_model()
        for question_id, text, first, last, username in text_rows.values_list(
            "question_id",
            "text",
            "submission__respondent__first_name",
            "submission__respondent__last_name",
            "submission__respondent__" + user_model.USERNAME_FIELD,
        ):
            texts[question_id].append({"text": text, "who": f"{first or ''} {last or ''}".strip() or username or ""})
    else:
        for question_id, text in text_rows.values_list("question_id", "text"):
            texts[question_id].append({"text": text, "who": ""})
    cards = []
    for question in questions:
        count = answered.get(question.pk, 0)
        card = {
            "question": question,
            "kind": question.kind,
            "answered_label": count_bucket(count),
            "answered": None if anonymous else count,
            "hidden": anonymous and count < k,
            "is_text": question.kind in TEXT_KINDS,
            "avg": None,
            "nps": None,
            "buckets": [],
            "texts": [],
            "texts_more": 0,
        }
        if not card["hidden"]:
            if question.kind in TEXT_KINDS:
                items = texts.get(question.pk, [])
                if anonymous:
                    _RANDOM.shuffle(items)
                card["texts"] = items[:TEXT_LIMIT]
                card["texts_more"] = max(len(items) - TEXT_LIMIT, 0)
            elif question.kind in CHOICE_KINDS:
                card.update(_choice_card(question, choices.get(question.pk, Counter()), count, anonymous))
            else:
                card.update(_number_card(question, numbers.get(question.pk, Counter()), count, anonymous))
        cards.append(card)
    result["questions"] = cards
    return result


def respondents(survey) -> list:
    """Şəxsli sorğunun respondentləri (ad, istifadəçi adı, tarix) — çağıran icazəni yoxlayır."""
    if survey.anonymous:
        return []
    user_model = get_user_model()
    rows = (
        SurveySubmission.objects.filter(survey=survey, respondent__isnull=False)
        .order_by("-submitted_at")
        .values_list(
            "respondent__first_name",
            "respondent__last_name",
            "respondent__" + user_model.USERNAME_FIELD,
            "submitted_at",
        )
    )
    return [
        {"name": f"{first or ''} {last or ''}".strip() or username, "username": username, "at": at}
        for first, last, username, at in rows[:2000]
    ]


def participation(survey) -> dict:
    """Gözlənilən / tamamlayan / faiz + vahidlər üzrə (anonim sorğuda səbət və 5-lik faiz)."""
    anonymous = survey.anonymous
    audience = audience_user_ids(survey)
    done = set(SurveyParticipation.objects.filter(survey=survey).values_list("user_id", flat=True)) & audience
    total = {"expected": len(audience), "completed": len(done)}
    units = unit_rows(survey.organization_id, normalize_filter(survey.audience_filter)["units"] or None)
    located = user_locations(survey.organization_id, audience) if units else {}
    rows = []
    for unit in units:
        members = {
            user_id
            for user_id, places in located.items()
            if any(
                str(unit_id) == str(unit["id"]) or (path or "").startswith(f"{unit['path']}/")
                for unit_id, path in places
            )
        }
        if not members:
            continue
        rows.append(_rate_row(unit["name"], len(members), len(members & done), anonymous))
    return {**_rate_row("", total["expected"], total["completed"], anonymous), "units": rows}


def _rate_row(label, expected, completed, anonymous) -> dict:
    rate = (100.0 * completed / expected) if expected else None
    if anonymous:
        return {
            "label": label,
            "expected": count_bucket(expected),
            "completed": count_bucket(completed),
            "rate": round5(rate / 100.0) if rate is not None else None,
        }
    return {
        "label": label,
        "expected": expected,
        "completed": completed,
        "rate": round(rate) if rate is not None else None,
    }
