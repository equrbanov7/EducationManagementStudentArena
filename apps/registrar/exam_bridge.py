"""İmtahan mərkəzi ↔ elektron jurnal körpüsü.

Rəqəmsal imtahanın nəticəsi (``ExamAttempt``) avtomatik registrar
``FinalGrade``-ə yazılır — əl ilə köçürmə (keçdi/kəsildi səhvi riski) aradan
qalxır. İki istiqamət:

* **Buraxılış qapısı** — tələbə qayıba görə imtahandan kəsilibsə (``barred``),
  imtahana start bloklanır və səbəb göstərilir.
* **Nəticə yazımı** — imtahan bitəndə xam faiz (0–100) fənnin imtahan
  şkalasına (``exam_score_max``, adətən 50, TAM ədəd) çevrilir və
  ``finals.set_exam_score`` ilə yazılır. İmtahandan qovulan (``expelled``)
  tələbəyə 0 → avtomatik F. Jurnalın semestr-sonu kilidi bu yazını dayandırmır
  (imtahan kiliddən SONRA keçir — bax ``finals.set_exam_score`` şərhi).

Bu modul exams tərəfindən ``apps.registrar.public`` fasadı vasitəsilə çağırılır
(model səviyyəsində birbaşa asılılıq yaranmır).
"""

from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal

from apps.registrar import finals, gradebook, services
from apps.registrar.models import Enrollment

logger = logging.getLogger(__name__)


def _current_period(organization):
    from django.apps import apps as django_apps

    AcademicPeriod = django_apps.get_model("organizations", "AcademicPeriod")
    return (
        AcademicPeriod.objects.filter(organization=organization, is_current=True).first()
        or AcademicPeriod.objects.filter(organization=organization).order_by("-start_date").first()
    )


def resolve_enrollment(*, student, subject_id, organization):
    """Tələbənin bu fənn üzrə aktiv qeydiyyatını tap (cari semestr üstünlüklə).

    İmtahan bir fənnə bağlı olmaya bilər (``subject`` null) — o halda ``None``
    (körpü sadəcə no-op olur, mövcud davranış pozulmur)."""
    if not subject_id or student is None:
        return None
    base = Enrollment.objects.filter(
        student=student,
        offering__subject_id=subject_id,
        offering__organization=organization,
        status=Enrollment.Status.ENROLLED,
    ).select_related("offering", "offering__period")
    period = _current_period(organization)
    if period is not None:
        match = base.filter(offering__period=period).first()
        if match is not None:
            return match
    # Cari semestr uyğunluğu yoxdursa — ən son açılış.
    return base.order_by("-offering__period__start_date").first()


def exam_eligibility(*, student, subject_id, organization):
    """İmtahana buraxılış statusu → dict.

    ``{"linked": bool, "barred": bool, "reason": str, "absence_hours", ...}``.
    ``linked=False`` → imtahan jurnal fənninə bağlı deyil (qapı tətbiq olunmur).
    """
    enrollment = resolve_enrollment(student=student, subject_id=subject_id, organization=organization)
    if enrollment is None:
        return {"linked": False, "barred": False, "reason": ""}
    limit_percent = gradebook.absence_limit_percent_for(enrollment.offering)
    elig = services.get_exam_eligibility(enrollment=enrollment, limit_percent=limit_percent)
    from django.utils.translation import pgettext

    reason = ""
    if elig["barred"]:
        reason = pgettext(
            "registrar.exam_bridge",
            "You are not admitted to the exam: %(hours)s absence hours exceed the %(limit)s%% limit for this subject.",
        ) % {"hours": elig["absence_hours"], "limit": elig["limit_percent"]}
    return {
        "linked": True,
        "barred": bool(elig["barred"]),
        "reason": reason,
        "absence_hours": elig["absence_hours"],
        "allowed_hours": elig["allowed_hours"],
        "limit_percent": elig["limit_percent"],
    }


def _to_exam_scale(percent, scheme) -> int:
    """Xam faiz (0–100) → fənnin imtahan şkalası (0..exam_score_max), TAM ədəd."""
    cap = finals.exam_score_max(scheme)  # adətən 50
    try:
        pct = Decimal(str(percent or 0))
    except (TypeError, ValueError):
        pct = Decimal("0")
    pct = max(Decimal("0"), min(Decimal("100"), pct))
    scaled = (pct * Decimal(cap) / Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(scaled)


def _actor_can_write(organization, user):
    """PG ``registrar_guard_same_org_actor`` triggerinin Python güzgüsü.

    ``FinalGrade.entered_by`` yalnız təşkilatın AKTİV üzvü (və ya sahibi /
    superuser) ola bilər — əks halda INSERT trigger səviyyəsində düşür və
    best-effort körpü bütün jurnal yazısını itirir. Uyğun olmayan aktoru
    NULL-a (sistem) endiririk ki, bal hər halda jurnala düşsün."""
    from django.apps import apps as django_apps

    user_id = getattr(user, "pk", None)
    if user_id is None or not getattr(user, "is_active", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    if getattr(organization, "owner_id", None) == user_id:
        return True
    Membership = django_apps.get_model("organizations", "Membership")
    return Membership.objects.filter(
        user_id=user_id,
        organization=organization,
        is_active=True,
        role__organization=organization,
        role__is_active=True,
    ).exists()


def record_exam_result(*, student, subject_id, organization, score_percent, is_expelled=False, by_user=None):
    """İmtahan nəticəsini jurnala yaz (``FinalGrade.exam_score``).

    ``score_percent`` — 0–100 xam faiz. ``is_expelled`` (proctordan qovulma) →
    0 bal (avtomatik F). Fənn qeydiyyatı tapılmasa no-op (``None``).

    JURNAL KİLİDİ (sahibin qərarı, 2026-08): imtahan jurnal bağlandıqdan SONRA
    keçir, ona görə kilidli jurnal imtahan nəticəsinin yazılmasını BLOKLAMIR.
    Əvvəl bu funksiya kilidi görüb no-op edir və nəticəni WARNING ilə itirirdi;
    indi ``finals.set_exam_score`` çıxış balını hər halda yazır (giriş balı —
    jurnal xanaları — kilidli qalır).

    ``by_user`` — yoxlayan müəllim / reviewer; ``None`` = avtomatik (sistem)
    yazı, audit izində belə də işarələnir (2026-08 auditi, G7).
    Nəticə: yazılan ``FinalGrade`` və ya ``None``.
    """
    enrollment = resolve_enrollment(student=student, subject_id=subject_id, organization=organization)
    if enrollment is None:
        return None
    if by_user is not None and not _actor_can_write(organization, by_user):
        logger.warning(
            "exam_bridge: actor %s cannot write for organization %s — falling back to system actor",
            getattr(by_user, "pk", "?"),
            getattr(organization, "pk", "?"),
        )
        by_user = None
    scheme = gradebook.ensure_assessment_scheme(offering=enrollment.offering)
    exam_score = 0 if is_expelled else _to_exam_scale(score_percent, scheme)
    note = "imtahan mərkəzi" if by_user is not None else "imtahan mərkəzi · avtomatik"
    return finals.set_exam_score(enrollment=enrollment, score=exam_score, by_user=by_user, source_note=note)


def exam_result_summary(*, student, subject_id, organization):
    """Tələbə nəticə səhifəsi üçün: giriş+imtahan cəmi, hərf qiyməti (A–F).

    ``{"linked": bool, "entry_score", "exam_score", "total", "letter", "gpa",
    "passed", "barred"}``; ``linked=False`` → imtahan jurnala bağlı deyil.
    """
    enrollment = resolve_enrollment(student=student, subject_id=subject_id, organization=organization)
    if enrollment is None:
        return {"linked": False}
    result = finals.compute_final_result(enrollment=enrollment, organization=organization)
    return {
        "linked": True,
        "entry_score": result["entry_score"],
        "exam_score": result["effective_exam"],
        "total": result["total"],
        "letter": result["letter"],
        "gpa": result["gpa"],
        "passed": result["passed"],
        "failed": result["failed"],
        "barred": result["barred"],
        "graded": result["graded"],
    }
