"""Dil variantı parity yoxlaması (audit EXAM-P1-17).

Çoxdilli imtahanda hər aktiv dil variantı student-ə eyni "çətinlik/həcm"
təqdim etməlidir: eyni aktiv sual sayı və eyni ümumi bal — fonddan təsadüfi seçimdə isə (hər tələbəyə N
eyni ballı sual) eyni N və hər fond ≥ N (2026-10-26). Əks halda bir dildə
imtahan verən tələbə digərinə nisbətən üstün/aşağı vəziyyətdə olur. Bu modul
publish-dən əvvəl çağırıla bilən saf validator təqdim edir (DB dəyişikliyi
yoxdur) — nəticə problemlərin siyahısıdır; boş siyahı = parity var.
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


def _per_attempt_count(exam, variant) -> int:
    """Hər tələbəyə veriləcək sual sayı (0 = fondun hamısı) — ``effective_needed_count_for_attempt`` qaydası."""
    override = getattr(variant, "question_count_override", None)
    if override:
        return int(override)
    try:
        return max(0, int(getattr(exam, "random_question_count", 0) or 0))
    except (TypeError, ValueError):
        return 0


def _label(variant):
    return variant.display_name or variant.get_language_display()


def _sample_mode_issues(exam, variants, stats):
    """Fonddan TƏSADÜFİ seçim (hər dildə hər tələbəyə N sual, bütün suallar eyni bal): fondların ölçüsü fərqli
    ola bilər (sahib 2026-10-26: «dəyişiklik olmuş olsun, başladanda problem verməsin»). ``None`` — bu rejim deyil."""
    counts = {variant.id: _per_attempt_count(exam, variant) for variant in variants}
    if any(value <= 0 for value in counts.values()):
        return None
    points = set()
    for variant in variants:
        _cnt, _total, low, high = stats.get(variant.id, (0, 0, 0, 0))
        if low != high:
            return None
        points.add(low)
    if len(points) != 1:
        return None
    # Fond N-dən böyük deyilsə tələbə fondun HAMISINI alır (``effective_random_question_count`` min(N, fond)) —
    # onda fondlar özü bərabər olmalıdır (köhnə qayda).
    if any(stats.get(variant.id, (0, 0, 0, 0))[0] <= counts[variant.id] for variant in variants):
        return None
    issues = []
    reference = variants[0]
    for variant in variants:
        if variant is not reference and counts[variant.id] != counts[reference.id]:
            issues.append(
                pgettext(
                    "exams.service.language_parity",
                    "'{lang}' variantında hər tələbəyə {count} sual verilir, '{ref}' variantında isə {ref_count}.",
                ).format(
                    lang=_label(variant),
                    count=counts[variant.id],
                    ref=_label(reference),
                    ref_count=counts[reference.id],
                )
            )
    return issues


def parity_issues(exam, variants, stats):
    """Saf qayda (sorğusuz) — ``check_language_variant_parity`` və siyahı batch-i EYNİ funksiyanı işlədir.

    * Təsadüfi seçim rejimi (hər fond N-dən böyük, bütün suallar eyni bal): fond ölçüsü fərqli ola bilər — N bütün
      dillərdə eyni olmalıdır (tələbələr eyni sayda, eyni ballı sual alır).
    * Əks halda (bütün suallar verilir və ya ballar fərqlidir): eyni aktiv sual sayı və eyni ümumi bal.
    """
    if len(variants) < 2:
        return []
    sampled = _sample_mode_issues(exam, variants, stats)
    if sampled is not None:
        return sampled
    reference = variants[0]
    ref_count, ref_points = stats.get(reference.id, (0, 0, 0, 0))[:2]
    ref_label = _label(reference)
    issues = []
    for variant in variants[1:]:
        count, points = stats.get(variant.id, (0, 0, 0, 0))[:2]
        label = _label(variant)
        if count != ref_count:
            issues.append(
                pgettext(
                    "exams.service.language_parity",
                    "'{lang}' variantında {count} aktiv sual var, '{ref}' variantında isə {ref_count}.",
                ).format(lang=label, count=count, ref=ref_label, ref_count=ref_count)
            )
        if points != ref_points:
            issues.append(
                pgettext(
                    "exams.service.language_parity",
                    "'{lang}' variantının ümumi balı {points}, '{ref}' variantınınkı isə {ref_points}.",
                ).format(lang=label, points=points, ref=ref_label, ref_points=ref_points)
            )
    return issues


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
