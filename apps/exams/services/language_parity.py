"""Dil variantı parity yoxlaması (audit EXAM-P1-17).

Çoxdilli imtahanda hər aktiv dil variantı student-ə eyni "çətinlik/həcm"
təqdim etməlidir: eyni aktiv sual sayı və eyni ümumi bal. Əks halda bir dildə
imtahan verən tələbə digərinə nisbətən üstün/aşağı vəziyyətdə olur. Bu modul
publish-dən əvvəl çağırıla bilən saf validator təqdim edir (DB dəyişikliyi
yoxdur) — nəticə problemlərin siyahısıdır; boş siyahı = parity var.
"""

from django.utils.translation import pgettext


def _variant_totals(variant):
    """(aktiv sual sayı, ümumi bal) — bu dil variantı üçün."""
    questions = list(variant.questions.filter(is_active=True).only("points"))
    total_points = sum(int(getattr(q, "points", 0) or 0) for q in questions)
    return len(questions), total_points


def check_language_variant_parity(exam):
    """Aktiv dil variantları arasında parity pozuntularının siyahısını qaytarır.

    Yalnız 2+ aktiv variant olduqda mənalıdır; tək variant həmişə parity-dir.
    Referans kimi ilk (ən kiçik language/id) aktiv variant götürülür.
    """
    variants = list(exam.language_variants.filter(is_active=True).order_by("language", "id"))
    if len(variants) < 2:
        return []

    reference = variants[0]
    ref_count, ref_points = _variant_totals(reference)
    ref_label = reference.display_name or reference.get_language_display()

    issues = []
    for variant in variants[1:]:
        count, points = _variant_totals(variant)
        label = variant.display_name or variant.get_language_display()
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


def language_variants_in_parity(exam):
    """Qısayol: parity varsa True."""
    return not check_language_variant_parity(exam)


__all__ = ["check_language_variant_parity", "language_variants_in_parity"]
