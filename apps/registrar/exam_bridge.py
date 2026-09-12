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

from django.db.models import Q

from apps.registrar import exam_eligibility as eligibility_gate
from apps.registrar import finals, gradebook, services
from apps.registrar.models import Enrollment, StudentAcademicRecord

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
    # İdmançı-tələbə istisnası BURADA da ötürülür (2026-08-31 düşmən baxışı,
    # 3-cü bloker).  Bu, statusun sadəcə göstərildiyi ekran deyil — imtahana
    # start-ı BLOKLAYAN qapıdır (``exams.journal_sync.registrar_block_reason``).
    # Ötürülmədiyi müddətdə istisna qoyulmuş tələbə kabinetdə «buraxılır»
    # görür, imtahan düyməsində isə qayıb səbəbi ilə dayandırılırdı.
    elig = services.get_exam_eligibility(
        enrollment=enrollment,
        limit_percent=limit_percent,
        exempt=finals.athlete_exemption(enrollment),
    )
    return _eligibility_payload(elig)


_UNLINKED_ELIGIBILITY = {"linked": False, "barred": False, "reason": ""}


def _eligibility_payload(elig):
    """``resolve()`` nəticəsi → ``exam_eligibility`` cavab dicti (tək və toplu yol ÜÇÜN ORTAQ)."""
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


# ── Toplu buraxılış qapısı (P1-3, 2026-09-12) ────────────────────────────────
# Tələbə imtahan siyahısı hər kart üçün ``exam_eligibility``-ni ayrıca çağırırdı
# (kart başına 5–8 sorğu: dövr, yazılış, təşkilat, qrup, qayıb həddi, istisna,
# donma).  Aşağıdakı toplu variant EYNİ qərarı səhifənin bütün fənləri üçün
# sabit sayda sorğu ilə verir.  Tək-fənn funksiyaları toxunulmaz qalır — onlar
# start/attempt axınının qapısıdır; burada yalnız «.first()» seçim qaydaları
# birə-bir güzgülənir ki, siyahı ilə start eyni cavabı versin.


def _resolve_enrollments_batch(*, student, subject_ids, organization):
    """``resolve_enrollment``-in toplu güzgüsü: ``{subject_id: Enrollment}`` (2 sorğu).

    Seçim qaydası tək variantla eynidir: cari dövrün açılışı (pk üzrə ilk),
    yoxdursa ən son dövr (``-start_date``; bərabərlikdə kiçik pk).
    """
    period = _current_period(organization)
    rows = list(
        Enrollment.objects.filter(
            student=student,
            offering__subject_id__in=list(subject_ids),
            offering__organization=organization,
            status=Enrollment.Status.ENROLLED,
        )
        .select_related("offering", "offering__period")
        .order_by("pk")
    )
    by_subject: dict = {}
    for enrollment in rows:
        by_subject.setdefault(enrollment.offering.subject_id, []).append(enrollment)

    resolved = {}
    for subject_id, candidates in by_subject.items():
        chosen = None
        if period is not None:
            chosen = next((e for e in candidates if e.offering.period_id == period.pk), None)
        if chosen is None:
            chosen = max(candidates, key=lambda e: (e.offering.period.start_date, -e.pk))
        resolved[subject_id] = chosen
    return resolved


def _absence_limit_percent_map(offerings) -> dict:
    """``gradebook.absence_limit_percent_for``-un toplu güzgüsü: ``{offering_id: limit}`` (1 sorğu).

    Tək variant açılışın (təşkilat, qrup) cütü üzrə İLK (pk) akademik qeydin
    proqram həddini götürür; qeyd yoxdursa defolt.  ``group`` NULL ola bilər —
    o halda tək variantdakı ``group=None`` → ``IS NULL`` şərti güzgülənir.
    """
    offerings = list(offerings)
    if not offerings:
        return {}
    org_ids = {o.organization_id for o in offerings}
    group_ids = {o.group_id for o in offerings if o.group_id is not None}
    group_q = Q(group_id__in=list(group_ids)) if group_ids else Q(pk__in=[])
    if any(o.group_id is None for o in offerings):
        group_q = group_q | Q(group_id__isnull=True)
    records = (
        StudentAcademicRecord.objects.filter(group_q, organization_id__in=list(org_ids))
        .select_related("program")
        .order_by("pk")
    )
    first_by_key = {}
    for record in records:
        first_by_key.setdefault((record.organization_id, record.group_id), record)
    result = {}
    for offering in offerings:
        record = first_by_key.get((offering.organization_id, offering.group_id))
        if record is not None and record.program:
            result[offering.id] = record.program.absence_limit_percent
        else:
            # Tək variantla eyni fallback (gradebook-un öz sabiti) — dəyər ayrılmasın.
            result[offering.id] = gradebook._DEFAULT_ABSENCE_LIMIT
    return result


def _athlete_exemption_map(enrollments) -> dict:
    """``finals.athlete_exemption``-un toplu güzgüsü: ``{(organization_id, student_id): bool}`` (1 sorğu).

    Tək variant (təşkilat, tələbə) üzrə İLK (pk) qeydin bayrağını qaytarır —
    burada da eyni sıra ilə ilk qeyd götürülür (``exempt_student_ids`` fərqli
    semantikadır: «hər hansı qeyddə True» — ona görə işlədilmir).
    """
    keys = {(e.organization_id, e.student_id) for e in enrollments}
    if not keys:
        return {}
    rows = (
        StudentAcademicRecord.objects.filter(
            organization_id__in=[k[0] for k in keys], student_id__in=[k[1] for k in keys]
        )
        .order_by("pk")
        .values_list("organization_id", "student_id", "national_athlete_exemption")
    )
    first_flag = {}
    for org_id, student_id, flag in rows:
        first_flag.setdefault((org_id, student_id), bool(flag))
    return {key: first_flag.get(key, False) for key in keys}


def exam_eligibility_batch(*, student, subject_ids, organization) -> dict:
    """``exam_eligibility``-nin toplu variantı: ``{subject_id: dict}``.

    Fənn sayından asılı olmayan sabit sorğu dəsti: dövr (1–2), yazılışlar (1),
    qayıb həddi (1), idmançı istisnası (1), donma (1–2), dərs saatı fallback-i
    (0–1; yalnız ``lesson_hours`` boş açılışlar üçün).  Hər fənn üçün nəticə
    tək variantla EYNİ dictdir (``_eligibility_payload``); yazılışı olmayan fənn
    → ``linked=False``.
    """
    wanted = {sid for sid in subject_ids if sid}
    result = {sid: dict(_UNLINKED_ELIGIBILITY) for sid in wanted}
    if not wanted or student is None or organization is None:
        return result
    enrollments = _resolve_enrollments_batch(student=student, subject_ids=wanted, organization=organization)
    if not enrollments:
        return result
    offerings = {e.offering_id: e.offering for e in enrollments.values()}
    limit_by_offering = _absence_limit_percent_map(offerings.values())
    exempt_by_key = _athlete_exemption_map(enrollments.values())
    hours_map = eligibility_gate.lesson_hours_map(
        [oid for oid, offering in offerings.items() if not (getattr(offering, "lesson_hours", 0) or 0)]
    )
    frozen_ids = eligibility_gate.frozen_offering_ids(list(offerings))
    for subject_id, enrollment in enrollments.items():
        elig = services.get_exam_eligibility(
            enrollment=enrollment,
            limit_percent=limit_by_offering.get(enrollment.offering_id, gradebook._DEFAULT_ABSENCE_LIMIT),
            exempt=exempt_by_key.get((enrollment.organization_id, enrollment.student_id), False),
            frozen=enrollment.offering_id in frozen_ids,
            hours_map=hours_map,
        )
        result[subject_id] = _eligibility_payload(elig)
    return result


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
