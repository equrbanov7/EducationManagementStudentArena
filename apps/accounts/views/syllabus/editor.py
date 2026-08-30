"""«Müəllim — Sillabus redaktoru» bölməsinin CONTEXT MÜQAVİLƏSİ (dizayn §3.2).

10 bölmə (``id``-lər dizayn paketi ilə EYNİ) profil shell-inin içində açılır —
SOL SIDEBAR QALIR. Bölmələr bir dəfə render olunur, sol naviqasiya isə aktiv
bölməni yalnız CSS ilə dəyişir (server round-trip yoxdur); autosave hər bölmə
üçün ayrıca PATCH göndərir (``.api.syllabus_section_save``).

──────────────────────────────────────────────────────────────────────────────
CONTEXT MÜQAVİLƏSİ — ``syllabus_editor_section`` (dict)
──────────────────────────────────────────────────────────────────────────────
    view_state   "normal" | "readonly" | "permission" | "missing"
    header       {code,name,meta,status_label,status_tone,version_label}
    nav          [{id,index,label,state,issue_count}]      — 10 addım
    panels       [{id,title,hint,is_rule,is_complete,data,revision}]
    completion   {percent,tone,done,total,note}
    issues       [{section,section_title,text}]
    summary      [{label,value,tone}]
    history      [{title,meta,tone}]
    selfwork     {options,disallowed,total_score}
    methods      [str]
    plan_hours   {lecture,seminar,lab,total}
    week_rows    [{index,topic,lecture,seminar,lab,outcome}]
    can_submit   bool
    urls         {save,action,list}
"""

from __future__ import annotations

from django.urls import reverse
from django.utils.translation import pgettext_lazy

from apps.syllabus.constants import (
    LESSON_HOUR_KINDS,
    MIN_DESCRIPTION_CHARS,
    MIN_GOAL_CHARS,
    MIN_OUTCOMES,
    RULE_SECTIONS,
    SELFWORK_DISALLOWED,
    SELFWORK_OPTIONS,
    SELFWORK_TOTAL_SCORE,
    WEEK_ROWS,
    SectionKey,
    SyllabusStatus,
)
from apps.syllabus.public import build_syllabus_editor_context

from .labels import HOUR_KIND_LABELS, STATUS_TONES, issue_text
from .preview import build_preview_blocks

_CTX = "accounts.syllabus"

ACCESS_DENIED = pgettext_lazy(_CTX, "Bu sillabusa giriş icazəniz yoxdur.")
NOT_FOUND = pgettext_lazy(_CTX, "Sillabus tapılmadı və ya artıq mövcud deyil.")

#: Qiymətləndirmə siyasəti — universitet səviyyəsində KİLİDLİ çəkilər (dizayn §3.2).
#: Müəllim yalnız `flex` (30 bal) hissəsini aralıq imtahan ↔ semestr layihəsi
#: arasında bölür; cəm HƏMİŞƏ 100 qalır.
ASSESSMENT_POLICY = {"attendance": 10, "selfwork": SELFWORK_TOTAL_SCORE, "final": 50, "flex": 30}

#: Sol naviqasiyanın QISA etiketi + bölmə başlığı + izah mətni (dizayn `SEC`).
SECTION_META = {
    SectionKey.INFO.value: (
        pgettext_lazy(_CTX, "Ümumi məlumat"),
        pgettext_lazy(_CTX, "Ümumi məlumat"),
        pgettext_lazy(
            _CTX,
            "Fənnin pasport məlumatları tədris planından gəlir və kilidlidir. Siz yalnız dərsi aparan müəllim, "
            "məsləhət saatı və prerekvizit sətirlərini doldurursunuz.",
        ),
    ),
    SectionKey.DESC.value: (
        pgettext_lazy(_CTX, "Təsvir və məqsəd"),
        pgettext_lazy(_CTX, "Fənnin təsviri və məqsədi"),
        pgettext_lazy(
            _CTX,
            "Təsvir tələbənin fənn seçimi zamanı gördüyü mətndir. Məqsəd bölməsi kafedra baxışında ilk oxunan "
            "hissədir.",
        ),
    ),
    SectionKey.OUT.value: (
        pgettext_lazy(_CTX, "Təlim nəticələri"),
        pgettext_lazy(_CTX, "Təlim nəticələri"),
        pgettext_lazy(
            _CTX,
            "Tələbə fənni bitirəndə nə bacaracaq. Ən azı 3 nəticə tələb olunur, hər biri həftəlik plandan ən azı "
            "bir mövzu ilə əlaqələndirilməlidir.",
        ),
    ),
    SectionKey.WEEK.value: (
        pgettext_lazy(_CTX, "Həftəlik mövzular"),
        pgettext_lazy(_CTX, "Həftəlik mövzular"),
        pgettext_lazy(
            _CTX,
            "Auditoriya saatlarının həftələr üzrə bölgüsü. Bu sətirlər təsdiqdən sonra e-jurnalda mövzu siyahısını "
            "yaradır — sonradan jurnaldan dəyişdirilə bilməz.",
        ),
    ),
    SectionKey.METHOD.value: (
        pgettext_lazy(_CTX, "Tədris metodları"),
        pgettext_lazy(_CTX, "Tədris metodları"),
        pgettext_lazy(_CTX, "Fənn üzrə istifadə olunan metodlar. Ən azı 2 metod seçilməlidir."),
    ),
    SectionKey.ASSESS.value: (
        pgettext_lazy(_CTX, "Qiymətləndirmə"),
        pgettext_lazy(_CTX, "Qiymətləndirmə strukturu"),
        pgettext_lazy(
            _CTX,
            "Davamiyyət, sərbəst iş və yekun imtahanın çəkisi universitet siyasəti ilə təyin edilib. Qalan 30 bal "
            "aralıq imtahan və semestr layihəsi arasında bölünür.",
        ),
    ),
    SectionKey.SELF.value: (
        pgettext_lazy(_CTX, "Sərbəst iş"),
        pgettext_lazy(_CTX, "Sərbəst iş strukturu"),
        pgettext_lazy(
            _CTX,
            "Universitetin icazə verdiyi üç struktur var və hər birinin cəmi 10 baldır. Struktur seçildikdən sonra "
            "mövzular həmin sayda daxil edilir.",
        ),
    ),
    SectionKey.LIT.value: (
        pgettext_lazy(_CTX, "Ədəbiyyat"),
        pgettext_lazy(_CTX, "Əsas və əlavə ədəbiyyat"),
        pgettext_lazy(_CTX, "Əsas ədəbiyyatda ən azı 2, əlavə ədəbiyyatda ən azı 1 mənbə göstərilməlidir."),
    ),
    SectionKey.PREV.value: (
        pgettext_lazy(_CTX, "Yekun görünüş"),
        pgettext_lazy(_CTX, "Yekun görünüş"),
        pgettext_lazy(
            _CTX, "Sillabusun yekun görünüşü. Bu görünüş tələbə kabinetində və kafedra baxışında eynidir."
        ),
    ),
    SectionKey.SEND.value: (
        pgettext_lazy(_CTX, "Təsdiqə göndərmə"),
        pgettext_lazy(_CTX, "Təsdiqə göndərmə"),
        pgettext_lazy(
            _CTX,
            "Bütün məcburi tələblər ödənildikdən sonra sillabus kafedra müdirinin növbəsinə düşür. Göndərildikdən "
            "sonra versiya kilidlənir.",
        ),
    ),
}

#: Sərbəst iş variantlarının izah mətni (dizayn §3.2 kart mətnləri).
SELFWORK_NOTES = {
    "1x10": pgettext_lazy(_CTX, "Bir böyük sərbəst iş — semestr layihəsi formatına uyğundur."),
    "2x5": pgettext_lazy(_CTX, "İki tapşırıq — semestrin ortası və sonu üçün balanslı variant."),
    "10x1": pgettext_lazy(_CTX, "Hər həftə kiçik tapşırıq — davamlı iş tələb edir."),
    "3x5": pgettext_lazy(_CTX, "Universitet siyasətinə uyğun deyil — cəmi 15 bal edir."),
}

_SUMMARY_LABELS = {
    "code": pgettext_lazy(_CTX, "Fənn kodu"),
    "credit": pgettext_lazy(_CTX, "Kredit"),
    "hours": pgettext_lazy(_CTX, "Auditoriya saatı"),
    "split": pgettext_lazy(_CTX, "Növ üzrə bölgü"),
    "outcomes": pgettext_lazy(_CTX, "Təlim nəticəsi"),
    "weeks": pgettext_lazy(_CTX, "Doldurulmuş həftə"),
    "methods": pgettext_lazy(_CTX, "Tədris metodu"),
    "selfwork": pgettext_lazy(_CTX, "Sərbəst iş strukturu"),
    "assessment": pgettext_lazy(_CTX, "Qiymətləndirmə cəmi"),
    "literature": pgettext_lazy(_CTX, "Ədəbiyyat"),
    "version": pgettext_lazy(_CTX, "Versiya"),
}

_UNIT_COUNT = pgettext_lazy(_CTX, "%(count)s ədəd")
_UNIT_HOURS = pgettext_lazy(_CTX, "%(count)s saat")
_UNIT_SELECTED = pgettext_lazy(_CTX, "%(count)s seçilib")
_UNIT_SOURCES = pgettext_lazy(_CTX, "%(primary)s əsas · %(additional)s əlavə")
_UNIT_WEEKS = pgettext_lazy(_CTX, "%(have)s / %(total)s")
_UNIT_POINTS = pgettext_lazy(_CTX, "100 bal")
_NOT_SELECTED = pgettext_lazy(_CTX, "seçilməyib")
_COMPLETION_NOTE = pgettext_lazy(_CTX, "%(done)s / %(total)s bölmə biznes qaydalarına uyğundur")


def _int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _week_rows(data) -> list:
    """``week`` bölməsinin 16 sətrini normallaşdırır (əskik sətir = boş sətir)."""
    raw = [row for row in (data.get("rows") or []) if isinstance(row, dict)]
    rows = []
    for index in range(WEEK_ROWS):
        source = raw[index] if index < len(raw) else {}
        row = {"index": index + 1, "topic": (source.get("topic") or "").strip(), "outcome": source.get("outcome") or ""}
        for kind in LESSON_HOUR_KINDS:
            row[kind] = _int(source.get(kind))
        # Şablon xüsusi filtr yazmadan dövr edə bilsin deyə saat xanaları hazır
        # siyahı kimi verilir (`{{ row|dictkey:… }}` kimi tələ qalmır).
        row["cells"] = [
            {"key": kind, "label": HOUR_KIND_LABELS[kind], "value": row[kind]} for kind in LESSON_HOUR_KINDS
        ]
        rows.append(row)
    return rows


#: Həftəlik cədvəldəki saat seçimləri (dizayn: «—», 1 s … 4 s).
HOUR_CHOICES = (0, 1, 2, 3, 4)


def _outcome_tags(data) -> list:
    """Mövcud təlim nəticələrinin etiketləri — həftə sətrinin açılış siyahısı."""
    count = len([item for item in (data.get("outcomes") or []) if str(item).strip()])
    return [f"TN{index}" for index in range(1, count + 1)]


def _hour_totals(week_rows, plan_hours) -> dict:
    totals = {kind: sum(row[kind] for row in week_rows) for kind in LESSON_HOUR_KINDS}
    planned = {kind: _int((plan_hours or {}).get(kind)) for kind in LESSON_HOUR_KINDS}
    return {
        "rows": [
            {
                "kind": kind,
                "have": totals[kind],
                "planned": planned[kind],
                "ok": totals[kind] == planned[kind],
            }
            for kind in LESSON_HOUR_KINDS
        ],
        "have": sum(totals.values()),
        "planned": sum(planned.values()),
        "ok": totals == planned,
    }


def _selfwork(data):
    option = (data.get("option") or "").strip()
    topics = [row for row in (data.get("topics") or []) if isinstance(row, dict)]
    options = []
    for key, config in SELFWORK_OPTIONS.items():
        options.append(
            {
                "key": key,
                "title": f"{config['count']} × {config['per_score']}",
                "count": config["count"],
                "per_score": config["per_score"],
                "total": config["count"] * config["per_score"],
                "note": SELFWORK_NOTES.get(key, ""),
                "active": option == key,
                "allowed": True,
            }
        )
    for key, config in SELFWORK_DISALLOWED.items():
        options.append(
            {
                "key": key,
                "title": f"{config['count']} × {config['per_score']}",
                "count": config["count"],
                "per_score": config["per_score"],
                "total": config["count"] * config["per_score"],
                "note": SELFWORK_NOTES.get(key, ""),
                "active": False,
                "allowed": False,
            }
        )
    config = SELFWORK_OPTIONS.get(option)
    slots = []
    for index in range(config["count"] if config else 0):
        source = topics[index] if index < len(topics) else {}
        slots.append(
            {
                "index": index + 1,
                "title": (source.get("title") or "").strip(),
                "graded": bool(source.get("graded")),
                "graded_count": _int(source.get("graded_count")),
                "per_score": config["per_score"],
            }
        )
    return {
        "option": option,
        "options": options,
        "slots": slots,
        "archived": [row for row in (data.get("archived") or []) if isinstance(row, dict)],
        "total_score": SELFWORK_TOTAL_SCORE,
    }


def _assessment(data):
    midterm = _int(data.get("midterm"))
    flex = ASSESSMENT_POLICY["flex"]
    midterm = max(0, min(midterm, flex))
    return {
        "attendance": ASSESSMENT_POLICY["attendance"],
        "selfwork": ASSESSMENT_POLICY["selfwork"],
        "final": ASSESSMENT_POLICY["final"],
        "flex": flex,
        "midterm": midterm,
        "project": flex - midterm,
        "note": (data.get("note") or "").strip(),
    }


_LOCKED_LABELS = {
    "subject": pgettext_lazy(_CTX, "Fənnin adı və kodu"),
    "chair": pgettext_lazy(_CTX, "Kafedra"),
    "program": pgettext_lazy(_CTX, "Təhsil proqramı"),
    "period": pgettext_lazy(_CTX, "Akademik il / semestr"),
    "credit": pgettext_lazy(_CTX, "Kredit"),
    "split": pgettext_lazy(_CTX, "Saat bölgüsü"),
    "group": pgettext_lazy(_CTX, "Qrup"),
}

_LOCKED_SOURCES = {
    "subject": pgettext_lazy(_CTX, "Fənn kataloqu"),
    "chair": pgettext_lazy(_CTX, "Struktur"),
    "program": pgettext_lazy(_CTX, "İxtisaslar"),
    "period": pgettext_lazy(_CTX, "Semestr açılışı"),
    "credit": pgettext_lazy(_CTX, "Tədris planı"),
    "split": pgettext_lazy(_CTX, "Tədris planı"),
    "group": pgettext_lazy(_CTX, "Qruplar"),
}


def _locked_rows(syllabus, hours):
    """`info` bölməsinin KİLİDLİ sətirləri — tədris planı/strukturdan gələn dəyərlər.

    Sillabusdan redaktə OLUNMUR: dəyişiklik lazımdırsa kafedraya müraciət gedir.
    Boş sahə sətri sadəcə ATILIR — «—» ilə uydurma doldurma yoxdur.
    """
    subject = syllabus.subject
    values = {
        "subject": f"{subject.name} · {subject.code}",
        "chair": syllabus.chair_unit.name if syllabus.chair_unit_id else "",
        "program": syllabus.program.name if syllabus.program_id else "",
        "period": (f"{syllabus.period.year_display} · {syllabus.period.name}" if syllabus.period_id else ""),
        "credit": str(subject.ects or ""),
        "split": " · ".join(str(row["planned"]) for row in hours["rows"]) if hours["planned"] else "",
        "group": (syllabus.offering.group.name if syllabus.offering_id and syllabus.offering.group_id else ""),
    }
    return [
        {"label": _LOCKED_LABELS[key], "value": value, "source": _LOCKED_SOURCES[key]}
        for key, value in values.items()
        if value
    ]


def _nav_state(section_id, report_sections, issue_counts):
    if section_id not in RULE_SECTIONS:
        return "check"
    if report_sections.get(section_id):
        return "done"
    return "error" if issue_counts.get(section_id) else "todo"


def _summary(*, syllabus, version, panels, completion, hours, selfwork_view, section_map):
    outcomes = [item for item in (section_map.get(SectionKey.OUT.value, {}).get("outcomes") or []) if str(item).strip()]
    weeks = [row for row in _week_rows(section_map.get(SectionKey.WEEK.value, {})) if row["topic"]]
    methods = [item for item in (section_map.get(SectionKey.METHOD.value, {}).get("methods") or []) if item]
    literature = section_map.get(SectionKey.LIT.value, {})
    primary = [line for line in (literature.get("primary") or []) if str(line).strip()]
    additional = [line for line in (literature.get("additional") or []) if str(line).strip()]
    subject = syllabus.subject
    ok = "success"
    bad = "warning"
    return [
        {"label": _SUMMARY_LABELS["code"], "value": subject.code, "tone": "default"},
        {"label": _SUMMARY_LABELS["credit"], "value": subject.ects, "tone": "default"},
        {
            "label": _SUMMARY_LABELS["hours"],
            "value": str(_UNIT_HOURS) % {"count": hours["have"]},
            "tone": ok if hours["ok"] else bad,
        },
        {
            "label": _SUMMARY_LABELS["split"],
            "value": " · ".join(f"{row['have']}/{row['planned']}" for row in hours["rows"]),
            "tone": ok if hours["ok"] else bad,
        },
        {
            "label": _SUMMARY_LABELS["outcomes"],
            "value": str(_UNIT_COUNT) % {"count": len(outcomes)},
            "tone": ok if len(outcomes) >= MIN_OUTCOMES else bad,
        },
        {
            "label": _SUMMARY_LABELS["weeks"],
            "value": str(_UNIT_WEEKS) % {"have": len(weeks), "total": WEEK_ROWS},
            "tone": "default",
        },
        {"label": _SUMMARY_LABELS["methods"], "value": str(_UNIT_SELECTED) % {"count": len(methods)}, "tone": "default"},
        {
            "label": _SUMMARY_LABELS["selfwork"],
            "value": (
                f"{selfwork_view['option']}" if selfwork_view["option"] else str(_NOT_SELECTED)
            ),
            "tone": "default" if selfwork_view["option"] else bad,
        },
        {"label": _SUMMARY_LABELS["assessment"], "value": _UNIT_POINTS, "tone": ok},
        {
            "label": _SUMMARY_LABELS["literature"],
            "value": str(_UNIT_SOURCES) % {"primary": len(primary), "additional": len(additional)},
            "tone": "default",
        },
        {"label": _SUMMARY_LABELS["version"], "value": version.label, "tone": "default"},
    ]


def _history(events):
    rows = []
    for event in events:
        if event.get("kind") == "version":
            status = event.get("status") or ""
            rows.append(
                {
                    "title": f"{event.get('version', '')} — {SyllabusStatus(status).label if status else ''}",
                    "meta": event.get("at"),
                    "actor": event.get("actor"),
                    "tone": STATUS_TONES.get(status, "neutral"),
                }
            )
        else:
            rows.append(
                {
                    "title": event.get("version", ""),
                    "meta": event.get("at"),
                    "actor": event.get("actor"),
                    "reason": event.get("reason", ""),
                    "tone": "neutral",
                }
            )
    return rows


def build_syllabus_editor_section(request, *, organization, version) -> dict:
    """Redaktor bölməsinin context-i. ``version`` None → «tapılmadı» vəziyyəti."""
    if organization is None or version is None:
        return {
            "syllabus_editor_section": {
                "view_state": "missing",
                "access_denied_message": NOT_FOUND,
                "nav": [],
                "panels": [],
            }
        }

    context = build_syllabus_editor_context(request, organization=organization, version=version)
    if context.get("view_state") == "permission":
        return {
            "syllabus_editor_section": {
                "view_state": "permission",
                "access_denied_message": ACCESS_DENIED,
                "nav": [],
                "panels": [],
            }
        }

    syllabus = context["syllabus"]
    completion = context["completion"]
    section_map = {row["id"]: (row["data"] or {}) for row in context["sections"]}

    issues = []
    issue_counts: dict = {}
    for issue in completion["issues"]:
        section_id = issue["section"]
        issue_counts[section_id] = issue_counts.get(section_id, 0) + 1
        issues.append(
            {
                "section": section_id,
                "section_title": SECTION_META[section_id][1],
                "text": issue_text(issue),
            }
        )

    # `nav` SIRALI siyahıdır (sol addım naviqasiyası), `panels` isə `id` ilə
    # açılan xəritə — şablon bölməni birbaşa `panels.info.data.teacher` kimi
    # oxusun deyə (uzun `{% for %}` + `{% if %}` zənciri olmasın).
    nav, panels = [], {}
    for index, row in enumerate(context["sections"], start=1):
        short_label, title, hint = SECTION_META[row["id"]]
        nav.append(
            {
                "id": row["id"],
                "index": index,
                "label": short_label,
                "state": _nav_state(row["id"], completion["sections"], issue_counts),
                "issue_count": issue_counts.get(row["id"], 0),
            }
        )
        panels[row["id"]] = (
            {
                "id": row["id"],
                "index": index,
                "title": title,
                "hint": hint,
                "is_rule": row["is_rule_section"],
                "is_complete": row["is_complete"],
                "data": row["data"] or {},
                "revision": row["revision"],
            }
        )

    week_rows = _week_rows(section_map.get(SectionKey.WEEK.value, {}))
    hours = _hour_totals(week_rows, context["plan_hours"])
    selfwork_view = _selfwork(section_map.get(SectionKey.SELF.value, {}))
    readonly = context["view_state"] != "normal"
    version_row = context["version"]

    return {
        "syllabus_editor_section": {
            "view_state": context["view_state"],
            "access_denied_message": "",
            "readonly": readonly,
            "syllabus_id": str(syllabus.pk),
            "version_id": str(version_row.pk),
            "header": {
                "code": syllabus.subject.code,
                "name": syllabus.subject.name,
                "program": syllabus.program.name if syllabus.program_id else "",
                "period": syllabus.period.year_display + " · " + syllabus.period.name if syllabus.period_id else "",
                "credit": syllabus.subject.ects,
                "status_key": version_row.status,
                "status_label": SyllabusStatus(version_row.status).label,
                "status_tone": STATUS_TONES.get(version_row.status, "neutral"),
                "version_label": version_row.label,
            },
            "nav": nav,
            "panels": panels,
            "active_id": (request.GET.get("step") or SectionKey.INFO.value),
            "completion": {
                "percent": completion["percent"],
                "tone": "success" if completion["percent"] >= 100 else "primary",
                "done": sum(1 for key in RULE_SECTIONS if completion["sections"].get(key)),
                "total": len(RULE_SECTIONS),
                "note": str(_COMPLETION_NOTE)
                % {
                    "done": sum(1 for key in RULE_SECTIONS if completion["sections"].get(key)),
                    "total": len(RULE_SECTIONS),
                },
            },
            "issues": issues,
            "summary": _summary(
                syllabus=syllabus,
                version=version_row,
                panels=panels,
                completion=completion,
                hours=hours,
                selfwork_view=selfwork_view,
                section_map=section_map,
            ),
            "history": _history(context["history"]),
            # `prev` bölməsi tələbənin/kafedranın gördüyü EYNİ mətni göstərir —
            # mənbə `preview.py`-dır, dublikat şablon məntiqi yoxdur.
            "preview_blocks": build_preview_blocks(section_map),
            "locked": _locked_rows(syllabus, hours),
            "hour_choices": HOUR_CHOICES,
            "outcome_tags": _outcome_tags(section_map.get(SectionKey.OUT.value, {})),
            "week_rows": week_rows,
            "hours": hours,
            "selfwork": selfwork_view,
            "assessment": _assessment(section_map.get(SectionKey.ASSESS.value, {})),
            "methods": [
                {"label": label, "active": str(label) in {str(x) for x in (section_map.get("method", {}).get("methods") or [])}}
                for label in context["teaching_methods"]
            ],
            "limits": {
                "description": MIN_DESCRIPTION_CHARS,
                "goal": MIN_GOAL_CHARS,
                "outcomes": MIN_OUTCOMES,
                "weeks": WEEK_ROWS,
            },
            "can_submit": (not readonly) and completion["percent"] >= 100,
            "actions": list(context["actions"]),
            "urls": {
                "save": reverse("accounts:syllabus_section_save", kwargs={"version_id": str(version_row.pk)}),
                "action": reverse("accounts:syllabus_action"),
            },
        }
    }


__all__ = [
    "ACCESS_DENIED",
    "ASSESSMENT_POLICY",
    "NOT_FOUND",
    "SECTION_META",
    "SELFWORK_NOTES",
    "build_syllabus_editor_section",
]
