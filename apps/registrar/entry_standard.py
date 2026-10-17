"""İmtahana qədər bal (giriş balı, /50) — sillabus STANDARTI, 2026/2027-dən (Midterm rejimi).

SAHİBİN QƏRARI (2026-09-25)
---------------------------
Tələbə kabineti strukturu çoxdan belə sənədləşdirir: «Davamiyyət 10 + Sərbəst iş 10 + Cari
qiymətləndirmə 30 + Yekun imtahan 50 = 100; Giriş balı = davamiyyət + sərbəst iş + cari
qiymətləndirmə».  Kod isə davamiyyəti giriş balına QATMIRDI (GENERIC komponentlər və ya
seminar/lab dərs ballarının CƏMİ + kollokvium/midterm + sərbəst iş).  Sahib hesablamanın
standarta uyğunlaşdırılmasını YALNIZ Midterm rejimli dövrlər üçün təsdiqlədi (tədris ili
≥ 2026/2027 — :mod:`apps.registrar.interim_assessment`).  Keçmiş dövrlər (kollokvium rejimi,
köçürülmüş/arxiv) OLDUĞU KİMİ qalır — hər rəqəm bayt-bayt eyni
(``gradebook_components.entry_score_for``-un köhnə qolu; sübut
``tests/test_entry_standard_parity.py`` — keçiddən əvvəlki kod üzərində çəkilmiş snapshot).

DÜSTUR (Midterm rejimi) — TƏK yer :func:`compose`
------------------------------------------------
* **Davamiyyət (0–10)** — kanonik :func:`apps.registrar.attendance.attendance_score`, buraxılış
  qərarının EYNİ məxrəci (``exam_eligibility.lesson_hours_for``) və tələbənin ÖZ həddi
  (``absence_limit``) ilə, idmançı istisnası ötürülür.  Buraxılmayan tələbə (hədd keçilib,
  istisna yoxdur) → **0**.  Hədd deqenerativdirsə (≤ 0 %) qərar verilmir — ``exam_eligibility
  .resolve`` ilə eyni.  Plan saatı da, dərs də yoxdursa kanonik funksiya 10.00 verir (cəza yox).
  Təkrar imtahan və donma giriş balını DƏYİŞMİR — giriş balı semestrin rəqəmidir.
* **Aktivlik (0–10)** — seminar/lab dərs ballarının ƏDƏDİ ORTASI.  Dərs balı 0–10 tam ədəddir
  (``gradebook.LESSON_SCORE_MAX``) və yalnız seminar/lab dərsinə yazılır
  (``gradebook.lesson_allows_score``) — orta birbaşa 10-luq şkaladadır, miqyaslama yoxdur.
  Balsız dərslər sayılmır; heç bal yoxdursa 0.  2 onluğa yarım-yuxarı.  Sahib 2026-10-10: fəndə
  seminar VƏ laboratoriya varsa 5 + 5 (hər növün ortasının yarısı) — qayda :mod:`apps.registrar.activity_kinds`.
* **Midterm (0–30)** — KOLLOKVIUM növlü «Midterm» komponentinin balı (öz tavanı ilə).  Bu
  dövrdə balı olan köhnə «Kollokvium N» qalığı varsa (``interim_components``) o da cəmə düşür,
  hissə ``academic_rules.midterm_max()`` ilə kəsilir (sərbəst iş açıqdırsa 20, sahib 2026-10-10).
* **Sərbəst iş (0–10)** — :mod:`apps.registrar.selfwork_points` cəmi (≤ 10); köhnə qayda kimi
  YALNIZ SELF_WORK komponenti olan jurnalda (canlı yazı yolları komponenti həmişə yaradır) VƏ yalnız
  RİM «Sistem tənzimləmələri»ndə sərbəst iş AÇIQDIRSA (sahib 2026-10-10: ləğv olunub, defolt söndürülü;
  açılanda midterm yenidən 20 olur — cəm 50 qalır).
* GENERIC komponentlər (köhnə çəkili sxem / köçürmə qalığı) bu rejimdə giriş balına DAXİL
  DEYİL — standartın dörd hissəsi var (2026-09-25 prod nüsxəsi: 2026/2027 açılışlarında 0).
* **Giriş balı** = ``round_score(min(cəm, entry_score_max))`` — tam ədəd, yarım-yuxarı.

Rejim + davamiyyət girişləri :class:`EntryRule`-dadır.  Rejim açılışın dövründən çıxır
(:func:`offering_is_midterm`) — dövr/təşkilat keşdədirsə SORĞUSUZ; toplu yollar
(``finals_batch``) onu komponent sorğusunun özündən oxuyur (:func:`midterm_flags`), yəni
sorğu büdcələri dəyişmir.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from functools import partial
from types import SimpleNamespace

from apps.registrar import activity_kinds, attendance, exam_eligibility, interim_assessment
from core import academic_rules

ZERO = Decimal("0")

#: Hissələrin tavanları (sərbəst iş açıqdırsa 10 + 10 + 20 + 10, söndürülübsə 10 + 10 + 30 = 50).
ATTENDANCE_MAX = attendance.MAX_SCORE
ACTIVITY_MAX = activity_kinds.ACTIVITY_MAX  # = gradebook.LESSON_SCORE_MAX (test ilə kilidlənib)
#: Sərbəst iş AÇIQ olanda midterm tavanı; cari tavan — :func:`midterm_max` (``core.academic_rules``).
MIDTERM_MAX = Decimal(interim_assessment.MIDTERM_MAX)
SELFWORK_MAX = Decimal("10")  # = selfwork_points.TOTAL_MAX (test ilə kilidlənib)
STANDARD_TOTAL = ATTENDANCE_MAX + ACTIVITY_MAX + MIDTERM_MAX + SELFWORK_MAX

#: Açılış nümunəsində rejim memo-su (sorğu-daxili; ``exam_eligibility.is_frozen`` nümunəsi).
_MODE_ATTR = "_ems_entry_midterm"

_KOLLOKVIUM = "kollokvium"
_SELF_WORK = "self_work"


@dataclass(frozen=True)
class RuleFlags:
    """Yeni qaydanın RİM bayraqları (``core.academic_rules``) — toplu yollarda BİR DƏFƏ oxunur, sətir başına yox."""

    selfwork: bool
    midterm_max: Decimal
    activity_split: bool


def rule_flags() -> RuleFlags:
    return RuleFlags(
        selfwork=academic_rules.selfwork_enabled(),
        midterm_max=Decimal(academic_rules.midterm_max()),
        activity_split=academic_rules.activity_split(),
    )


def midterm_max() -> Decimal:
    """Midterm hissəsinin cari tavanı: sərbəst iş söndürülübsə 30, açıqdırsa 20 (sahib 2026-10-10)."""
    return Decimal(academic_rules.midterm_max())


@dataclass(frozen=True)
class EntryRule:
    """Giriş balının hesab qaydası: rejim + (Midterm-də) davamiyyət girişləri.

    ``lesson_hours`` / ``limit_percent`` / ``exempt`` — buraxılış qərarının İŞLƏTDİYİ dəyərlər;
    ``None`` olanı tək-sətir yolunda oxunur (:func:`attendance_inputs`).  ``activity_bits`` — açılışın
    seminar/lab növ maskası (:mod:`apps.registrar.activity_kinds`; ədəd və ya tənbəl çağırış, ``None`` —
    lazım olanda oxunur); ``flags`` — toplu dəstin bir dəfə oxuduğu RİM bayraqları (``None`` — indi oxunur)."""

    midterm: bool
    lesson_hours: Decimal | None = None
    limit_percent: int | None = None
    exempt: bool | None = None
    activity_bits: object = None
    flags: RuleFlags | None = None


#: Keçmiş dövrlər (kollokvium rejimi) — köhnə qayda.
LEGACY = EntryRule(midterm=False)


@dataclass(frozen=True)
class EntryParts:
    """Midterm rejimində giriş balının hissələri + yekun (UI və parite testləri üçün).

    ``midterm_max`` / ``selfwork_active`` — hesabın İŞLƏTDİYİ qayda (şablonlar «/30», «Sərbəst iş» nişanını
    buradan oxuyur); ``activity_detail`` — seminar/lab bölgüsü (yalnız görünüş, müqayisəyə girmir)."""

    attendance: Decimal
    activity: Decimal
    midterm: Decimal
    selfwork: Decimal
    total: Decimal
    #: Davamiyyət həddi keçilib (istisnasız) → davamiyyət hissəsi 0.
    attendance_barred: bool = False
    midterm_max: Decimal = MIDTERM_MAX
    selfwork_active: bool = True
    activity_detail: activity_kinds.ActivityDetail | None = field(default=None, compare=False)
    #: Hissələrin cəmi tavanı (``cap``) keçib — yekun tavanla kəsilib (yuvarlaqlaşdırma deyil; yalnız görünüş).
    capped: bool = field(default=False, compare=False)

    @property
    def raw_sum(self) -> Decimal:
        return self.attendance + self.activity + self.midterm + self.selfwork

    @property
    def rounded_from(self) -> Decimal | None:
        """QA-1 P3 (2026-10-17): hissələrin kəsirli cəmi yekundan fərqlidirsə o cəm, əks halda ``None``.

        Yekun ``total`` qayda ilə tam ədəddir (``round_score``, yarım-yuxarı: 9,55 → 10); şablon bal bölgüsündə
        «Cəm 9,55 → 10» sətrini göstərir ki, başlıqdakı bal ilə hissələr ziddiyyətli görünməsin. Cəm tavanı
        keçibsə (``capped``) bu yuvarlaqlaşdırma deyil, kəsmədir — sətir göstərilmir."""
        raw = self.raw_sum
        return None if self.capped or raw == self.total else raw

    @property
    def attendance_max(self) -> Decimal:
        return ATTENDANCE_MAX

    @property
    def activity_max(self) -> Decimal:
        return ACTIVITY_MAX

    @property
    def selfwork_max(self) -> Decimal:
        return SELFWORK_MAX


# ── Hissələr (saf funksiyalar) ───────────────────────────────────────────────


def _dec(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value or 0))


def attendance_part(*, lesson_hours, absence_hours, limit_percent, exempt) -> tuple[Decimal, bool]:
    """``(bal, buraxılmır?)`` — kanonik davamiyyət balı; buraxılmayan tələbədə bal 0."""
    percent = exam_eligibility.DEFAULT_LIMIT_PERCENT if limit_percent is None else limit_percent
    # Hədd ≤ 0 % deqenerativdir — resolver kimi buraxılış qərarı VERİLMİR, bal hesablanır.
    score, barred = attendance.attendance_score(
        lesson_hours, absence_hours, limit_percent=percent, exempt=bool(exempt) or _dec(percent) <= 0
    )
    return (ZERO if score is None else score), bool(barred)


def activity_part(score_sum, score_count) -> Decimal:
    """Bütün balı olan dərslərin BİRGƏ ortası (0–10, 2 onluq, yarım-yuxarı); bal yoxdursa 0.

    5 + 5 bölgüsü (seminar + laboratoriya) :func:`apps.registrar.activity_kinds.activity`-dədir."""
    return activity_kinds.pooled_mean(score_sum, score_count)


def midterm_part(interim_total, cap=None) -> Decimal:
    """Midterm (+ balı olan köhnə kollokvium qalığı) cəmi, cari tavanla (30 / 20) kəsilmiş."""
    return min(_dec(interim_total), midterm_max() if cap is None else _dec(cap))


def selfwork_part(points, *, counted: bool, active: bool | None = None) -> Decimal:
    """Sərbəst iş (≤ 10) — SELF_WORK komponenti olan jurnalda VƏ sərbəst iş RİM-də açıq olanda sayılır.

    Bu funksiya yalnız yeni qayda (Midterm) dövrlərinin hesabındadır; köhnə dövrlərdə sərbəst iş həmişə
    sayılır (``gradebook_components.entry_score_for``-un köhnə qolu)."""
    if active is None:
        active = academic_rules.selfwork_enabled()
    return min(_dec(points), SELFWORK_MAX) if counted and active else ZERO


def compose(
    *, attendance_score, activity, midterm, selfwork, cap, attendance_barred=False, activity_detail=None, flags=None
) -> EntryParts:
    """Hissələr → :class:`EntryParts` (cəm ``cap`` ilə kəsilir, ``round_score`` ilə tam ədəd)."""
    # Dövri idxal: ``gradebook_components`` bu modulu idxal edir.
    from apps.registrar.gradebook_components import round_score

    flags = flags or rule_flags()
    raw = attendance_score + activity + midterm + selfwork
    return EntryParts(
        attendance=attendance_score,
        activity=activity,
        midterm=midterm,
        selfwork=selfwork,
        total=round_score(min(raw, _dec(cap))),
        capped=raw > _dec(cap),
        attendance_barred=attendance_barred,
        midterm_max=flags.midterm_max,
        selfwork_active=flags.selfwork,
        activity_detail=activity_detail or activity_kinds.ActivityDetail(activity),
    )


def compose_from_totals(
    *,
    cap,
    lesson_hours,
    absence_hours,
    limit_percent,
    exempt,
    interim_total,
    selfwork_points,
    selfwork_counted,
    score_sum=ZERO,
    score_count=0,
    lesson_totals=None,
    activity_bits=None,
    flags=None,
) -> EntryParts:
    """Aqreqat dəyərlərdən (SQL güzgüləri: ``analytics``, ``analytics_fast``, ``academic_summary``)
    — :func:`parts_for` ilə EYNİ düstur, yalnız giriş formasıdır.

    ``lesson_totals`` (:class:`activity_kinds.LessonTotals`) verilməsə yalnız birgə cəm/say (``score_sum`` /
    ``score_count``) bilinir — 5 + 5 bölgüsü üçün növ cəmləri və açılışın ``activity_bits`` maskası lazımdır."""
    flags = flags or rule_flags()
    att, barred = attendance_part(
        lesson_hours=lesson_hours, absence_hours=absence_hours, limit_percent=limit_percent, exempt=exempt
    )
    totals = lesson_totals if lesson_totals is not None else activity_kinds.LessonTotals(score_sum, score_count)
    detail = activity_kinds.activity(totals, activity_bits, split_enabled=flags.activity_split)
    return compose(
        attendance_score=att,
        activity=detail.value,
        midterm=midterm_part(interim_total, flags.midterm_max),
        selfwork=selfwork_part(selfwork_points, counted=selfwork_counted, active=flags.selfwork),
        cap=cap,
        attendance_barred=barred,
        activity_detail=detail,
        flags=flags,
    )


# ── Sətir (enrollment) yolu ──────────────────────────────────────────────────


def attendance_inputs(enrollment, rule: EntryRule) -> tuple:
    """``(saat, hədd %, istisna)`` — qaydada yoxdursa TƏK-SƏTİR yolu ilə oxunur (hər biri ≤ 1 sorğu)."""
    hours = rule.lesson_hours
    if hours is None:
        hours = exam_eligibility.lesson_hours_for(enrollment.offering)
    limit = rule.limit_percent
    if limit is None:
        from apps.registrar import absence_limit

        limit = absence_limit.limit_percent_for_enrollment(enrollment)
    exempt = rule.exempt
    if exempt is None:
        from apps.registrar import finals  # dövri idxal: finals → gradebook → bu modul

        exempt = finals.athlete_exemption(enrollment)
    return hours, limit, exempt


def parts_for(enrollment, cap, *, rule, components, marks=None, component_scores=None, selfwork_points=None):
    """Bir yazılışın Midterm hissələri — ``gradebook_components.entry_score_for`` ilə EYNİ girişlər.

    ``components`` məcburidir (çağıran onsuz da oxuyur); ``marks`` / ``component_scores`` /
    ``selfwork_points`` verilməsə köhnə qolun sorğuları ilə eyni şəkildə oxunur.  ``marks`` dərs növünü
    daşımalıdır (annotasiya və ya keşlənmiş ``lesson`` — :func:`activity_kinds.mark_kind`).  Açılışın
    seminar/lab maskası qaydada yoxdursa bal sorğusunun ÖZÜNƏ qatılır (əlavə sorğu yoxdur)."""
    from apps.registrar import selfwork_points as selfwork_rules
    from apps.registrar.models import ComponentScore

    flags = rule.flags or rule_flags()
    interim = {c.id: _dec(c.max_score) for c in components if c.kind == _KOLLOKVIUM}
    interim_total = ZERO
    if interim:
        if component_scores is None:
            component_scores = ComponentScore.objects.filter(component_id__in=list(interim), enrollment=enrollment)
        interim_total = sum(
            (min(cs.score or ZERO, interim[cs.component_id]) for cs in component_scores if cs.component_id in interim),
            ZERO,
        )
    offering = _cached(enrollment, "offering")
    bits = rule.activity_bits if rule.activity_bits is not None else activity_kinds.known_bits(offering)
    if marks is None:
        marks = _own_scored_marks(enrollment, with_bits=flags.activity_split and bits is None)
        if bits is None:
            bits = activity_kinds.known_bits(offering, marks)
    if bits is None:  # yalnız tələbənin balları TƏK növdə olanda oxunur (activity_kinds.activity)
        bits = partial(_offering_bits, enrollment)
    totals = activity_kinds.totals_from_marks(marks, need_kinds=flags.activity_split)
    counted = flags.selfwork and any(c.kind == _SELF_WORK for c in components)
    if counted and selfwork_points is None:
        selfwork_points = selfwork_rules.selfwork_total_for(enrollment)
    hours, limit, exempt = attendance_inputs(enrollment, rule)
    return compose_from_totals(
        cap=cap,
        lesson_hours=hours,
        absence_hours=enrollment.absence_hours,
        limit_percent=limit,
        exempt=exempt,
        lesson_totals=totals,
        activity_bits=bits,
        interim_total=interim_total,
        selfwork_points=selfwork_points or ZERO,
        selfwork_counted=counted,
        flags=flags,
    )


def _own_scored_marks(enrollment, *, with_bits):
    """Yazılışın balı olan işarələri + dərs növü (+ lazım olsa açılışın növ maskası) — TƏK sorğu."""
    from apps.registrar.models import LessonMark

    marks = activity_kinds.annotate_kind(LessonMark.objects.filter(enrollment=enrollment, score__isnull=False))
    if with_bits:
        marks = marks.annotate(**{activity_kinds.BITS_ATTR: activity_kinds.bits_expression("lesson__offering__")})
    return list(marks)


def _offering_bits(enrollment) -> int:
    return activity_kinds.bits_for_offering(enrollment.offering)


# ── Rejim (keşdən / toplu, əlavə sorğusuz) ───────────────────────────────────


def _org_stub(from_year_raw):
    """Xam ``settings["registrar"]["midterm_from_year"]`` → ``interim_assessment`` qəbul edən obyekt.

    Qayda (ədəd yoxlaması, 2000–2100 həddi) TƏK yerdə qalsın deyə saf dəyər
    ``interim_assessment.midterm_from_year``-dan keçirilir."""
    return SimpleNamespace(settings={"registrar": {"midterm_from_year": from_year_raw}})


def is_midterm_fields(academic_year, start_date, *, organization=None, from_year_raw=None) -> bool:
    """Dövr SAHƏLƏRİNDƏN rejim (SQL güzgüləri) — ``interim_assessment.mode_for_period`` ilə eyni qayda."""
    period = SimpleNamespace(academic_year=academic_year or "", start_date=start_date)
    org = organization if organization is not None else _org_stub(from_year_raw)
    return interim_assessment.mode_for_period(period, org) == interim_assessment.MODE_MIDTERM


def _cached(instance, name):
    state = getattr(instance, "_state", None)
    return state.fields_cache.get(name) if state is not None else None


def _known_organizations(offerings, organization, period) -> dict:
    """Artıq yaddaşda olan təşkilat nümunələri (id → obyekt) — işarə + açılış/dövr FK keşləri."""
    candidates = [organization, _cached(period, "organization")]
    for offering in offerings:
        candidates.append(_cached(offering, "organization"))
        candidates.append(_cached(_cached(offering, "period"), "organization"))
    return {org.id: org for org in candidates if org is not None and getattr(org, "id", None) is not None}


def midterm_flags(offerings, *, organization=None, period=None, carried=None) -> dict:
    """``offering_id → Midterm rejimidir?`` — məlum məlumatdan, çatışmayanlar üçün TƏK sorğu.

    Mənbələr (sırayla): açılışın memo-su; keşlənmiş (və ya çağıranın ``period`` işarəsi ilə
    eyni id-li) dövr + yaddaşdakı təşkilat; ``carried`` — ``{offering_id: (tədris ili,
    başlanğıc, xam midterm_from_year)}`` (``finals_batch`` komponent sorğusunun özündən oxuyur).
    Heç biri yoxdursa açılışlar üçün bir ``values_list`` sorğusu.  Nəticə hər açılış nümunəsinə
    memo kimi yazılır."""
    offerings = [offering for offering in offerings if offering is not None]
    orgs = _known_organizations(offerings, organization, period)
    result: dict = {}
    missing: dict = {}
    for offering in offerings:
        memo = getattr(offering, _MODE_ATTR, None)
        if memo is None:
            memo = result.get(offering.id)
        if memo is None:
            memo = _resolve_known(offering, orgs=orgs, period=period, carried=carried)
        if memo is None:
            missing.setdefault(offering.id, []).append(offering)
            continue
        setattr(offering, _MODE_ATTR, memo)
        result[offering.id] = memo
    if missing:
        from apps.registrar.models import CourseOffering

        rows = CourseOffering.objects.filter(id__in=list(missing)).values_list(
            "id", "period__academic_year", "period__start_date", "organization__settings__registrar__midterm_from_year"
        )
        for offering_id, academic_year, start_date, from_year_raw in rows:
            flag = is_midterm_fields(academic_year, start_date, from_year_raw=from_year_raw)
            result[offering_id] = flag
            for offering in missing[offering_id]:
                setattr(offering, _MODE_ATTR, flag)
    return result


def period_is_midterm(period, organization=None) -> bool:
    """Bütöv dövr üçün rejim (dövr analitikası — bütün yazılışlar eyni dövrdədir), sorğusuz."""
    return interim_assessment.mode_for_period(period, organization) == interim_assessment.MODE_MIDTERM


def midterm_offering_ids(offering_ids) -> frozenset:
    """Midterm rejimli açılışların id-ləri — TƏK sorğu (id-lər siyahı və ya ``qs.values("id")``).

    Açılış obyekti olmayan toplu yollar üçün (``analytics.build_evaluation_maps_for``-un id
    variantı): dövr sahələri + təşkilatın ``midterm_from_year`` açarı bir ``values_list``-dən."""
    from apps.registrar.models import CourseOffering

    if isinstance(offering_ids, (list, tuple, set, frozenset)):
        offering_ids = [oid for oid in offering_ids if oid is not None]
        if not offering_ids:
            return frozenset()
    rows = CourseOffering.objects.filter(id__in=offering_ids).values_list(
        "id", "period__academic_year", "period__start_date", "organization__settings__registrar__midterm_from_year"
    )
    return frozenset(oid for oid, year, start, raw in rows if is_midterm_fields(year, start, from_year_raw=raw))


def _resolve_known(offering, *, orgs, period, carried):
    # ``__dict__`` — ``.only()`` ilə təxirə salınmış FK sütununa toxunmaq sətir başına sorğu olardı.
    fields = getattr(offering, "__dict__", {})
    own_period = _cached(offering, "period")
    if own_period is None and period is not None and fields.get("period_id") == period.id:
        own_period = period
    if own_period is not None:
        org = orgs.get(fields.get("organization_id"))
        if org is not None:
            return interim_assessment.mode_for_period(own_period, org) == interim_assessment.MODE_MIDTERM
    if isinstance(carried, Mapping) and offering.id in carried:
        academic_year, start_date, from_year_raw = carried[offering.id]
        return is_midterm_fields(academic_year, start_date, from_year_raw=from_year_raw)
    return None


def offering_is_midterm(offering, *, organization=None, period=None) -> bool:
    """Tək açılış — keşdədirsə sorğusuz; əks halda bir sorğu (nəticə nümunəyə memo olunur)."""
    fields = getattr(offering, "__dict__", {})
    if getattr(offering, _MODE_ATTR, None) is None and _cached(offering, "period") is None and period is None:
        orgs = _known_organizations([offering], organization, None)
        if fields.get("organization_id") in orgs and fields.get("period_id") is not None:
            offering.period  # noqa: B018 — FK bir dəfə yüklənir və nümunədə KEŞLƏNİR (sonrakılar sorğusuz)
    flag = midterm_flags([offering], organization=organization, period=period).get(getattr(offering, "id", None))
    if flag is None:  # yazılmamış (pk-sız) nümunə — birbaşa kanonik qayda
        return interim_assessment.is_midterm_offering(offering)
    return flag


def rule_for(enrollment, *, organization=None) -> EntryRule:
    """Tək-sətir yolu: rejim açılışdan; davamiyyət girişləri lazım olanda :func:`attendance_inputs`."""
    return EntryRule(midterm=True) if offering_is_midterm(enrollment.offering, organization=organization) else LEGACY


# ── SQL güzgüləri üçün (``apps.accounts`` yalnız ``registrar.public`` fasadından oxuyur) ─────
#: ``{offering_id: seminar/lab maskası}`` — TƏK sorğu (:mod:`apps.registrar.activity_kinds`).
activity_bits_map = activity_kinds.bits_map
#: Maskanın SQL ifadəsi — mövcud açılış sorğusuna qatmaq üçün (``prefix`` — açılışa gedən yol).
activity_bits_expression = activity_kinds.bits_expression
#: ``(açar, dərs növü, cəm, say)`` sətirləri → ``{açar: LessonTotals}``.
lesson_totals_by_key = activity_kinds.totals_by_key
LessonTotals = activity_kinds.LessonTotals
ACTIVITY_BITS_ATTR = activity_kinds.BITS_ATTR


__all__ = [
    "ACTIVITY_BITS_ATTR",
    "ACTIVITY_MAX",
    "ATTENDANCE_MAX",
    "EntryParts",
    "EntryRule",
    "LEGACY",
    "LessonTotals",
    "MIDTERM_MAX",
    "RuleFlags",
    "SELFWORK_MAX",
    "STANDARD_TOTAL",
    "activity_bits_expression",
    "activity_bits_map",
    "activity_part",
    "attendance_inputs",
    "attendance_part",
    "compose",
    "compose_from_totals",
    "is_midterm_fields",
    "lesson_totals_by_key",
    "midterm_flags",
    "midterm_max",
    "midterm_offering_ids",
    "midterm_part",
    "offering_is_midterm",
    "parts_for",
    "period_is_midterm",
    "rule_flags",
    "rule_for",
    "selfwork_part",
]
