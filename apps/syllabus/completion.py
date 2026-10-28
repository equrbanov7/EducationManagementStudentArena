"""Tamamlanma — BİZNES QAYDASINA görə, doldurulmuş input sayına görə YOX.

README §3.2-dəki 8 qayda bölməsi (``RULE_SECTIONS``) ayrı-ayrılıqda «ödənilib /
ödənilməyib» kimi qiymətləndirilir; faiz = ödənilən bölmə / 8 (sərbəst işi söndürülmüş
qaydada — sahib 2026-10-10 — ``self`` daxil deyil: / 7). Boş qalmış
opsional sahə faizi aşağı SALMIR, yarımçıq məcburi qayda isə bölməni TAM
ödənilməmiş sayır — «10 sahədən 7-si doldurulub = 70%» sayğacı QƏSDƏN yoxdur.

Nəticə strukturlaşdırılmış ISSUE KODLARI qaytarır (mətn deyil): mesaj tərcüməsi
UI qatına aiddir, domen qatı yalnız kod + parametr verir. Kodların tam siyahısı
:mod:`apps.syllabus.public` müqaviləsindədir.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .constants import (
    LESSON_HOUR_KINDS,
    MIN_ADDITIONAL_SOURCES,
    MIN_DESCRIPTION_CHARS,
    MIN_FILLED_WEEKS,
    MIN_GOAL_CHARS,
    MIN_METHODS,
    MIN_OUTCOME_CHARS,
    MIN_OUTCOMES,
    MIN_PRIMARY_SOURCES,
    MIN_SELFWORK_TOPIC_CHARS,
    MIN_SOURCE_CHARS,
    MIN_TOPIC_CHARS,
    RULE_SECTIONS,
    SELFWORK_OPTIONS,
    SectionKey,
)
from .rules import SyllabusRule
from .week_plan import expected_week_rows


@dataclass(frozen=True)
class Issue:
    """Bir çatışmazlıq: hansı bölmə, hansı qayda, hansı ölçülər."""

    section: str
    code: str
    params: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"section": self.section, "code": self.code, "params": dict(self.params)}


@dataclass(frozen=True)
class CompletionReport:
    """Bölmə-bölmə nəticə + faiz + çatışmazlıq siyahısı."""

    sections: dict
    percent: int
    issues: tuple

    @property
    def is_complete(self) -> bool:
        return self.percent == 100

    def as_dict(self) -> dict:
        return {
            "sections": dict(self.sections),
            "percent": self.percent,
            "issues": [issue.as_dict() for issue in self.issues],
        }


def _text(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _lines(value) -> list:
    """Mətn blokunu və ya siyahını mənbə sətirlərinə çevirir."""
    if isinstance(value, (list, tuple)):
        raw = [_text(item) for item in value]
    else:
        raw = [_text(line) for line in _text(value).split("\n")]
    return [line for line in raw if len(line) > MIN_SOURCE_CHARS]


def _check_info(data, issues) -> bool:
    teacher = _text(data.get("teacher"))
    if not teacher:
        issues.append(Issue(SectionKey.INFO.value, "info.teacher_missing"))
    return bool(teacher)


def _check_desc(data, issues) -> bool:
    description = _text(data.get("description"))
    goal = _text(data.get("goal"))
    ok = True
    if len(description) < MIN_DESCRIPTION_CHARS:
        ok = False
        issues.append(
            Issue(
                SectionKey.DESC.value,
                "desc.description_too_short",
                {"min": MIN_DESCRIPTION_CHARS, "have": len(description)},
            )
        )
    if len(goal) < MIN_GOAL_CHARS:
        ok = False
        issues.append(Issue(SectionKey.DESC.value, "desc.goal_too_short", {"min": MIN_GOAL_CHARS, "have": len(goal)}))
    return ok


def _outcome_labels(data) -> list:
    """Etibarlı təlim nəticələri (TN1, TN2, … sırası ilə)."""
    raw = data.get("outcomes") or []
    return [_text(item) for item in raw if len(_text(item)) >= MIN_OUTCOME_CHARS]


def _check_out(data, issues) -> bool:
    """Sahib 2026-10-15: ən azı ``MIN_OUTCOMES`` (1) dolu nəticə — həftəyə bağlanma TƏLƏB OLUNMUR.

    Əvvəlki «hər nəticə ən azı bir həftədə istifadə olunsun» (``out.orphan_outcomes``) qaydası ləğv edilib.
    """
    outcomes = _outcome_labels(data)
    if len(outcomes) < MIN_OUTCOMES:
        issues.append(Issue(SectionKey.OUT.value, "out.too_few", {"min": MIN_OUTCOMES, "have": len(outcomes)}))
        return False
    return True


def _check_week(data, plan_hours, issues) -> bool:
    rows = [row for row in (data.get("rows") or []) if isinstance(row, dict)]
    filled = [row for row in rows if len(_text(row.get("topic"))) >= MIN_TOPIC_CHARS]
    totals = {kind: sum(_int(row.get(kind)) for row in rows) for kind in LESSON_HOUR_KINDS}
    ghost = [row for row in rows if not _text(row.get("topic")) and sum(_int(row.get(k)) for k in LESSON_HOUR_KINDS)]
    no_hour = [row for row in filled if sum(_int(row.get(kind)) for kind in LESSON_HOUR_KINDS) == 0]
    # Sahib 2026-10-15: həftə sətrinin təlim nəticəsi (``outcome``) İSTƏYƏ BAĞLIDIR — boş qalması
    # bölməni natamam saymır (əvvəlki ``week.outcome_not_linked`` qaydası ləğv edilib).

    ok = True
    # Plan varsa minimum PLANDAN çıxarılan sətir sayıdır (15 saat → 8 mövzu);
    # plan yoxdursa köhnə sabit (14) qalır.
    minimum = expected_week_rows(plan_hours) or MIN_FILLED_WEEKS
    if len(filled) < minimum:
        ok = False
        issues.append(Issue(SectionKey.WEEK.value, "week.too_few_topics", {"min": minimum, "have": len(filled)}))
    # Saat balansı YALNIZ tədris planı saat bölgüsü verəndə yoxlanılır.
    #
    # `plan_hours` boş olanda («{}») əvvəllər hər növ üçün `expected = 0`
    # alınırdı; halbuki aşağıdakı `no_hour` qaydası dolu hər mövzudan ən azı
    # 1 saat TƏLƏB EDİR.  İki qayda bir-birini istisna edirdi, yəni plan
    # bölgüsü olmayan sillabus HEÇ VAXT `week` bölməsini bağlaya bilmirdi
    # → tamamlanma 100%-ə çatmır → təsdiqə göndərilə bilmir.
    # Bu, müəllimin sıfırdan yaratdığı hər yeni qaralamaya aid idi
    # (`api.py::_do_create` `plan_hours={}` ötürür, çünki `CourseOffering`
    # yalnız `lesson_hours` cəmini daşıyır, növ üzrə bölgünü yox).
    #
    # Doğru semantika: «plan varsa ona bərabər olsun», «plan yoxdursa
    # məhdudiyyət də yoxdur».  Plan bölgüsü modelləşəndə (apps/workload ↔
    # apps/syllabus müqaviləsi) bu şərt öz-özünə yenidən işə düşür.
    for kind in LESSON_HOUR_KINDS:
        if not _int((plan_hours or {}).get(kind)):
            continue
        expected = _int((plan_hours or {}).get(kind))
        if totals[kind] != expected:
            ok = False
            issues.append(
                Issue(
                    SectionKey.WEEK.value,
                    "week.hours_mismatch",
                    {"kind": kind, "expected": expected, "have": totals[kind]},
                )
            )
    if ghost:
        ok = False
        issues.append(Issue(SectionKey.WEEK.value, "week.hours_without_topic", {"count": len(ghost)}))
    if no_hour:
        ok = False
        issues.append(Issue(SectionKey.WEEK.value, "week.topic_without_hours", {"count": len(no_hour)}))
    return ok


def _check_method(data, issues) -> bool:
    methods = [_text(item) for item in (data.get("methods") or []) if _text(item)]
    if len(methods) < MIN_METHODS:
        issues.append(Issue(SectionKey.METHOD.value, "method.too_few", {"min": MIN_METHODS, "have": len(methods)}))
        return False
    return True


def _check_self(data, issues) -> bool:
    option = _text(data.get("option"))
    config = SELFWORK_OPTIONS.get(option)
    if config is None:
        issues.append(Issue(SectionKey.SELF.value, "self.option_not_allowed", {"option": option}))
        return False
    topics = [t for t in (data.get("topics") or []) if isinstance(t, dict)]
    filled = [t for t in topics if len(_text(t.get("title"))) >= MIN_SELFWORK_TOPIC_CHARS]
    if len(filled) != config["count"]:
        issues.append(
            Issue(SectionKey.SELF.value, "self.topic_count_mismatch", {"need": config["count"], "have": len(filled)})
        )
        return False
    return True


def _check_assess(data, weights, issues, accepted=()) -> bool:
    """Qiymətləndirmə çəkiləri — README §8/4: cəm HƏMİŞƏ 100.

    Davamiyyət / sərbəst iş / yekun imtahan universitet SİYASƏTİ ilə kilidlidir
    (``weights``), müəllim yalnız qalan ``flex`` balı aralıq imtahan ↔ semestr
    layihəsi arasında bölür.  Bölgü TAM olmalıdır: bölünməmiş bal cəmi 100-dən
    aşağı salır, ona görə «toxunulmamış» (0/0) bölgü də QƏBUL EDİLMİR.

    Qayda domen qatındadır, redaktor slaydında yox: HTTP səthi
    (``syllabus_section_save``) ixtiyari JSON qəbul edir, yəni struktur
    invariantı yalnız burada və ``services.drafts.save_section``-da qorunur.

    ``accepted`` — standartdan əlavə qəbul olunan ``(midterm, project)`` cütləri
    (``policy.standard_splits``): sahib 2026-10-10 qaydası standartı dəyişəndə (midterm
    20 → 30) əvvəlki standartla saxlanmış bölgü yalnız buna görə «natamam» sayılmır.
    """
    from .policy import standard_midterm, standard_project

    midterm = _int(data.get("midterm"))
    project = _int(data.get("project"))
    if midterm < 0 or project < 0:
        issues.append(Issue(SectionKey.ASSESS.value, "assess.negative_weight", {}))
        return False
    # Sahib 2026-09-20: bölgü STANDARTDIR (midterm 30 + seminar/lab orta 10; sərbəst iş
    # yandırılanda 20 + 10);
    # saxlanan dəyər standarta bərabər deyilsə bölmə tamamlanmamış sayılır
    # (növbəti autosave-də `save_section` onu standarta gətirir).
    need_midterm, need_project = standard_midterm(weights), standard_project(weights)
    if (midterm, project) != (need_midterm, need_project) and (midterm, project) not in accepted:
        issues.append(
            Issue(
                SectionKey.ASSESS.value,
                "assess.split_mismatch",
                {"need": need_midterm + need_project, "have": midterm + project},
            )
        )
        return False
    return True


def _check_lit(data, issues) -> bool:
    primary = _lines(data.get("primary"))
    additional = _lines(data.get("additional"))
    ok = True
    if len(primary) < MIN_PRIMARY_SOURCES:
        ok = False
        issues.append(
            Issue(SectionKey.LIT.value, "lit.primary_too_few", {"min": MIN_PRIMARY_SOURCES, "have": len(primary)})
        )
    if len(additional) < MIN_ADDITIONAL_SOURCES:
        ok = False
        issues.append(
            Issue(
                SectionKey.LIT.value, "lit.additional_too_few", {"min": MIN_ADDITIONAL_SOURCES, "have": len(additional)}
            )
        )
    return ok


def evaluate(
    section_data: dict,
    plan_hours: dict | None = None,
    assessment: dict | None = None,
    *,
    selfwork: bool = True,
    accepted_splits=(),
) -> CompletionReport:
    """Bölmə məzmunundan tamamlanma hesabatı qurur.

    ``section_data`` — ``{section_id: data}`` xəritəsi (``SyllabusSection.data``).
    ``plan_hours`` — tədris planından gələn saat bölgüsü; ``week`` qaydası bunun
    ilə tutuşdurulur.
    ``assessment`` — :mod:`apps.syllabus.policy`-dən gələn çəki siyasəti
    (kilidli çəkilər + ``flex``); verilməsə org-suz default işlədilir.

    ``assess`` bölməsi ARTIQ AVTOMATİK ÖDƏNİLMİŞ SAYILMIR (2026-09-03): kilidli
    çəkilər müəllimə açıq deyil, amma qalan ``flex`` balın TAM bölünməsi məhz
    müəllimin işidir və README §8/4 cəmi 100 tələb edir.

    ``selfwork`` — sərbəst iş bölməsi qaydaya daxildirmi. Sahib 2026-10-10: yeni qayda
    dövrlərində sərbəst iş söndürüləndə ``self`` yoxlanmır və faizə daxil deyil (7 bölmə),
    bölmənin datası isə toxunulmur. Defolt ``True`` — tam kataloq; semestri bilən çağıran
    ``SyllabusRule.selfwork`` ötürür (``services.drafts.recompute_completion``).
    ``accepted_splits`` — :func:`_check_assess`-ə ötürülür.
    """
    from .policy import assessment_weights

    weights = assessment or assessment_weights(None, selfwork=selfwork)
    sections = SyllabusRule(selfwork=selfwork).rule_sections
    data = {key: (section_data.get(key) or {}) for key in RULE_SECTIONS}
    issues: list = []
    results = {
        SectionKey.INFO.value: _check_info(data[SectionKey.INFO], issues),
        SectionKey.DESC.value: _check_desc(data[SectionKey.DESC], issues),
        SectionKey.OUT.value: _check_out(data[SectionKey.OUT], issues),
        SectionKey.WEEK.value: _check_week(data[SectionKey.WEEK], plan_hours, issues),
        SectionKey.METHOD.value: _check_method(data[SectionKey.METHOD], issues),
        SectionKey.ASSESS.value: _check_assess(data[SectionKey.ASSESS], weights, issues, accepted_splits or ()),
    }
    if selfwork:
        results[SectionKey.SELF.value] = _check_self(data[SectionKey.SELF], issues)
    results[SectionKey.LIT.value] = _check_lit(data[SectionKey.LIT], issues)
    done = sum(1 for key in sections if results[key])
    percent = round(done / len(sections) * 100)
    return CompletionReport(sections=results, percent=percent, issues=tuple(issues))


__all__ = ["CompletionReport", "Issue", "evaluate"]
