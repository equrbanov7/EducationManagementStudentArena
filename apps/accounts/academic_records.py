"""Staff-facing HİERARXİK akademik-qeyd icmalı — read-only, batched aggregation.

Dekan / kafedra müdiri / rektor / registrator öz görünüş sahəsindəki (unit scope)
tələbələrin akademik nəticələrini fakültə → kafedra → ixtisas → qrup → tələbə
süzgəcləri ilə görür: hər kəs yalnız özündən BİR ALT səviyyəni (və daha aşağını)
görür (:mod:`apps.organizations.scoping`). Kiçik "box"-lar seçilmiş süzgəc üzrə
ümumi mənzərəni verir (neçə tələbə, toplanmış kredit, neçə kəsr — q/b vs 25%
ayrımı, neçə QİYMƏTLƏNDİRİLMƏYİB, orta ÜOMG).

**Qiymətləndirilməyib (2026-08).** Nə keçmiş, nə kəsilmiş yazılış — yəni nə
``FinalGrade.exam_score``, nə ``ResitRecord.resit_score`` var — əvvəllər heç bir
qutuya düşmürdü və rəqəmlər səssizcə "itirdi" (legacy köçürmə ölçüsündə 106 870
yazılışın 23 382-si). İndi :func:`_is_ungraded` onları ayrıca sayır; sayğac
mövcud tam keçidin İÇİNDƏ artırılır — YENİ SORĞU YOXDUR, səhifələmə müqaviləsi
toxunulmazdır.

**Performans müqaviləsi (2026-08 optimallaşdırması).** İcmal İKİ müstəqil işə
bölünüb, çünki onların qiyməti kökündən fərqlidir:

* :func:`build_records_page` — cədvəlin GÖRÜNƏN səhifəsi. Tələbələr **bazada**
  səhifələnir (ad üzrə sıralama), sonra yalnız həmin ~25 tələbənin enrollment-ləri
  qiymətləndirilir. Yəni qiymət səhifə ölçüsündən asılıdır, scope-un ümumi tələbə
  sayından YOX.
* :func:`build_records_summary` — box-lar. Bunlar tərifən bütün süzgəc sahəsi
  üzrə aqreqatdır, ona görə tam keçid lazımdır; amma keçid yüngülləşdirilib
  (aşağıdakı üç qayda) və UI-da AYRICA, gecikmiş sorğu ilə yüklənir ki, cədvəl
  dərhal görünsün.

Tam keçidin üç qaydası — hamısı ölçülüb (5 213 tələbə / 106 870 enrollment):

1. ``select_related("offering", "offering__subject", "offering__period")``
   İŞLƏDİLMİR. O zəncir hər enrollment üçün 4 model obyekti yaradırdı (≈428 000
   obyekt, 4.7 s). Əvəzinə enrollment-lər ``.only(...)`` ilə çəkilir, açılışlar
   isə BİR DƏFƏ kiçik lüğətə yığılıb FK-ya mənimsədilir (9 599 açılış, 0.04 s) —
   ``e.offering = obj`` mənimsətməsi FK keşini doldurur, sonrakı müraciətdə
   əlavə sorğu getmir.
2. Bulk map-lara id **queryset** verilir (siyahı yox) →
   :func:`analytics.build_evaluation_maps_for` ``IN (SELECT …)`` alt-sorğusu
   yazır; 106 870 elementli parametr siyahısı yaranmır (1.25 s → 0.33 s / map).
3. Tədris ili / semestr süzgəci Python-da deyil, **SQL-də** (``period_id__in``)
   tətbiq olunur — süzgəc seçiləndə DB-dən az sətir gəlir.

Per-enrollment riyaziyyat dəyişməyib: :func:`analytics.evaluate_enrollment` +
:func:`analytics.build_evaluation_maps_for` — yəni ``compute_final_result``
N dəfə çağırılmır və q/b vs 25% ayrımı :func:`transcript._fail_reason_code`
semantikası ilə eynidir.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Q

from apps.organizations.models import AcademicPeriod, OrgUnit
from apps.organizations.scoping import UnitScope
from apps.registrar import analytics, exam_eligibility, transcript
from apps.registrar.models import CourseOffering, Enrollment, StudentAcademicRecord

_TWO = Decimal("0.01")
DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100

#: Cədvəlin standart sıralaması — bazada edilə bilən (yəni səhifələnə bilən) ad
#: sıralaması. ``student_search`` lookup-u ilə eyni ki, axtarışdan gələn nəticə
#: cədvəldəki yerlə uyğun gəlsin.
_NAME_ORDER = ("student__last_name", "student__first_name", "student__username")

#: Sıralama seçimləri. ``name`` bazada səhifələnir (sürətli, standart);
#: ``fails`` isə tərifən bütün scope-un qiymətləndirilməsini tələb edir
#: (kəsri çox olan öndə) — ona görə açıq şəkildə seçilir və bahalıdır.
SORT_NAME = "name"
SORT_FAILS = "fails"


def _round2(value) -> Decimal:
    return Decimal(value).quantize(_TWO, rounding=ROUND_HALF_UP)


def _fail_reason(result) -> str:
    """Bir KƏSİLMİŞ nəticənin səbəb kodu — transcript._fail_reason_code güzgüsü.

    ``qb``     → davamiyyətdən (barred) imtahana buraxılmayıb → fənn yenidən keçilir.
    ``exam25`` → imtahana girib, kəsilib → 25% ilə təkrar imtahan hüququ.
    ``other``  → STRUKTUR OLARAQ ƏLÇATMAZ (2026-08 auditi).  ``analytics._evaluate``
                 ``failed = barred or (graded and not passed)`` yazır, yəni «kəsr»
                 çoxluğunda ``barred`` deyilsə mütləq ``graded and not passed``
                 olur.  Ona görə «kəsr = q/b + imtahandan 25%» eyniliyi tavtologiya
                 deyil, düsturun özündən çıxır.  Qol qəsdən saxlanılır: analitika
                 düsturu bir gün genişlənsə (məs. plagiat kəsri) susmaq əvəzinə
                 buraya düşsün.
    """
    return exam_eligibility.fail_reason_code(result)


def _is_ungraded(result) -> bool:
    """Nə keçib, nə kəsilib — YƏNİ HEÇ BİR QUTUYA DÜŞMÜR.

    Səbəb: ``analytics._evaluate``-də ``graded = effective is not None``, yəni
    nə ``FinalGrade.exam_score``, nə də ``ResitRecord.resit_score`` var.  Belə
    yazılış nə krediti sayılır, nə kəsrə düşür, nə də ÜOMG-yə girir — köçürmə
    ölçüsündə 106,870 yazılışın 23,382-si (21.9 %) məhz belədir.  Onları ayrıca
    saymasaq rəqəmlər «itir»: cəm sətir sayı ilə uyğun gəlmir.  ``barred``
    tələbə ``failed=True`` olduğuna görə BURAYA DÜŞMÜR (o, q/b kəsridir)."""

    return not result["passed"] and not result["failed"]


def _scoped_records(organization, scope: UnitScope, filters: dict):
    """StudentAcademicRecord **queryset**-i — scope alt-ağacı + aktiv süzgəclər.

    Scope: unit-scoped istifadəçi yalnız öz fakültə/kafedra alt-ağacındakı
    qruplara bağlı qeydləri görür (``group__path``); org-wide hamısını görür;
    scope yoxdursa (adi müəllim/tələbə) heç nə.

    Qəsdən queryset qaytarır (``list()`` YOX): çağıran ya bazada səhifələyir
    (:func:`build_records_page`), ya da yalnız ``student_id``-lərini alt-sorğu
    kimi ötürür (:func:`build_records_summary`) — heç birində 5 000+ sətrin
    Python-a çəkilməsinə ehtiyac yoxdur."""
    qs = StudentAcademicRecord.objects.filter(organization=organization, is_active=True).select_related(
        "student", "program", "group"
    )
    # İyerarxiya scoping — hər kəs özündən aşağını görür.
    qs = qs.filter(scope.unit_subtree_q(path_field="group__path", id_field="group_id"))

    # Ən dərin verilmiş struktur süzgəci (qrup > ixtisas > kafedra > fakültə).
    if filters.get("student"):
        qs = qs.filter(student_id=filters["student"])
    if filters.get("program"):
        qs = qs.filter(program_id=filters["program"])
    unit_id = filters.get("group") or filters.get("department") or filters.get("faculty")
    if unit_id:
        unit = OrgUnit.objects.filter(organization=organization, pk=unit_id).only("id", "path").first()
        if unit is None:
            return qs.none()
        if unit.path:
            qs = qs.filter(Q(group_id=unit.id) | Q(group__path__startswith=f"{unit.path}/"))
        else:
            qs = qs.filter(group_id=unit.id)
    return qs


# ── Dövr (tədris ili / semestr) köməkçiləri ──────────────────────────────────


def _org_periods(organization):
    """Təşkilatın bütün dövrləri — kiçik siyahı (onluqlarla), bir sorğu."""
    return list(
        AcademicPeriod.objects.filter(organization=organization).only("id", "academic_year", "start_date", "name")
    )


def _period_ids_for(organization, year, season):
    """(tədris ili, semestr) süzgəcinə uyğun dövr id-ləri; süzgəc yoxdursa ``None``.

    Süzgəci SQL-ə çevirmək üçündür: ``year_display`` Python xüsusiyyətidir
    (``format_year``), semestr isə başlanğıc ayından hesablanır — ikisi də SQL-də
    ifadə olunmur. Amma dövrlərin sayı azdır, ona görə uyğun dövr id-lərini
    əvvəlcədən tapıb enrollment-ləri ``offering__period_id__in`` ilə süzürük.
    Beləcə süzgəc seçiləndə DB-dən AZ sətir gəlir (Python-da süzmək əvəzinə)."""
    if not year and not season:
        return None
    ids = []
    for period in _org_periods(organization):
        if year and period.year_display != year:
            continue
        if season and transcript._season_of(period) != season:
            continue
        ids.append(period.id)
    return ids


def _distinct_student_ids(records):
    """Scope-dakı TƏLƏBƏ id-ləri (qeyd id-ləri yox), ad üzrə sıralı, təkrarsız.

    Bir tələbənin BİRDƏN ÇOX aktiv qeydi ola bilər — unikallıq
    ``(organization, student, program)`` üzrədir, yəni ikinci ixtisas / köçürmə
    halında eyni tələbə iki sətirlə gəlir. Cədvəl tələbə-başına bir sətir
    göstərdiyi üçün həm sayım, həm səhifələmə TƏLƏBƏ üzrə təkrarsız olmalıdır.

    ``.distinct()`` sıralama sütunlarını da SELECT-ə əlavə edir; burada bu
    TƏHLÜKƏSİZDİR, çünki həmin sütunlar (``student__last_name`` və s.) məhz
    tələbənin öz sahələridir — yəni ``student_id``-dən funksional asılıdır və
    təkrarsızlığı poza bilmir."""
    return records.order_by(*_NAME_ORDER).values_list("student_id", flat=True).distinct()


def _distinct_student_count(records) -> int:
    """Scope-dakı təkrarsız tələbə sayı (``order_by()`` sıfırlanır ki, sıralama
    sütunları DISTINCT-ə qarışmasın)."""
    return records.order_by().values("student_id").distinct().count()


def _year_options(organization) -> list:
    """Dropdown üçün tədris ili seçimləri — ən yeni öndə.

    Əvvəllər bu siyahı BÜTÜN enrollment-ləri gəzərək qurulurdu; indi birbaşa
    dövrlər cədvəlindən gəlir (onluqlarla sətir)."""
    return sorted({p.year_display for p in _org_periods(organization) if p.year_display}, reverse=True)


# ── Yüngül enrollment yükləməsi ──────────────────────────────────────────────


def _enrollment_qs(organization, student_ids, period_ids=None):
    """Qiymətləndiriləcək enrollment-lərin queryset-i (hələ icra olunmur).

    ``student_ids`` siyahı da ola bilər, queryset də — queryset veriləndə Django
    alt-sorğu yazır (nəhəng IN siyahısı yaranmır)."""
    qs = Enrollment.objects.filter(organization=organization, student_id__in=student_ids).exclude(
        status=Enrollment.Status.DROPPED
    )
    if period_ids is not None:
        qs = qs.filter(offering__period_id__in=period_ids)
    return qs


def _load_enrollments(organization, enrollment_qs):
    """Enrollment-ləri YÜNGÜL çəkir — obyekt sayı ~4× azalır.

    ``_evaluate`` enrollment-dən yalnız ``id``, ``student_id``, ``absence_hours``
    və açılışın ``id`` / ``lesson_hours`` / ``subject.ects`` sahələrini oxuyur.
    Ona görə enrollment-lər ``.only(...)`` ilə çəkilir, açılışlar isə bir dəfə
    lüğətə yığılıb FK-ya mənimsədilir: ``e.offering = obj`` FK keşini doldurur,
    yəni ``e.offering.subject.ects`` sonradan ƏLAVƏ SORĞU vermir. Obyektlər real
    Django modelidir — ``_evaluate`` üçün heç nə dəyişmir."""
    offerings = {
        o.id: o
        for o in CourseOffering.objects.filter(id__in=enrollment_qs.order_by().values("offering_id"))
        .select_related("subject")
        .only("id", "lesson_hours", "subject__ects")
    }
    enrollments = list(enrollment_qs.only("id", "student_id", "offering_id", "absence_hours"))
    for enrollment in enrollments:
        offering = offerings.get(enrollment.offering_id)
        if offering is not None:
            enrollment.offering = offering  # FK keşi — sonrakı müraciətdə sorğu yoxdur
    return enrollments


def _evaluate_all(organization, enrollment_qs):
    """(enrollment, nəticə) cütlərini verir — sabit sayda sorğu ilə.

    Map-lara id-lər **queryset** kimi ötürülür (bax modul başlığı, qayda 2)."""
    enrollments = _load_enrollments(organization, enrollment_qs)
    if not enrollments:
        return []
    flat = enrollment_qs.order_by()  # alt-sorğuda ORDER BY lazım deyil
    maps = analytics.build_evaluation_maps_for(
        organization,
        enrollment_ids=flat.values("id"),
        offering_ids=flat.values("offering_id"),
        student_ids=flat.values("student_id"),
    )
    return [(e, analytics.evaluate_enrollment(e, maps)) for e in enrollments]


# ── Aqreqasiya ───────────────────────────────────────────────────────────────


def _new_acc() -> dict:
    return {
        "credits_earned": 0,
        "fails": 0,
        "qb": 0,
        "exam25": 0,
        "ungraded": 0,
        "quality_points": Decimal("0"),
        "gpa_credits": 0,
    }


def _accumulate(acc, result) -> None:
    """Bir enrollment nəticəsini tələbənin akkumulyatoruna əlavə edir."""
    if result["passed"] or result["failed"]:
        # ÜOMG 100 bal: Σ(yekun_bal × kredit) / Σ(kredit) (transcript ilə eyni).
        acc["quality_points"] += result["total"] * result["credit"]
        acc["gpa_credits"] += result["credit"]
    if result["passed"]:
        acc["credits_earned"] += result["credit"]
    elif result["failed"]:
        acc["fails"] += 1
        reason = _fail_reason(result)
        if reason == "qb":
            acc["qb"] += 1
        elif reason == "exam25":
            acc["exam25"] += 1
    else:
        # Qiymətləndirilməyib: kəsrə QARIŞMIR, krediti sayılmır, ÜOMG-yə girmir —
        # amma artıq GÖRÜNÜR ki, imtahan mərkəzi onları hədəfli düzəldə bilsin.
        acc["ungraded"] += 1


def _per_student(organization, student_ids, period_ids) -> dict:
    """student_id → akkumulyator (yalnız verilmiş tələbələr üçün)."""
    per_student: dict = {}
    for enrollment, result in _evaluate_all(organization, _enrollment_qs(organization, student_ids, period_ids)):
        acc = per_student.get(enrollment.student_id)
        if acc is None:
            acc = per_student[enrollment.student_id] = _new_acc()
        _accumulate(acc, result)
    return per_student


def _row(record, acc) -> dict:
    """Cədvəlin bir sətri (tələbə + akkumulyator)."""
    # ⚠️ Məxrəc yoxdursa "0.00" DEYİL, BOŞ — cədvəldə "—" görünür.  231 tələbənin
    # bütün ÜOMG-daşıyan sətirləri köhnə sistemdə nəticəsizdir; sıfır yazmaq
    # «sıfır bal aldı» iddiasıdır (2026-08-31 düşmən baxışı, 1-ci bloker).
    gpa, gpa_available = exam_eligibility.uomg_from(acc["quality_points"], acc["gpa_credits"])
    student = record.student
    return {
        "student_id": str(record.student_id),
        "name": (student.get_full_name() or "").strip() or student.username,
        "username": student.username,
        "group": record.group.name if record.group_id else "—",
        # Cədvəl sətrində ad + RƏSMİ dövlət ixtisas şifri birlikdə göstərilir
        # (``display_label`` — cari şifr, yoxsa köhnə). ``program_code`` xam şifr
        # kimi, ``program_code_full`` isə hər iki nəsil kimi ayrıca qalır.
        # Daxili ``Program.code`` (``MYEDU-*``) heç birində iştirak etmir.
        "program": record.program.display_label if record.program_id else "—",
        "program_code": record.program.display_code if record.program_id else "",
        # Tooltip üçün TAM etiket — ad + HƏR İKİ nəslin şifri.
        "program_full": record.program.display_label_full if record.program_id else "",
        "credits_earned": acc["credits_earned"],
        "fails": acc["fails"],
        "qb": acc["qb"],
        "exam25": acc["exam25"],
        "ungraded": acc["ungraded"],
        "gpa": str(gpa) if gpa_available else "",
    }


def _rows_for(records, student_ids, per_student) -> list:
    """Verilmiş tələbə id-ləri üçün cədvəl sətirləri — id sırasını qoruyaraq.

    Tələbənin birdən çox aktiv qeydi olduqda ilki götürülür (cədvəl tələbə-başına
    bir sətirdir); ``_scoped_records`` artıq ``select_related`` etdiyi üçün
    qrup/ixtisas adları əlavə sorğu vermir."""
    by_student: dict = {}
    for record in records.filter(student_id__in=student_ids):
        by_student.setdefault(record.student_id, record)
    rows = []
    for sid in student_ids:
        record = by_student.get(sid)
        if record is not None:
            rows.append(_row(record, per_student.get(sid) or _new_acc()))
    return rows


def _empty_summary() -> dict:
    return {
        "students": 0,
        "credits_earned": 0,
        "fails": 0,
        "qb": 0,
        "exam25": 0,
        "ungraded": 0,
        "quality_points": Decimal("0"),
        "gpa_credits": 0,
        "avg_gpa": "",
        "avg_gpa_available": False,
    }


def _public_summary(box) -> dict:
    """Daxili akkumulyator sahələrini ataraq JSON-a hazır box qaytarır."""
    box = dict(box)
    # ⚠️ Məxrəc yoxdursa "0.00" DEYİL, boş sətir + bayraq: JS «Hesablana bilmir»
    # yazır.  Sıfır «pis nəticə» kimi oxunur (2026-08-31 düşmən baxışı, 1-ci bloker).
    value, available = exam_eligibility.uomg_from(box["quality_points"], box["gpa_credits"])
    box["avg_gpa"] = str(value) if available else ""
    box["avg_gpa_available"] = available
    del box["quality_points"], box["gpa_credits"]
    return box


def _no_access_payload() -> dict:
    return {
        "has_access": False,
        "summary": _public_summary(_empty_summary()),
        "results": [],
        "has_more": False,
        "total": 0,
        "year_options": [],
    }


# ── Public API ───────────────────────────────────────────────────────────────


def build_records_page(*, organization, scope: UnitScope, filters=None, offset=0, limit=DEFAULT_PAGE_SIZE, sort=None):
    """Cədvəlin BİR səhifəsi — scope-un ümumi ölçüsündən (demək olar) asılı deyil.

    Standart sıralamada (``sort="name"``) tələbələr **bazada** səhifələnir və
    yalnız görünən ~25 tələbənin enrollment-ləri qiymətləndirilir. ``sort="fails"``
    seçiləndə (kəsri çox olan öndə) sıralama tərifən bütün scope-u tələb edir —
    o zaman tam keçid edilir və səhifə Python-da kəsilir.
    """
    filters = filters or {}
    limit = max(1, min(int(limit or DEFAULT_PAGE_SIZE), MAX_PAGE_SIZE))
    offset = max(0, int(offset or 0))

    if not scope.has_structure_access:
        return {"has_access": False, "results": [], "has_more": False, "total": 0}

    records = _scoped_records(organization, scope, filters)
    period_ids = _period_ids_for(organization, filters.get("year"), filters.get("season"))
    total = _distinct_student_count(records)

    if sort == SORT_FAILS:
        # Bahalı yol: «kəsri çox olan öndə» sıralaması tərifən bütün scope-un
        # qiymətləndirilməsini tələb edir (kəsr sayı bazada mövcud sütun deyil).
        student_ids = list(_distinct_student_ids(records))
        per_student = _per_student(organization, student_ids, period_ids)
        rows = _rows_for(records, student_ids, per_student)
        rows.sort(key=lambda r: (-r["fails"], r["name"].lower()))
        return {
            "has_access": True,
            "results": rows[offset : offset + limit],
            "has_more": offset + limit < total,
            "total": total,
        }

    # Sürətli yol: səhifə BAZADA kəsilir, sonra yalnız onun tələbələri hesablanır.
    student_ids = list(_distinct_student_ids(records)[offset : offset + limit])
    if not student_ids:
        return {"has_access": True, "results": [], "has_more": False, "total": total}
    per_student = _per_student(organization, student_ids, period_ids)
    return {
        "has_access": True,
        "results": _rows_for(records, student_ids, per_student),
        "has_more": offset + limit < total,
        "total": total,
    }


def build_records_summary(*, organization, scope: UnitScope, filters=None):
    """Xülasə box-ları + tədris ili seçimləri — bütün süzgəc sahəsi üzrə.

    Bu, tərifən tam keçiddir (box-lar səhifəyə görə dəyişmir), ona görə UI-da
    cədvəldən AYRICA, gecikmiş sorğu ilə yüklənir — cədvəl gözləmir."""
    filters = filters or {}
    if not scope.has_structure_access:
        return {"has_access": False, "summary": _public_summary(_empty_summary()), "year_options": []}

    # Org-səviyyəli aktor üçün 7 800 tələbənin bütün yazılışları qiymətləndirilir
    # (7.8–9.5 s, QA 2026-09-05 P2-19). Box-lar səhifəyə görə dəyişmir → qısa TTL keş;
    # açar aktorun əhatəsi + süzgəclərdir, istifadəçi adı deyil (eyni əhatə eyni rəqəm).
    from django.core.cache import cache

    cache_key = _summary_cache_key(organization, scope, filters)
    cached = cache.get(cache_key) if cache_key else None
    if cached is not None:
        return cached

    records = _scoped_records(organization, scope, filters)
    period_ids = _period_ids_for(organization, filters.get("year"), filters.get("season"))

    box = _empty_summary()
    box["students"] = _distinct_student_count(records)
    for _enrollment, result in _evaluate_all(
        organization, _enrollment_qs(organization, records.order_by().values("student_id"), period_ids)
    ):
        _accumulate(box, result)
    payload = {
        "has_access": True,
        "summary": _public_summary(box),
        "year_options": _year_options(organization),
    }
    if cache_key:
        cache.set(cache_key, payload, SUMMARY_CACHE_TTL)
    return payload


#: Xülasə box-larının keş müddəti (saniyə) — bal yazıları bir neçə dəqiqə gecikə bilər.
SUMMARY_CACHE_TTL = 300


def _summary_cache_key(organization, scope, filters) -> str:
    import hashlib
    import json

    try:
        raw = json.dumps(
            {
                "org": str(getattr(organization, "pk", "")),
                "scope": [scope.scope_type, sorted(str(u) for u in (scope.unit_ids or ()))],
                "filters": {k: str(v) for k, v in sorted((filters or {}).items()) if v},
            },
            sort_keys=True,
        )
    except (TypeError, ValueError):
        return ""
    return "academic_records:summary:" + hashlib.sha1(raw.encode("utf-8")).hexdigest()


def build_records_overview(
    *, organization, scope: UnitScope, filters=None, offset=0, limit=DEFAULT_PAGE_SIZE, sort=None
):
    """Səhifə + box-ları BİRLİKDƏ qaytaran uyğunluq sarğısı.

    UI artıq ikisini ayrı-ayrı çağırır (cədvəl dərhal, box-lar gecikmiş); bu
    funksiya isə tək çağırışla tam mənzərə istəyən yerlər (testlər, ixrac,
    skriptlər) üçün saxlanılıb — qiyməti tam keçid qədərdir."""
    filters = filters or {}
    if not scope.has_structure_access:
        return _no_access_payload()
    page = build_records_page(
        organization=organization, scope=scope, filters=filters, offset=offset, limit=limit, sort=sort
    )
    summary = build_records_summary(organization=organization, scope=scope, filters=filters)
    return {
        "has_access": True,
        "summary": summary["summary"],
        "results": page["results"],
        "has_more": page["has_more"],
        "total": page["total"],
        "year_options": summary["year_options"],
    }


def student_is_in_scope(*, organization, scope: UnitScope, student_id) -> bool:
    """Verilmiş tələbə istifadəçinin görünüş sahəsindədirmi (drill-down mühafizəsi)."""
    if not scope.has_structure_access:
        return False
    qs = StudentAcademicRecord.objects.filter(organization=organization, is_active=True, student_id=student_id)
    qs = qs.filter(scope.unit_subtree_q(path_field="group__path", id_field="group_id"))
    return qs.exists()
