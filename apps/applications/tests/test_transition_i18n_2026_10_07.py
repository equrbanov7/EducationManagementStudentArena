"""``TransitionDenied`` mətnləri aktiv dilə tərcümə olunur, ``code`` isə sabit qalır (2026-10-07)."""

from __future__ import annotations

from django.utils import translation

import pytest

from apps.applications.constants import ApplicationStatus as S
from apps.applications.state_machine import Action, TransitionDenied, ensure_allowed, rule_for

INVALID_SOURCE = {
    "az": "«reopen» əməli «submitted» statusundan mümkün deyil.",
    "en": "The “reopen” action is not possible from the “submitted” status.",
    "ru": "Действие «reopen» невозможно из статуса «submitted».",
    "tr": "“reopen” işlemi “submitted” durumundan yapılamaz.",
}


def _denied(**kwargs):
    with pytest.raises(TransitionDenied) as excinfo:
        ensure_allowed(**kwargs)
    return excinfo.value


@pytest.mark.parametrize("language", sorted(INVALID_SOURCE))
def test_invalid_source_message_follows_active_language(language):
    with translation.override(language):
        exc = _denied(action=Action.REOPEN, status=S.SUBMITTED.value, text="Kifayət qədər uzun izah mətni")
    assert exc.code == "transition.invalid_source"
    assert exc.params == {"action": Action.REOPEN, "status": S.SUBMITTED.value}
    assert str(exc) == INVALID_SOURCE[language]


def test_placeholders_are_filled_in_every_language():
    for language, expected in {"en": "at least 10 characters", "ru": "не менее 10 символов"}.items():
        with translation.override(language):
            exc = _denied(action=Action.RESOLVE, status=S.IN_REVIEW.value, text="qısa")
        assert exc.code == "transition.text_too_short"
        assert expected in str(exc)
    with translation.override("tr"):
        with pytest.raises(TransitionDenied) as excinfo:
            rule_for("teleport")
    assert excinfo.value.code == "transition.unknown"
    assert str(excinfo.value) == "Bilinmeyen işlem: teleport"


def test_reason_required_in_english():
    with translation.override("en"):
        exc = _denied(action=Action.REJECT, status=S.IN_REVIEW.value, text="  ")
    assert (exc.code, str(exc)) == ("transition.reason_required", "Text is required for this action.")
