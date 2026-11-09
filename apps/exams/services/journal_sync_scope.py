"""Jurnal nəticələrinin rəqabət sərhədi: tələbənin faktiki qeydiyyatı.

Bağlı açılış + fallback seçimi registrar yazıçısı ilə eyni resolver-dən gəlir.
Fənn adı/id-si təkbaşına semestrlər arasında eyni qiymət xanası demək deyil.
"""

from __future__ import annotations


def target_identity(attempt):
    from apps.registrar.public import resolve_exam_result_target

    exam = attempt.exam
    return resolve_exam_result_target(
        student=attempt.user,
        subject_id=exam.subject_id,
        organization=exam.organization,
        offering_ids=[offering.pk for offering in exam.journal_offerings.all()],
        attempt=attempt if exam.exam_type_extended == "final" else None,
    )


def target_key(attempt):
    """Toplu bərpada ayrı semestr/açılışları bir cəhdə endirmə.

    Qeydiyyatı həll olunmayan imtahanları bir-birinə görə itirmə: onların
    görünən no_enrollment statusu sinxronizasiya qatında saxlanır.
    """
    identity = target_identity(attempt)
    return (
        attempt.exam.organization_id,
        attempt.user_id,
        attempt.exam.subject_id,
        identity,
        None if identity is not None else attempt.exam_id,
    )


def has_same_target(attempt, candidates) -> bool:
    """Sonrakı namizədlərdən hər hansı biri məhz eyni jurnal xanasına yazılırmı."""
    candidates = iter(candidates)
    first = next(candidates, None)
    if first is None:
        return False
    identity = target_identity(attempt)
    if identity is None:
        return False
    if target_identity(first) == identity:
        return True
    return any(target_identity(candidate) == identity for candidate in candidates)
