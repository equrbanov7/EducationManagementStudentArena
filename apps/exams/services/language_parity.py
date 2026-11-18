"""Dil variantı parity yoxlaması (audit EXAM-P1-17) — sahib 2026-11-19 qərarı ilə LƏĞV edilib.

Əvvəl çoxdilli imtahanda hər aktiv variant eyni aktiv sual sayına və eyni ümumi bala malik olmalı idi, əks halda
imtahan aktiv edilmirdi.  Sahib: «2 dildə fərqli sual sayı ola bilər, yenə imtahanı aktivləşdirmək olmalıdır»;
sualsız (boş) variant isə heç sayılmamalıdır.  API (``check_language_variant_parity`` / ``language_parity_error_message``)
çağıranlar üçün saxlanılır və həmişə boş nəticə qaytarır.
"""

from django.utils.translation import pgettext


def variant_stats(variant_ids):
    """``{variant_id: (aktiv sual sayı, ümumi bal, min bal, maks bal)}`` — BİR sorğu."""
    from django.db.models import Count, Max, Min, Sum

    from apps.exams.models import ExamQuestion

    if not variant_ids:
        return {}
    rows = (
        ExamQuestion.objects.filter(language_variant_id__in=list(variant_ids), is_active=True)
        .values("language_variant_id")
        .annotate(cnt=Count("id"), total=Sum("points"), low=Min("points"), high=Max("points"))
    )
    return {
        row["language_variant_id"]: (row["cnt"], row["total"] or 0, row["low"] or 0, row["high"] or 0) for row in rows
    }


def parity_issues(exam, variants, stats):
    """Saf qayda (sorğusuz) — ``check_language_variant_parity`` və siyahı batch-i EYNİ funksiyanı işlədir.

    Sahib 2026-11-19: dil variantlarında sual sayı və bal FƏRQLİ ola bilər — imtahan yenə aktiv edilir və başladılır
    (köhnə «eyni say / eyni bal» qaydası ləğv edildi). Sualsız variant tələbəyə onsuz da göstərilmir
    (``language_variants.build_language_options``), ona görə heç bir variant fərqi aktivləşdirməni bağlamır.
    """
    return []


def check_language_variant_parity(exam):
    """Aktiv dil variantları arasında parity pozuntularının siyahısını qaytarır (bax :func:`parity_issues`).

    Yalnız 2+ aktiv variant olduqda mənalıdır; tək variant həmişə parity-dir.
    Referans kimi ilk (ən kiçik language/id) aktiv variant götürülür.
    """
    variants = list(exam.language_variants.filter(is_active=True).order_by("language", "id"))
    if len(variants) < 2:
        return []
    return parity_issues(exam, variants, variant_stats([variant.id for variant in variants]))


def language_variants_in_parity(exam):
    """Qısayol: parity varsa True."""
    return not check_language_variant_parity(exam)


def language_parity_error_message(exam):
    """Activation/start UX üçün lokallaşdırılmış ilk parity xətası."""
    issues = check_language_variant_parity(exam)
    if not issues:
        return ""
    return pgettext(
        "exams.service.language_parity",
        "Dil variantları eyni aktiv sual sayına və ümumi bala malik olmalıdır: {issue}",
    ).format(issue=issues[0])


__all__ = [
    "check_language_variant_parity",
    "language_parity_error_message",
    "language_variants_in_parity",
    "parity_issues",
    "variant_stats",
]
