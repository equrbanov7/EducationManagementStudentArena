"""
Apellyasiya başlığının (Appeal) status state-machine-i.

İcazəli keçidlər ``constants.APPEAL_STATUS_TRANSITIONS``-də təyin olunub.
"""

from django.core.exceptions import ValidationError
from django.utils.translation import pgettext

from apps.appeals.constants import APPEAL_STATUS_TRANSITIONS


class InvalidAppealTransition(ValidationError):
    """İcazəsiz status keçidi cəhdi."""


def can_transition(current, target):
    if current == target:
        return True
    return target in APPEAL_STATUS_TRANSITIONS.get(current, set())


def assert_transition(current, target):
    if not can_transition(current, target):
        raise InvalidAppealTransition(
            pgettext("appeals.service.state.error", "invalid_transition").format(current=current, target=target)
        )


__all__ = [
    "InvalidAppealTransition",
    "assert_transition",
    "can_transition",
]
