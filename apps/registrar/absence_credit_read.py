"""Qayıb güzəştlərinin toplu oxusu; hesablanan saat sıfırdan aşağı düşmür."""

from django.db.models import Sum

from .models import AbsenceCredit


def credit_hours_map(enrollment_ids):
    return dict(
        AbsenceCredit.objects.filter(enrollment_id__in=enrollment_ids, reverses__isnull=True, reversed_by__isnull=True)
        .values("enrollment_id")
        .annotate(total=Sum("hours"))
        .values_list("enrollment_id", "total")
    )


def effective_hours(raw_hours, credit_hours):
    return max(0, int(raw_hours) - int(credit_hours or 0))
