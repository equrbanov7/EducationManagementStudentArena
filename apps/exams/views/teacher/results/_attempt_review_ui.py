"""Müəllimin cəhd baxış səhifəsi («Bax») — xülasə + sual xəritəsi (yenidən dizayn 2026-10-17).

``teacher_view_attempt`` cavabları onsuz da TAM yükləyir (bir prefetch dəsti); burada
həmin yaddaş siyahısından sorğusuz törənir:

* hər sualın vəziyyəti — test: düzgün / səhv / cavabsız; yazılı/praktiki: tam bal /
  qismən / sıfır / qiymətləndirilməyib / cavabsız (rəng YALNIZ köməkçidir — hər
  vəziyyətin mətn etiketi var);
* bal xülasəsi — test üçün ``calculate_test_attempt_result`` (+ apellyasiya effektiv
  balı), yazılı üçün müəllim balı ÷ çatdırılan sualların snapshot tavanı;
* sual xəritəsi — hər sual üçün səhifə nömrəsi + lövbər (axtarışsız siyahı üzrə).

Bal QAYDASI DƏYİŞMİR: bu modul heç nə hesablamır ki, onsuz da hesablanmamış olsun.
"""

from __future__ import annotations

from urllib.parse import urlencode

from django.utils.translation import pgettext

from apps.exams.services.result_calculation import answer_scoring_keys

CTX = "exams.attempt_review"

#: vəziyyət → (ton, ikon)
STATE_META = {
    "correct": ("success", "fa-circle-check"),
    "partial": ("warning", "fa-circle-half-stroke"),
    "wrong": ("danger", "fa-circle-xmark"),
    "unanswered": ("muted", "fa-circle-minus"),
    "ungraded": ("info", "fa-hourglass-half"),
}


def _state_labels():
    return {
        "correct": pgettext(CTX, "Düzgün"),
        "partial": pgettext(CTX, "Qismən"),
        "wrong": pgettext(CTX, "Səhv"),
        "unanswered": pgettext(CTX, "Cavabsız"),
        "ungraded": pgettext(CTX, "Qiymətləndirilməyib"),
    }


def _written_labels():
    """Yazılı sual üçün «düzgün/səhv» yox, bal dilində etiketlər."""
    return {
        "correct": pgettext(CTX, "Tam bal"),
        "partial": pgettext(CTX, "Qismən bal"),
        "wrong": pgettext(CTX, "0 bal"),
    }


def _test_keys(item):
    """Test sualının açarı — bal hesablanması ilə EYNİ qayda (snapshot + dondurulmuş seçim)."""
    if "correct_ids" not in item:
        points, correct_ids, selected_ids = answer_scoring_keys(item["answer"])
        item["correct_ids"], item["selected_ids"], item["points_value"] = correct_ids, selected_ids, points
    return item["correct_ids"], item["selected_ids"]


def _question_state(item, *, is_test):
    answer = item["answer"]
    if is_test:
        correct_ids, selected_ids = _test_keys(item)
        if not selected_ids:
            return "unanswered"
        return "correct" if correct_ids and selected_ids == correct_ids else "wrong"
    score = answer.teacher_score
    if score is None:
        return "ungraded" if item["has_answer_content"] else "unanswered"
    if score <= 0:
        return "wrong" if item["has_answer_content"] else "unanswered"
    return "correct" if score >= item["max_points"] else "partial"


def annotate_questions(qa_list, *, is_test, page_size):
    """Hər sual elementinə nömrə, vəziyyət, ton, etiket və səhifə əlavə edir (yerində)."""
    labels = _state_labels()
    if not is_test:
        labels.update(_written_labels())
    for index, item in enumerate(qa_list):
        state = _question_state(item, is_test=is_test)
        tone, icon = STATE_META[state]
        item["number"] = index + 1
        item["page"] = index // page_size + 1
        item["state"] = state
        item["state_tone"] = tone
        item["state_icon"] = icon
        item["state_label"] = labels[state]
        item["anchor"] = f"q-{item['question'].id}"
        if is_test:
            # Açar ``_test_keys``-dən (prefetch keşi / snapshot) — sorğu yoxdur.
            item["earned"] = _fmt_points(item["points_value"]) if state == "correct" else 0
            item["max_points"] = _fmt_points(item["points_value"])
        else:
            item["earned"] = item["answer"].teacher_score
    return qa_list


def _fmt_points(value):
    """Decimal bal → «2» / «1.5» (sonda sıfırsız)."""
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _counts(qa_list):
    counts = {key: 0 for key in STATE_META}
    for item in qa_list:
        counts[item["state"]] += 1
    return counts


def _percent(score, max_score):
    if not max_score:
        return None
    return round(float(score) * 100.0 / float(max_score), 1)


def _fmt(value):
    text = f"{value:.1f}" if isinstance(value, float) else str(value)
    return text[:-2] if text.endswith(".0") else text


def build_summary(qa_list, *, exam, attempt, test_result, effective_score_info, appeal_bonus_points):
    """Xülasə kartı + bölgü zolağı üçün kontekst."""
    counts = _counts(qa_list)
    is_test = exam.exam_type == "test"
    labels = _state_labels()
    if not is_test:
        labels.update(_written_labels())
    if is_test and test_result is not None:
        appeal_applied = bool(appeal_bonus_points and appeal_bonus_points > 0 and effective_score_info)
        if appeal_applied:
            percent = float(effective_score_info["effective_percentage"])
            score_text = f"{effective_score_info['effective_score']} / {effective_score_info['max_score']}"
        else:
            percent = float(test_result.percentage)
            score_text = f"{test_result.score_display} / {test_result.max_score_display}"
        status = (
            ("success", pgettext(CTX, "Apellyasiya ilə düzəldilib"))
            if appeal_applied
            else ("info", pgettext(CTX, "Avtomatik qiymətləndirilib"))
        )
        graded = True
        segments = ("correct", "wrong", "unanswered")
    else:
        appeal_applied = False
        max_total = sum(item["max_points"] for item in qa_list)
        graded = attempt.checked_by_teacher and attempt.teacher_score is not None
        percent = _percent(attempt.teacher_score, max_total) if graded else None
        score_text = f"{attempt.teacher_score} / {max_total}" if graded else "—"
        status = (
            ("success", pgettext(CTX, "Yoxlanılıb"))
            if attempt.checked_by_teacher
            else ("warning", pgettext(CTX, "Yoxlanılmayıb"))
        )
        segments = ("correct", "partial", "wrong", "unanswered", "ungraded")
    total = len(qa_list) or 1
    return {
        "is_test": is_test,
        "graded": graded,
        "percent": percent,
        "percent_display": _fmt(percent) if percent is not None else "",
        "percent_tone": ("success" if percent >= 50 else "danger") if percent is not None else "neutral",
        "score_text": score_text,
        "status_tone": status[0],
        "status_label": status[1],
        "appeal_applied": appeal_applied,
        "question_count": len(qa_list),
        "segments": [
            {
                "key": key,
                "label": labels[key],
                "tone": STATE_META[key][0],
                "count": counts[key],
                "share": round(counts[key] * 100.0 / total, 2),
            }
            for key in segments
            if counts[key] or key in ("correct", "wrong")
        ],
        "teacher_feedback": (getattr(attempt, "teacher_feedback", "") or "").strip(),
    }


def build_question_map(qa_list, *, base_path, navigation_params, current_page, searching):
    """Sual xəritəsi — eyni səhifədəki sual üçün yalnız lövbər, başqası üçün səhifə linki."""
    rows = []
    for item in qa_list:
        if item["page"] == current_page and not searching:
            href = f"#{item['anchor']}"
        else:
            query = urlencode({**navigation_params, "questions_page": item["page"]})
            href = f"{base_path}?{query}#{item['anchor']}"
        rows.append(
            {
                "number": item["number"],
                "href": href,
                "tone": item["state_tone"],
                "label": item["state_label"],
                "current": item["page"] == current_page and not searching,
            }
        )
    return rows
