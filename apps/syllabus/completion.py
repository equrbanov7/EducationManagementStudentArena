"""Tamamlanma — BİZNES QAYDASINA görə, doldurulmuş input sayına görə YOX.

README §3.2-dəki 8 qayda bölməsi (``RULE_SECTIONS``) ayrı-ayrılıqda «ödənilib /
ödənilməyib» kimi qiymətləndirilir; faiz = ödənilən bölmə / 8. Boş qalmış
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
    MIN_OFFICE_HOURS_CHARS,
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
    office = _text(data.get("office_hours"))
    if not teacher:
        issues.append(Issue(SectionKey.INFO.value, "info.teacher_missing"))
    if len(office) < MIN_OFFICE_HOURS_CHARS:
        issues.append(Issue(SectionKey.INFO.value, "info.office_hours_missing", {"min": MIN_OFFICE_HOURS_CHARS}))
    return bool(teacher) and len(office) >= MIN_OFFICE_HOURS_CHARS


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


def _check_out(data, week_data, issues) -> bool:
    outcomes = _outcome_labels(data)
    used = set()
    for row in week_data.get("rows") or []:
        link = _text(row.get("outcome") if isinstance(row, dict) else "")
        if link:
            used.add(link)
    orphans = [index for index in range(1, len(outcomes) + 1) if f"TN{index}" not in used]
    ok = True
    if len(outcomes) < MIN_OUTCOMES:
        ok = False
        issues.append(Issue(SectionKey.OUT.value, "out.too_few", {"min": MIN_OUTCOMES, "have": len(outcomes)}))
    if orphans:
        ok = False
        issues.append(Issue(SectionKey.OUT.value, "out.orphan_outcomes", {"count": len(orphans), "indexes": orphans}))
    return ok


def _check_week(data, plan_hours, issues) -> bool:
    rows = [row for row in (data.get("rows") or []) if isinstance(row, dict)]
    filled = [row for row in rows if len(_text(row.get("topic"))) >= MIN_TOPIC_CHARS]
    totals = {kind: sum(_int(row.get(kind)) for row in rows) for kind in LESSON_HOUR_KINDS}
    ghost = [row for row in rows if not _text(row.get("topic")) and sum(_int(row.get(k)) for k in LESSON_HOUR_KINDS)]
    no_hour = [row for row in filled if sum(_int(row.get(kind)) for kind in LESSON_HOUR_KINDS) == 0]
    unlinked = [row for row in filled if not _text(row.get("outcome"))]

    ok = True
    if len(filled) < MIN_FILLED_WEEKS:
        ok = False
        issues.append(
            Issue(SectionKey.WEEK.value, "week.too_few_topics", {"min": MIN_FILLED_WEEKS, "have": len(filled)})
        )
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
    if unlinked:
        ok = False
        issues.append(Issue(SectionKey.WEEK.value, "week.outcome_not_linked", {"count": len(unlinked)}))
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


def _check_assess(data, weights, issues) -> bool:
    """Qiymətləndirmə çəkiləri — README §8/4: cəm HƏMİŞƏ 100.

    Davamiyyət / sərbəst iş / yekun imtahan universitet SİYASƏTİ ilə kilidlidir
    (``weights``), müəllim yalnız qalan ``flex`` balı aralıq imtahan ↔ semestr
    layihəsi arasında bölür.  Bölgü TAM olmalıdır: bölünməmiş bal cəmi 100-dən
    aşağı salır, ona görə «toxunulmamış» (0/0) bölgü də QƏBUL EDİLMİR.

    Qayda domen qatındadır, redaktor slaydında yox: HTTP səthi
    (``syllabus_section_save``) ixtiyari JSON qəbul edir, yəni struktur
    invariantı yalnız burada və ``services.drafts.save_section``-da qorunur.
    """
    flex = _int(weights.get("flex"))
    midterm = _int(data.get("midterm"))
    project = _int(data.get("project"))
    if midterm < 0 or project < 0:
        issues.append(Issue(SectionKey.ASSESS.value, "assess.negative_weight", {}))
        return False
    if midterm + project != flex:
        issues.append(
            Issue(
                SectionKey.ASSESS.value,
                "assess.split_mismatch",
                {"need": flex, "have": midterm + project},
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


def evaluate(section_data: dict, plan_hours: dict | None = None, assessment: dict | None = None) -> CompletionReport:
    """Bölmə məzmunundan tamamlanma hesabatı qurur.

    ``section_data`` — ``{section_id: data}`` xəritəsi (``SyllabusSection.data``).
    ``plan_hours`` — tədris planından gələn saat bölgüsü; ``week`` qaydası bunun
    ilə tutuşdurulur.
    ``assessment`` — :mod:`apps.syllabus.policy`-dən gələn çəki siyasəti
    (kilidli çəkilər + ``flex``); verilməsə org-suz default işlədilir.

    ``assess`` bölməsi ARTIQ AVTOMATİK ÖDƏNİLMİŞ SAYILMIR (2026-09-03): kilidli
    çəkilər müəllimə açıq deyil, amma qalan ``flex`` balın TAM bölünməsi məhz
    müəllimin işidir və README §8/4 cəmi 100 tələb edir.
    """
    from .policy import assessment_weights

    weights = assessment or assessment_weights(None)
    data = {key: (section_data.get(key) or {}) for key in RULE_SECTIONS}
    issues: list = []
    results = {
        SectionKey.INFO.value: _check_info(data[SectionKey.INFO], issues),
        SectionKey.DESC.value: _check_desc(data[SectionKey.DESC], issues),
        SectionKey.OUT.value: _check_out(data[SectionKey.OUT], data[SectionKey.WEEK], issues),
        SectionKey.WEEK.value: _check_week(data[SectionKey.WEEK], plan_hours, issues),
        SectionKey.METHOD.value: _check_method(data[SectionKey.METHOD], issues),
        SectionKey.ASSESS.value: _check_assess(data[SectionKey.ASSESS], weights, issues),
        SectionKey.SELF.value: _check_self(data[SectionKey.SELF], issues),
        SectionKey.LIT.value: _check_lit(data[SectionKey.LIT], issues),
    }
    done = sum(1 for key in RULE_SECTIONS if results[key])
    percent = round(done / len(RULE_SECTIONS) * 100)
    return CompletionReport(sections=results, percent=percent, issues=tuple(issues))


__all__ = ["CompletionReport", "Issue", "evaluate"]
