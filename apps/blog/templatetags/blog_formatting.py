from django import template

register = template.Library()


@register.filter
def compact_number(value):
    try:
        number = int(value or 0)
    except (TypeError, ValueError):
        return "0"

    for threshold, suffix in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")):
        if number >= threshold:
            compacted = f"{number / threshold:.1f}".rstrip("0").rstrip(".")
            return f"{compacted}{suffix}"

    return str(number)
