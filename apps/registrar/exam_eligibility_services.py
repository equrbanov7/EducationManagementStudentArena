"""Canonical enrollment eligibility facade, including explicit language-level rules."""

from . import exam_eligibility


def get_exam_eligibility(
    *,
    enrollment,
    limit_percent,
    exempt=False,
    resit_done=False,
    frozen=None,
    hours_map=None,
    absence_count=None,
    absence_hours=None,
):
    """Absence (qayıb) rule: a student is barred from the subject's exam when
    unexcused absence hours exceed ``limit_percent`` of the lesson hours.

    ``limit_percent`` comes from the student's program
    (``Program.absence_limit_percent``); it is tenant/program-configurable.

    ``exempt`` — rəsmi idmançı-tələbə istisnası (milli yığma;
    ``StudentAcademicRecord.national_athlete_exemption``).  ``True`` olduqda
    saatlar olduğu kimi qalır (``absence_hours`` dəyişmir, davamiyyət balı yenə
    real qayıba görə hesablanır), sadəcə ``barred`` heç vaxt qalxmır.

    ``frozen`` — ``None`` olduqda açılış üçün özü yoxlanılır
    (:func:`exam_eligibility.is_frozen`).  Toplu səthlər bunu
    :func:`exam_eligibility.frozen_offering_ids` ilə əvvəlcədən hesablayıb
    ötürməlidir (N+1-in qarşısını alır).

    ⚠️ Bu funksiya artıq yalnız **nazik sarğıdır**: qərarın özü
    :func:`apps.registrar.exam_eligibility.resolve`-dadır — sistemdə yeganə
    yerdir.  2026-08-31 auditinə qədər eyni müqayisə doqquz yerdə təkrarlanırdı;
    yeni buraxılış qaydası ARTIQ təkrarlanmamalıdır, o qapıdan keçməlidir.
    """
    from . import language_level_grading

    if language_level_grading.is_level(enrollment.offering):
        return language_level_grading.eligibility(
            enrollment,
            absence_count=absence_count,
            absence_hours=absence_hours,
            lesson_hours=exam_eligibility.lesson_hours_for(enrollment.offering, hours_map=hours_map),
            exempt=exempt,
            resit_done=resit_done,
        )
    return exam_eligibility.resolve(
        absence_hours=enrollment.absence_hours,
        # Məxrəc TƏK tərifdən (``lesson_hours`` boşdursa dərslərin saat cəmi) —
        # əvvəl bu səth xam sahəyə baxırdı, jurnal qridi isə fallback-a, yəni
        # eyni sətir iki ekranda fərqli cavab alırdı.  ``hours_map`` verilibsə
        # sorğu yaranmır (döngüdə çağıranlar onu əvvəlcədən qurur).
        lesson_hours=exam_eligibility.lesson_hours_for(enrollment.offering, hours_map=hours_map),
        limit_percent=limit_percent,
        exempt=exempt,
        resit_done=resit_done,
        frozen=exam_eligibility.is_frozen(enrollment.offering) if frozen is None else frozen,
    )
