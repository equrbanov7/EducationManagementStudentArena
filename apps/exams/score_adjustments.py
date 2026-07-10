"""İmtahan balına kənar düzəliş üçün GENİŞLƏNMƏ NÖQTƏSİ (M2, 2026-07-02).

Problem: exams view/servisləri apellyasiya bonusunu göstərmək üçün birbaşa
`apps.appeals.services` import edirdi → appeals↔exams dövri asılılığı.

Həll (dependency inversion): exams burada neytral-default hook-lar təyin edir;
appeals (və gələcəkdə istənilən modul) öz implementasiyalarını
AppConfig.ready()-də `register()` ilə qoşur. Appeals quraşdırılmayıbsa/qoşulmayıbsa
davranış: bonus yoxdur, apellyasiya CTA-sı görünmür — təhlükəsiz neytral hal.

Qeyd: bu, exams→appeals importunu aradan qaldırır; appeals→exams istiqaməti
(FK-lar + ready()-dəki qoşulma) qalır və legitimdir.
"""

from __future__ import annotations


def _default_bonus_map(attempt_ids):
    return {}


def _default_apply_bonus(test_result, bonus):
    return test_result


def _default_effective_test_score(attempt, *, answers=None):
    return None


def _default_score_state(attempt):
    return {"bonus_points": 0, "credited_question_ids": [], "bonus_by_question_id": {}}


def _default_student_visible_bonus_map(attempt_ids):
    return {}


def _default_student_visible_effective_test_score(attempt, *, answers=None):
    return None


def _default_student_visible_score_state(attempt):
    return {"bonus_points": 0, "credited_question_ids": [], "bonus_by_question_id": {}}


def _default_student_visible_status_by_qid(attempt):
    return {}


def _default_can_create(request, attempt):
    return False


def _default_remaining_window_seconds(attempt):
    return 0


_HOOKS = {
    "bonus_map": _default_bonus_map,
    "apply_bonus": _default_apply_bonus,
    "effective_test_score": _default_effective_test_score,
    "score_state": _default_score_state,
    "student_visible_bonus_map": _default_student_visible_bonus_map,
    "student_visible_effective_test_score": _default_student_visible_effective_test_score,
    "student_visible_score_state": _default_student_visible_score_state,
    "student_visible_status_by_qid": _default_student_visible_status_by_qid,
    "can_create": _default_can_create,
    "remaining_window_seconds": _default_remaining_window_seconds,
}


def register(name, fn):
    """Hook implementasiyasını qeyd et (AppConfig.ready()-dən çağırılır)."""
    if name not in _HOOKS:
        raise KeyError(f"Naməlum score-adjustment hook-u: {name!r}")
    _HOOKS[name] = fn


def bonus_map(attempt_ids):
    return _HOOKS["bonus_map"](attempt_ids)


def apply_bonus(test_result, bonus):
    return _HOOKS["apply_bonus"](test_result, bonus)


def effective_test_score(attempt, *, answers=None):
    return _HOOKS["effective_test_score"](attempt, answers=answers)


def score_state(attempt):
    return _HOOKS["score_state"](attempt)


def student_visible_bonus_map(attempt_ids):
    return _HOOKS["student_visible_bonus_map"](attempt_ids)


def student_visible_effective_test_score(attempt, *, answers=None):
    return _HOOKS["student_visible_effective_test_score"](attempt, answers=answers)


def student_visible_score_state(attempt):
    return _HOOKS["student_visible_score_state"](attempt)


def student_visible_status_by_qid(attempt):
    return _HOOKS["student_visible_status_by_qid"](attempt)


def can_create(request, attempt):
    return _HOOKS["can_create"](request, attempt)


def remaining_window_seconds(attempt):
    return _HOOKS["remaining_window_seconds"](attempt)
