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

from django.db import transaction

from apps.registrar import absence_limit
from apps.registrar import exam_eligibility as eligibility_gate
from apps.registrar import finals, gradebook, services
from apps.registrar.models import Enrollment, StudentAcademicRecord

logger = logging.getLogger(__name__)


def _current_period(organization):
    """İmtahan körpüsünün dövrü: ``is_current`` → yoxdursa BAŞLAMIŞ ən son dövr → yoxdursa ən son dövr.

    2026-10-26 (sahib: «nəticə doğru jurnala düşsün»): əvvəlki ehtiyat yol ``-start_date`` üzrə İLK dövrü
    götürürdü — gələcək semestr (prod: «Yaz 2027», 8k ``enrolled`` sətir) cari kimi seçilə bilirdi."""
    from django.apps import apps as django_apps
    from django.utils import timezone

    AcademicPeriod = django_apps.get_model("organizations", "AcademicPeriod")
    periods = AcademicPeriod.objects.filter(organization=organization)
    return (
        periods.filter(is_current=True).first()
        or periods.filter(start_date__lte=timezone.localdate()).order_by("-start_date").first()
        or periods.order_by("-start_date").first()
    )


def _linked_key(value) -> str:
    return str(value)


def pick_enrollment(candidates, linked_offering_ids=()):
    """Bir neçə namizəd qeydiyyatdan BİRİNİ seç (yekun + midterm körpüsünün ORTAQ qaydası).

    Sıra (sahib 2026-10-26: «təkrar fənn varsa göstərməsin» — nəticə təsadüfi jurnala düşməsin):

    1. imtahanın AÇIQ bağlandığı jurnal (``Exam.journal_offerings``);
    2. tələbənin ÖZ qrupunun qeydiyyatı (``source_group IS NULL`` — alt qrupdan əlavə olunmuş deyil);
    3. ən son yaradılmış qeydiyyat (bərabərlikdə ``pk`` — deterministik).

    Birdən çox namizəd varsa WARNING loglanır (monitorinq: eyni fənn iki jurnalda)."""
    candidates = list(candidates or ())
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    linked = {_linked_key(value) for value in linked_offering_ids or ()}

    def _rank(enrollment):
        return (
            _linked_key(enrollment.offering_id) in linked,
            enrollment.source_group_id is None,
            enrollment.created_at.timestamp() if enrollment.created_at else 0.0,
            _linked_key(enrollment.pk),
        )

    chosen = max(candidates, key=_rank)
    logger.warning(
        "exam_bridge: student %s has %s enrollments for subject %s — chose %s (offering %s)",
        chosen.student_id,
        len(candidates),
        getattr(chosen.offering, "subject_id", "?"),
        chosen.pk,
        chosen.offering_id,
    )
    return chosen


def choose_enrollment(candidates, period, linked_offering_ids=()):
    """Namizədlərdən (bir tələbə + bir fənn) körpünün qeydiyyatı — tək və toplu yolun ORTAQ qərarı.

    Cari dövrün qeydiyyatı varsa ondan (``pick_enrollment``); yoxdursa YALNIZ keçmiş dövrlər (cari dövrdən
    ƏVVƏL başlamış; cari dövr yoxdursa bu gün və ya daha əvvəl başlamış), ən son başlamış dövr — gələcək
    semestrin qeydiyyatı HEÇ VAXT seçilmir."""
    candidates = list(candidates or ())
    if not candidates:
        return None
    if period is not None:
        current = [e for e in candidates if e.offering.period_id == period.pk]
        if current:
            return pick_enrollment(current, linked_offering_ids)
        past = [e for e in candidates if e.offering.period.start_date < period.start_date]
    else:
        from django.utils import timezone

        today = timezone.localdate()
        past = [e for e in candidates if e.offering.period.start_date <= today]
    if not past:
        return None
    latest = max(e.offering.period.start_date for e in past)
    return pick_enrollment([e for e in past if e.offering.period.start_date == latest], linked_offering_ids)


def linked_enrollment(student, organization, offering_ids):
    """Tələbənin imtahanın bağlı jurnallarından birindəki aktiv qeydiyyatı (yoxdursa ``None``)."""
    if not offering_ids or student is None:
        return None
    candidates = Enrollment.objects.filter(
        student=student,
        offering_id__in=list(offering_ids),
        offering__organization=organization,
        status=Enrollment.Status.ENROLLED,
    ).select_related("offering", "offering__period")
    return pick_enrollment(candidates, offering_ids)


def resolve_enrollment(*, student, subject_id, organization, offering_ids=()):
    """Tələbənin bu fənn üzrə aktiv qeydiyyatını tap.

    ``offering_ids`` — imtahanın AÇIQ bağlandığı jurnallar (``Exam.journal_offerings``, 2026-10-24): tələbə
    onlardan birində qeydiyyatdadırsa o qaytarılır; yoxdursa fənn üzrə qeydiyyat (``choose_enrollment``:
    cari dövr, sonra yalnız keçmiş dövrlər).

    İmtahan bir fənnə bağlı olmaya bilər (``subject`` null) — o halda ``None``
    (körpü sadəcə no-op olur, mövcud davranış pozulmur)."""
    if not subject_id or student is None:
        return None
    linked = linked_enrollment(student, organization, offering_ids)
    if linked is not None:
        return linked
    candidates = Enrollment.objects.filter(
        student=student,
        offering__subject_id=subject_id,
        offering__organization=organization,
        status=Enrollment.Status.ENROLLED,
    ).select_related("offering", "offering__period")
    return choose_enrollment(candidates, _current_period(organization), offering_ids)


def exam_eligibility(*, student, subject_id, organization):
    """İmtahana buraxılış statusu → dict.

    ``{"linked": bool, "barred": bool, "reason": str, "absence_hours", ...}``.
    ``linked=False`` → imtahan jurnal fənninə bağlı deyil (qapı tətbiq olunmur).
    """
    enrollment = resolve_enrollment(student=student, subject_id=subject_id, organization=organization)
    if enrollment is None:
        return {"linked": False, "barred": False, "reason": ""}
    # F-06 (2026-09-13): hədd tələbənin ÖZ proqramından — kabinetlə EYNİ mənbə
    # (əvvəl açılış qrupunun ilk qeydi idi; qonaq tələbədə qapı ≠ kabinet).
    limit_percent = absence_limit.limit_percent_for_enrollment(enrollment)
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

    Seçim qaydası tək variantla eynidir (``choose_enrollment``): cari dövr, yoxdursa yalnız keçmiş dövrlər.
    """
    period = _current_period(organization)
    rows = list(
        Enrollment.objects.filter(
            student=student,
            offering__subject_id__in=list(subject_ids),
            offering__organization=organization,
            status=Enrollment.Status.ENROLLED,
        ).select_related("offering", "offering__period")
    )
    by_subject: dict = {}
    for enrollment in rows:
        by_subject.setdefault(enrollment.offering.subject_id, []).append(enrollment)

    resolved = {}
    for subject_id, candidates in by_subject.items():
        chosen = choose_enrollment(candidates, period)
        if chosen is not None:
            resolved[subject_id] = chosen
    return resolved


def _absence_limit_percent_map(offerings, *, student=None, organization=None) -> dict:
    """``absence_limit.limit_percent_for_enrollment``-in toplu güzgüsü: ``{offering_id: limit}`` (1 sorğu).

    F-06 (2026-09-13): əvvəl açılışın (təşkilat, qrup) cütü üzrə İLK akademik
    qeydin proqram həddi götürülürdü (qapı ≠ kabinet).  Toplu yol TƏK tələbə
    üçündür, ona görə hədd tələbənin öz qeydindən bir dəfə oxunur və hər
    açılışa eyni dəyər verilir — tək variantla (``exam_eligibility``) birə-bir.
    """
    offerings = list(offerings)
    if not offerings:
        return {}
    limit = absence_limit.limit_percent_for_student(
        organization_id=getattr(organization, "pk", None), student_id=getattr(student, "pk", None)
    )
    return {offering.id: limit for offering in offerings}


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
    limit_by_offering = _absence_limit_percent_map(offerings.values(), student=student, organization=organization)
    exempt_by_key = _athlete_exemption_map(enrollments.values())
    hours_map = eligibility_gate.lesson_hours_map(
        [oid for oid, offering in offerings.items() if not (getattr(offering, "lesson_hours", 0) or 0)]
    )
    frozen_ids = eligibility_gate.frozen_offering_ids(list(offerings))
    for subject_id, enrollment in enrollments.items():
        elig = services.get_exam_eligibility(
            enrollment=enrollment,
            limit_percent=limit_by_offering.get(enrollment.offering_id, eligibility_gate.DEFAULT_LIMIT_PERCENT),
            exempt=exempt_by_key.get((enrollment.organization_id, enrollment.student_id), False),
            frozen=enrollment.offering_id in frozen_ids,
            hours_map=hours_map,
        )
        result[subject_id] = _eligibility_payload(elig)
    return result


def _to_exam_scale(percent, scheme) -> int:
    """Xam faiz (0–100) → fənnin imtahan şkalası (0..exam_score_max), TAM ədəd."""
    return scale_percent(percent, finals.exam_score_max(scheme))  # tavan adətən 50


def scale_percent(percent, cap) -> int:
    """Xam faiz (0–100) → ``0..cap`` TAM bal, ROUND_HALF_UP — yekun və midterm körpüsünün ORTAQ qaydası."""
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


#: ``_retake_attempt_result`` — «bu 25% cəhdi deyil» (adi yola davam et). ``None`` isə «25% cəhdidir, işləndi».
_NOT_RETAKE = object()


def _retake_attempt_result(
    *, student, subject_id, organization, attempt, score_percent, is_expelled, by_user, appeal_id
):
    """25% cəhdidirsə nəticəni müraciətə yaz və ``ResitRecord``-u qaytar; deyilsə ``_NOT_RETAKE``.

    Review 2026-10-19 HIGH-1: müraciət bağlanıbsa («İmtahana gəlmədi» / rədd / geri götürmə) cəhd yenə 25%
    cəhdidir — bal HEÇ YERƏ yazılmır (nə müraciətə, nə ``FinalGrade.exam_score``-a), xəbərdarlıq loglanır,
    nəticə ``None`` (işlənmiş no-op)."""
    if attempt is None:
        return _NOT_RETAKE
    from apps.registrar import retake_results

    application = retake_results.application_for_attempt(
        student=student, subject_id=subject_id, organization=organization, attempt=attempt
    )
    if application is None:
        return _NOT_RETAKE
    if application.status not in retake_results.RESULT_ACCEPTING:
        logger.warning(
            "exam_bridge: attempt %s belongs to closed retake application %s (%s) — score not recorded",
            getattr(attempt, "pk", "?"),
            application.pk,
            application.status,
        )
        return None
    if by_user is not None and not _actor_can_write(organization, by_user):
        by_user = None
    scheme = gradebook.ensure_assessment_scheme(offering=application.enrollment.offering)
    score = 0 if is_expelled else _to_exam_scale(score_percent, scheme)
    application = retake_results.record_attempt_result(
        application=application, score=score, attempt=attempt, by_user=by_user, appeal_id=appeal_id
    )
    return application.resit_record


def record_exam_result(
    *,
    student,
    subject_id,
    organization,
    score_percent,
    is_expelled=False,
    by_user=None,
    appeal_id=None,
    attempt=None,
    offering_ids=None,
):
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

    ``attempt`` (2026-10-18, 25% müraciəti): cəhd «İmtahan şansı ver» (səbəb «25% müraciəti») qeydindən
    SONRA başlayıbsa bu, 25% cəhdidir — bal ``FinalGrade.exam_score``-a (əsas imtahanın balı) YAZILMIR,
    ``retake_results.record_attempt_result`` ilə ``ResitRecord``-a + müraciətə yazılır (ilk yazı, təkrar
    yoxlama və apellyasiya — hamısı bu yolla). Nəticə: ``ResitRecord``.

    ``offering_ids`` (2026-10-26) — imtahanın AÇIQ bağlandığı jurnallar (``Exam.journal_offerings``), midterm
    körpüsü ilə EYNİ qayda: tələbə onlardan birindədirsə bal ORAYA yazılır. Statusu da lazım olan çağıran
    (``exams.journal_sync`` — ``no_enrollment`` sayğacı) :func:`record_final_result` işlədir.
    """
    return record_final_result(
        student=student,
        subject_id=subject_id,
        organization=organization,
        score_percent=score_percent,
        is_expelled=is_expelled,
        by_user=by_user,
        appeal_id=appeal_id,
        attempt=attempt,
        offering_ids=offering_ids,
    )[1]


#: ``record_final_result`` statusları.
FINAL_WRITTEN = "written"
FINAL_NO_ENROLLMENT = "no_enrollment"
FINAL_RETAKE = "retake"
FINAL_RETAKE_CLOSED = "retake_closed"


def record_final_result(
    *,
    student,
    subject_id,
    organization,
    score_percent,
    is_expelled=False,
    by_user=None,
    appeal_id=None,
    attempt=None,
    offering_ids=None,
):
    """:func:`record_exam_result` + status → ``(status, FinalGrade | ResitRecord | None)``.

    ``no_enrollment`` — tələbənin bu fənn üzrə qeydiyyatı (bağlı jurnalda da) yoxdur: bal HEÇ YERƏ yazılmadı
    (əvvəl bu hal səssiz ``None`` idi — exams tərəfi indi onu sayğac + WARNING ilə görünən edir)."""
    retake = _retake_attempt_result(
        student=student,
        subject_id=subject_id,
        organization=organization,
        attempt=attempt,
        score_percent=score_percent,
        is_expelled=is_expelled,
        by_user=by_user,
        appeal_id=appeal_id,
    )
    if retake is not _NOT_RETAKE:
        return (FINAL_RETAKE if retake is not None else FINAL_RETAKE_CLOSED), retake
    enrollment = resolve_enrollment(
        student=student, subject_id=subject_id, organization=organization, offering_ids=offering_ids
    )
    if enrollment is None:
        return FINAL_NO_ENROLLMENT, None
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
    if appeal_id is None:
        grade = finals.set_exam_score(enrollment=enrollment, score=exam_score, by_user=by_user, source_note=note)
        return FINAL_WRITTEN, grade
    # Audit 2026-09-28 EXA-03: apellyasiya qərarı balı dəyişirsə ledger-də «apellyasiya» sətri.
    from apps.registrar.exam_score_entry import record_appeal_score_change
    from apps.registrar.models import FinalGrade

    with transaction.atomic():
        previous = FinalGrade.objects.filter(enrollment=enrollment).values_list("exam_score", flat=True).first()
        grade = finals.set_exam_score(enrollment=enrollment, score=exam_score, by_user=by_user, source_note=note)
        if grade is not None:
            record_appeal_score_change(
                enrollment=enrollment,
                old_score=previous,
                new_score=grade.exam_score,
                by_user=by_user,
                appeal_id=appeal_id,
            )
    return FINAL_WRITTEN, grade


def exam_result_summary(*, student, subject_id, organization, offering_ids=()):
    """Tələbə nəticə səhifəsi üçün: giriş+imtahan cəmi, hərf qiyməti (A–F).

    ``{"linked": bool, "entry_score", "exam_score", "total", "letter", "gpa",
    "passed", "barred"}``; ``linked=False`` → imtahan jurnala bağlı deyil.
    ``offering_ids`` — imtahanın bağlı jurnalları (körpü ilə EYNİ qeydiyyat göstərilsin).
    """
    enrollment = resolve_enrollment(
        student=student, subject_id=subject_id, organization=organization, offering_ids=offering_ids
    )
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
        # Paket A (2026-10-18): nəticə səhifəsinin bal bölgüsü (davamiyyət · aktivlik · midterm) —
        # ``compute_final_result``-un artıq hesabladığı hissələr; köhnə (kollokvium) dövrdə ``None``.
        "entry_parts": result.get("entry_parts"),
    }
