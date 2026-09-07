"""Dövr analitikasının SÜRƏTLİ aqreqasiya yolu (2026-09 QA P2-2).

Niyə ayrıca yol var
-------------------
:func:`apps.registrar.analytics.build_period_analytics` bir semestrin BÜTÜN
yazılışlarını qiymətləndirir — rektor səviyyəsində bu, 19 643 sətirdir.  Sorğu
sayı onsuz da sabit idi (13 sorğu), amma ilk (keşsiz) açılış 3.0–3.9 s çəkirdi
və vaxtın demək olar hamısı **Python obyekt qurmağa** gedirdi (2026-09-05
profili, ``qa.rector``, kabinet səhifəsi):

* ``uuid.UUID.__init__`` 372 267 çağırış — psycopg2 hər UUID sütununu obyektə
  çevirir, sonra hər map axtarışı ``UUID.__hash__`` (435 033) + ``__eq__``
  (396 488) ödəyir;
* Django ``Model.__init__`` 91 255 çağırış — hər yazılış ``select_related``
  ilə açılış + fənn + qrup obyekti kimi materiallaşırdı;
* ``lookups.batch_process_rhs`` 0.57 s — map-lar ``id__in=[19 643 UUID]``
  siyahısı ilə çağırılırdı, hər sorğuda bütün siyahı yenidən hazırlanırdı;
* ``analytics._evaluate`` 19 643 çağırış — hər sətir üçün 18 açarlı nəticə
  dicti, ``exam_eligibility.resolve`` dicti, davamiyyət balı, status etiketləri
  və ``grading_scale.score_to_letter`` (hərf/GPA) hesablanırdı.

Panel isə həmin nəticənin YALNIZ doqquz sahəsini oxuyur (bax
:meth:`analytics._Bucket.add_row`): ``student``, ``absence_hours``,
``lesson_hours``, ``barred``, ``graded``, ``total``, ``passed``, ``failed``,
``credit``.  Hərf qiyməti, GPA, ``eligibility`` dicti, status etiketi/tooltip-i,
davamiyyət balı — heç biri panelə girmir.  Bu modul məhz o doqquz sahəni
hesablayır:

1. **Mətn açarlar.** Yazılış/tələbə/açılış birləşmə açarları SQL-də
   ``::text``-ə çevrilir (:func:`_text`), yəni psycopg2 UUID obyekti YARATMIR
   və map axtarışları sətir heşi ilə gedir.  UUID yalnız AÇILIŞ və PROQRAM
   səviyyəsində (bucket açarı, saat/donma körpüsü) qalır — 19 k əvəzinə ~2 k.
2. **Model obyekti yoxdur.** Yazılışlar ``values_list`` demətləri kimi gəzilir.
3. **Açılış-səviyyəli iş bir dəfə.** Sxem hədləri, komponent/dərs mənbəyi,
   auditoriya saatı, kredit, «donmuşdur?» bayrağı və bucket etiketləri hər
   AÇILIŞ üçün bir dəfə hesablanır (açılış sayı yazılış sayından ~13× azdır).
4. **Alt-sorğu, siyahı yox.** Map-lara id-lər ``qs.values("id")`` kimi verilir
   → Django ``IN (SELECT …)`` yazır, 19 643 elementli parametr siyahısı
   ümumiyyətlə yaranmır.
5. **Birləşdirilmiş skan.** ``ComponentScore`` iki dəfə (generic + kollokvium)
   yox, şərti ``FILTER`` ilə BİR dəfə gəzilir; dərs balı cəmi isə yalnız
   generic komponenti OLMAYAN açılışlar üçün hesablanır (nəticəsi yalnız orada
   oxunur).

⚠️ **Riyaziyyat dəyişmir.**  Aşağıdakı düstur :func:`analytics._evaluate` +
:meth:`analytics._Bucket.add` cütünün güzgüsüdür və
``tests/test_analytics_fast_path.py`` iki yolu eyni «çirkli» fikstura üzərində
müqayisə edərək kilidləyir.  Düsturun hər hansı qolu dəyişəndə HƏR İKİ yer
dəyişməlidir (test əks halda qırılır).

⚠️ Eyni playbook akademik-qeyd XÜLASƏSİ üçün ``apps.accounts.academic_summary``
modulunda tətbiq olunub (P2-19).  Oradakı köməkçilər bu modulun köməkçilərinin
əkizidir; ``apps.registrar`` ``apps.accounts``-u idxal EDƏ BİLMƏZ (modul sərhəd
qapısı), ona görə birləşdirmə yalnız əks istiqamətdə — accounts tərəfindən —
mümkündür və ayrıca işdir.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Count, DecimalField, F, Q, Sum, TextField
from django.db.models.functions import Cast, Least

from apps.registrar import analytics, exam_eligibility
from apps.registrar.models import (
    AssessmentComponent,
    AssessmentScheme,
    ComponentScore,
    CourseOffering,
    Enrollment,
    FinalGrade,
    LessonMark,
    ResitRecord,
    SelfWorkMark,
    StudentAcademicRecord,
)
from core.program_codes import program_display_code

_ZERO = Decimal("0")
_ONE = Decimal("1")
_HUNDRED = Decimal("100")
_TEN = Decimal("10")
_TEXT = TextField()

#: Sxem yoxdursa işləyən hədlər — ``analytics``-dən oxunur ki, iki yol arasında
#: sürüşmə mümkün olmasın (defolt dəyər İKİ yerdə yazılmır).
_DEFAULT_SCHEME = (
    analytics._DEFAULT_ENTRY_MAX,
    analytics._DEFAULT_PASS,
    analytics._DEFAULT_MIN_EXAM,
)
_DEFAULT_ABSENCE_LIMIT = analytics._DEFAULT_ABSENCE_LIMIT

#: Giriş balına töhfə verən komponent növləri (generic = dərs cəmini ƏVƏZ edir,
#: kollokvium = həmişə ÜSTƏGƏL) — ``analytics.build_evaluation_maps_for`` güzgüsü.
_GENERIC_KIND = "generic"
_KOLLOKVIUM_KIND = "kollokvium"
_ENTRY_KINDS = (_GENERIC_KIND, _KOLLOKVIUM_KIND)

#: Tələbə qeydi olmayan sətir üçün defolt: (qayıb həddi, istisna, proqram yoxdur).
_NO_RECORD = (_DEFAULT_ABSENCE_LIMIT, False, None, "", "")


def _text(field: str):
    """``field``-in SQL-də mətnə çevrilmiş forması — açar kimi işlədilir.

    Təmsil (defisli vs defissiz) backend-dən asılıdır, amma BÜTÜN açarlar eyni
    çevirmədən keçdiyi üçün daxilən uyğundur.  ``str(uuid)`` ilə müqayisə
    ETMƏYİN — o, sqlite-da fərqli sətir verir."""
    return Cast(field, _TEXT)


def _keyed_sum(qs, expr) -> dict:
    """``enrollment_id`` (mətn) → aqreqat — tək sorğu, UUID obyekti yaranmır."""
    rows = qs.annotate(key_text=_text("enrollment_id")).values_list("key_text").annotate(total=expr)
    return {key: total or _ZERO for key, total in rows}


# ── Yazılış-səviyyəli map-lar (``analytics.build_evaluation_maps_for`` güzgüsü) ──


def _component_sum_maps(enrollment_ids) -> tuple[dict, dict]:
    """(generic, kollokvium) cəmləri — ``analytics._capped_component_sum`` güzgüsü.

    Riyaziyyat eynidir (bal öz komponent tavanı ilə kəsilir), fərq yalnız
    sorğu sayındadır: ``analytics`` ``ComponentScore``-u İKİ dəfə gəzir, burada
    isə şərti aqreqasiya (``FILTER``) ilə bir keçiddə hər iki cəm çıxır.

    ⚠️ Cəmi ``None`` olan açar lüğətə düşmür — çağıran onu ``_ZERO`` defolt ilə
    oxuyur, yəni nəticə ``analytics``-dəki ``total or Decimal("0")`` ilə eynidir."""
    decimal_field = DecimalField(max_digits=8, decimal_places=2)
    capped = Least(F("score"), Cast(F("component__max_score"), decimal_field), output_field=decimal_field)
    rows = (
        ComponentScore.objects.filter(enrollment_id__in=enrollment_ids, component__kind__in=_ENTRY_KINDS)
        .annotate(key_text=_text("enrollment_id"))
        .values_list("key_text")
        .annotate(
            generic_total=Sum(capped, filter=Q(component__kind=_GENERIC_KIND)),
            kollokvium_total=Sum(capped, filter=Q(component__kind=_KOLLOKVIUM_KIND)),
        )
    )
    generic: dict = {}
    kollokvium: dict = {}
    for key, generic_total, kollokvium_total in rows:
        if generic_total is not None:
            generic[key] = generic_total
        if kollokvium_total is not None:
            kollokvium[key] = kollokvium_total
    return generic, kollokvium


def _selfwork_map(enrollment_ids) -> dict:
    """``analytics._selfwork_map`` güzgüsü — təhvil verilmiş iş sayı, ≤10 bal."""
    qs = SelfWorkMark.objects.filter(enrollment_id__in=enrollment_ids, done=True)
    return {key: min(Decimal(total), _TEN) for key, total in _keyed_sum(qs, Count("id")).items()}


def _lesson_sum_map(enrollment_ids, offering_ids) -> dict:
    """Dərs balı cəmi — YALNIZ generic komponenti OLMAYAN açılışlar üçün.

    ``analytics`` bunu bütün yazılışlar üçün hesablayır, amma nəticə yalnız
    ``use_components`` yanlış olan açılışlarda oxunur — komponentli açılışın
    dərs cəmi heç vaxt heç nəyə təsir etmir.  Süzgəc rəqəmləri dəyişmir, yalnız
    işi atır."""
    if not offering_ids:
        return {}
    qs = LessonMark.objects.filter(
        enrollment_id__in=enrollment_ids, score__isnull=False, enrollment__offering_id__in=offering_ids
    )
    return _keyed_sum(qs, Sum("score"))


def _exam_map(enrollment_ids) -> dict:
    rows = (
        FinalGrade.objects.filter(enrollment_id__in=enrollment_ids)
        .annotate(key_text=_text("enrollment_id"))
        .values_list("key_text", "exam_score", "bonus")
    )
    return {key: (score, bonus) for key, score, bonus in rows}


def _resit_map(enrollment_ids) -> dict:
    rows = (
        ResitRecord.objects.filter(enrollment_id__in=enrollment_ids, resit_score__isnull=False)
        .annotate(key_text=_text("enrollment_id"))
        .values_list("key_text", "resit_score")
    )
    return dict(rows)


def _record_map(organization, student_ids) -> dict:
    """``student_id`` (mətn) → (qayıb həddi %, istisna, proqram id/ad/şifr).

    ``analytics._record_map`` güzgüsü: HEÇ BİR ``is_active`` süzgəci yoxdur və
    eyni tələbənin birdən çox qeydi olsa SONUNCU qalır.  Fərq yalnız odur ki,
    burada model obyekti yox, skalyarlar oxunur; ``display_code`` isə modelin
    ``@property``-si deyil, onun altındakı saf funksiya ilə qurulur (eyni
    qayda — bax :func:`core.program_codes.program_display_code`)."""
    rows = (
        StudentAcademicRecord.objects.filter(organization=organization, student_id__in=student_ids)
        .annotate(key_text=_text("student_id"))
        .values_list(
            "key_text",
            "program__absence_limit_percent",
            "national_athlete_exemption",
            "program_id",
            "program__name",
            "program__official_code",
            "program__legacy_official_code",
        )
    )
    return {
        key: (limit, exempt, program_id, name, program_display_code(official, legacy))
        for key, limit, exempt, program_id, name, official, legacy in rows
    }


# ── Açılış-səviyyəli sabitlər (yazılış başına DEYİL, açılış başına bir dəfə) ──


def _offering_info(offering_ids) -> tuple[dict, list]:
    """``offering_id`` (mətn) → açılışın bütün sabitləri, tək demət halında.

    Demət: ``(entry_max, pass_threshold, min_exam, komponentlidir?,
    auditoriya_saatı, kredit, donmuşdur?, offering_id, group_id, qrup_adı,
    fənn_adı, fənn_şifri)``.

    ``analytics._evaluate`` bunların hamısını HƏR yazılış üçün yenidən açırdı
    (sxem axtarışı, dəst üzvlüyü, ``lesson_hours_for``, ``ects`` çevirmə), bucket
    etiketlərini isə ``select_related`` ilə gələn model obyektlərindən oxuyurdu.

    İkinci qaytarma dəyəri — dərs balı cəmi LAZIM olan açılışların id-ləri
    (generic komponenti olmayanlar); bax :func:`_lesson_sum_map`."""
    # Açılış sətirləri ƏVVƏL oxunur: əhatəsi boş olan aktorda (məs. altında
    # açılış olmayan kafedra) qalan beş sorğu ümumiyyətlə getmir — köhnə yolun
    # «yazılış yoxdursa dərhal qayıt» qısa-qapanması ilə eyni ucuzluq.
    rows = list(
        CourseOffering.objects.filter(id__in=offering_ids)
        .annotate(key_text=_text("id"))
        .values_list(
            "id",
            "key_text",
            "lesson_hours",
            "subject__ects",
            "subject__name",
            "subject__code",
            "group_id",
            "group__name",
        )
    )
    if not rows:
        return {}, []

    schemes = {
        key: (entry_max, pass_threshold, min_exam)
        for key, entry_max, pass_threshold, min_exam in AssessmentScheme.objects.filter(offering_id__in=offering_ids)
        .annotate(key_text=_text("offering_id"))
        .values_list("key_text", "entry_score_max", "pass_threshold", "min_final_exam_score")
    }
    with_components = set(
        AssessmentComponent.objects.filter(offering_id__in=offering_ids, kind=_GENERIC_KIND)
        .annotate(key_text=_text("offering_id"))
        .values_list("key_text", flat=True)
    )
    # ⚠️ Bu iki köməkçi UUID ilə açarlanır (mətn açar bilmir), ona görə açılış
    # sətirlərində həm UUID, həm mətn açar oxunur və körpü BURADA qurulur —
    # açılış sayı qədər UUID (yazılış səviyyəsində 19× çox olardı).
    hours_fallback = exam_eligibility.lesson_hours_map(offering_ids)
    frozen = exam_eligibility.frozen_offering_ids(offering_ids)

    info: dict = {}
    lesson_source_ids: list = []
    for offering_id, key, lesson_hours, ects, subject_name, subject_code, group_id, group_name in rows:
        entry_max, pass_threshold, min_exam = schemes.get(key, _DEFAULT_SCHEME)
        # ``exam_eligibility.lesson_hours_for`` güzgüsü: kanonik saat 0/None
        # olduqda açılışın bütün dərslərinin saat cəmi işlədilir.
        hours = Decimal(lesson_hours or 0)
        if hours <= 0:
            hours = Decimal(hours_fallback.get(offering_id, 0) or 0)
        use_components = key in with_components
        if not use_components:
            lesson_source_ids.append(offering_id)
        info[key] = (
            Decimal(entry_max),
            pass_threshold,
            min_exam,
            use_components,
            hours,
            int(ects or 0),
            offering_id in frozen,
            offering_id,
            group_id,
            group_name,
            subject_name,
            subject_code,
        )
    return info, lesson_source_ids


# ── Aqreqasiya ───────────────────────────────────────────────────────────────


def build_period_analytics(*, organization, period, scope_q=None) -> dict:
    """:func:`analytics.build_period_analytics`-in obyektsiz gövdəsi.

    Eyni payload-u qaytarır (``totals`` / ``programs`` / ``groups`` / ``at_risk``);
    aqreqasiya ``analytics._Bucket`` üzərində gedir ki, xülasə düsturu (keçid
    faizi, ÜOMG, qayıb faizi) TƏK yerdə qalsın."""
    enrollment_qs = Enrollment.objects.filter(organization=organization, offering__period=period)
    if scope_q is not None:
        enrollment_qs = enrollment_qs.filter(scope_q)
    flat = enrollment_qs.exclude(status=Enrollment.Status.DROPPED)

    # ⚠️ İd-lər ALT-SORĞU kimi ötürülür (siyahı kimi yox) — bax modul
    # docstring-i, 4-cü bənd.
    enrollment_ids = flat.values("id")
    info, lesson_source_ids = _offering_info(flat.values("offering_id"))
    if not info:
        # Yazılış yoxdursa açılış da yoxdur (FK NOT NULL) — köhnə yolun
        # ``if not enrollments`` qolu ilə eyni payload.
        return {"has_data": False, "period": period, "totals": None, "programs": [], "groups": [], "at_risk": []}

    component_sums, kollokvium_sums = _component_sum_maps(enrollment_ids)
    selfwork_sums = _selfwork_map(enrollment_ids)
    lesson_sums = _lesson_sum_map(enrollment_ids, lesson_source_ids)
    exams = _exam_map(enrollment_ids)
    resits = _resit_map(enrollment_ids)
    records = _record_map(organization, flat.values("student_id"))

    overall = analytics._Bucket("overall", "")
    programs: dict = {}
    groups: dict = {}
    subjects: dict = {}

    # (açılış, hədd%) → icazəli saat — ``resolve``-un arifmetikası açılış başına
    # təkrarlanmasın deyə yaddaşda saxlanılır.
    allowed_memo: dict = {}

    rows = flat.annotate(
        enrollment_text=_text("id"),
        student_text=_text("student_id"),
        offering_text=_text("offering_id"),
    ).values_list("enrollment_text", "student_text", "offering_text", "absence_hours")

    for enrollment_key, student_key, offering_key, absence_hours in rows.iterator(chunk_size=5000):
        # ``offering`` FK NOT NULL-dur və ``info`` məhz bu queryset-in
        # açılışlarından qurulub — açar həmişə var (``.get`` ilə səssizcə
        # ötürmək sətri rəqəmlərdən ITIRƏRDİ).
        (
            entry_max,
            pass_threshold,
            min_exam,
            use_components,
            lesson_hours,
            credit,
            frozen,
            offering_id,
            group_id,
            group_name,
            subject_name,
            subject_code,
        ) = info[offering_key]

        # ── Giriş balı (gradebook.entry_score_for güzgüsü) ────────────────────
        source = component_sums if use_components else lesson_sums
        raw_entry = source.get(enrollment_key, _ZERO)
        kollokvium = kollokvium_sums.get(enrollment_key)
        if kollokvium is not None:
            raw_entry += kollokvium
        selfwork = selfwork_sums.get(enrollment_key)
        if selfwork is not None:
            raw_entry += selfwork
        entry = raw_entry if raw_entry < entry_max else entry_max
        entry = entry.quantize(_ONE, rounding=ROUND_HALF_UP)  # gradebook.round_score

        # ── İmtahan / təkrar imtahan ─────────────────────────────────────────
        exam, bonus = exams.get(enrollment_key, (None, _ZERO))
        resit = resits.get(enrollment_key)
        resit_done = resit is not None
        effective = resit if resit_done else exam
        graded = effective is not None

        total = entry
        if effective is not None:
            total += effective
        if bonus:
            total += bonus
        if total < _ZERO:
            total = _ZERO
        elif total > _HUNDRED:
            total = _HUNDRED
        total = total.quantize(_ONE, rounding=ROUND_HALF_UP)

        limit, exempt, program_id, program_name, program_code = records.get(student_key, _NO_RECORD)

        # ── Buraxılış (exam_eligibility.resolve güzgüsü) ──────────────────────
        if frozen:
            # Donmuş dilimdə buraxılış qərarı HEÇ verilmir (köhnə sistemin
            # faktiki nəticəsi göstərilir) — ``resolve(frozen=True)`` güzgüsü.
            barred = False
        else:
            if limit is None:
                limit = exam_eligibility.DEFAULT_LIMIT_PERCENT
            memo_key = (offering_key, limit)
            allowed = allowed_memo.get(memo_key)
            if allowed is None:
                allowed = allowed_memo[memo_key] = lesson_hours * Decimal(limit) / _HUNDRED
            # ``hours_known`` = məxrəc yararlıdır (allowed > 0); strict ``>``.
            over_limit = allowed > 0 and (absence_hours or 0) > allowed
            barred = over_limit and not exempt and not resit_done

        exam_ok = graded and effective >= min_exam
        passed = graded and not barred and total >= pass_threshold and exam_ok
        failed = barred or (graded and not passed)
        absent = absence_hours or 0

        overall.add_row(student_key, absent, lesson_hours, barred, graded, total, passed, failed, credit)

        if program_id is not None:
            bucket = programs.get(program_id)
            if bucket is None:
                bucket = programs[program_id] = analytics._Bucket(program_id, program_name, program_code)
            bucket.add_row(student_key, absent, lesson_hours, barred, graded, total, passed, failed, credit)

        if group_id is not None:
            bucket = groups.get(group_id)
            if bucket is None:
                bucket = groups[group_id] = analytics._Bucket(group_id, group_name)
            bucket.add_row(student_key, absent, lesson_hours, barred, graded, total, passed, failed, credit)

        bucket = subjects.get(offering_id)
        if bucket is None:
            bucket = subjects[offering_id] = analytics._Bucket(offering_id, subject_name, subject_code)
        bucket.add_row(student_key, absent, lesson_hours, barred, graded, total, passed, failed, credit)

    return analytics.assemble_payload(period, overall, programs, groups, subjects)


__all__ = ["build_period_analytics"]
