"""Academic transfer extension point; registrar owns enrollment/journal writes.

Registered at AppConfig.ready(). Missing integration fails closed before any
transfer write. The organization UI retains tenant, scope and reason checks.
"""

from django.core.exceptions import ValidationError

_handler = None


def register_student_transfer(handler):
    if not callable(handler):
        raise TypeError("Student transfer handler must be callable")
    global _handler
    _handler = handler


def transfer_student_group(*, record, new_group, period, by_user, reason):
    if _handler is None:
        raise ValidationError("Tələbə köçürmə xidməti qoşulmayıb.")
    return _handler(record=record, new_group=new_group, period=period, by_user=by_user, reason=reason)
