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


def transfer_student_group(*, record, new_group, period, by_user, reason, **options):
    """``options`` dəyişmədən ötürülür (məs. ``keep_parent_journal=True`` — «ana qrupu alt qruplara böl»)."""
    if _handler is None:
        raise ValidationError("Tələbə köçürmə xidməti qoşulmayıb.")
    return _handler(record=record, new_group=new_group, period=period, by_user=by_user, reason=reason, **options)


# Sahib 2026-11-18: «əcnəbi tələbə 2 qrupda ola bilər» — ƏLAVƏ üzvlük (öz qrupu qalır). Registrar həm
# yazını (qrupun cari jurnallarına əlavə), həm də oxunu (çekmecədəki «Əlavə üzvlər») təmin edir.
_extra_handler = None
_extra_reader = None


def register_student_extra_group(handler, reader):
    if not callable(handler) or not callable(reader):
        raise TypeError("Student extra-group handlers must be callable")
    global _extra_handler, _extra_reader
    _extra_handler, _extra_reader = handler, reader


def add_student_extra_group(*, record, group, period, by_user, reason):
    if _extra_handler is None:
        raise ValidationError("Əlavə qrup xidməti qoşulmayıb.")
    return _extra_handler(record=record, group=group, period=period, by_user=by_user, reason=reason)


def extra_group_members(*, organization, group, period):
    """Oxu: qrupun cari jurnallarındakı başqa-qrup tələbələri (xidmət yoxdursa boş — çekmecə sınmasın)."""
    if _extra_reader is None:
        return []
    return _extra_reader(organization=organization, group=group, period=period)


# Sahib 2026-11-25: «Qrupdan çıxar» — tələbə qrupsuz qalır (status dəyişmir); əlavə üzv isə yalnız bu qrupun
# cari jurnallarından çıxır. Registrar həm rəsmi sübutlu çıxarmanı, həm əlavənin tərsini təmin edir.
_removal_handler = None
_extra_removal_handler = None


def register_student_group_removal(handler, extra_handler):
    if not callable(handler) or not callable(extra_handler):
        raise TypeError("Student group-removal handlers must be callable")
    global _removal_handler, _extra_removal_handler
    _removal_handler, _extra_removal_handler = handler, extra_handler


def remove_student_from_group(*, record, period, by_user, reason, order_number="", order_date=None):
    if _removal_handler is None:
        raise ValidationError("Qrupdan çıxarma xidməti qoşulmayıb.")
    return _removal_handler(
        record=record, period=period, by_user=by_user, reason=reason, order_number=order_number, order_date=order_date
    )


def remove_extra_group_member(*, record, group, period, by_user, reason):
    if _extra_removal_handler is None:
        raise ValidationError("Əlavə qrup xidməti qoşulmayıb.")
    return _extra_removal_handler(record=record, group=group, period=period, by_user=by_user, reason=reason)
