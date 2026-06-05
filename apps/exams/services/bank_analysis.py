"""
Saxlanmış imtahan sual bankının keyfiyyət analizi.

Bu servis ``test_question_bank`` import preview-undakı (parsing._validate_questions)
eyni yoxlama məntiqini artıq bazada saxlanmış ``ExamQuestion`` obyektlərinə tətbiq
edir. Məqsəd: müəllimə sual bankında dublikat, variant problemi, uzunluq balansı və
digər xəbərdarlıqları göstərmək, eyni zamanda Excel hesabatı üçün ``parsed``-bənzər
struktur hazırlamaq.

Yalnız test (MCQ) imtahanları üçün mənalıdır — yazılı/praktiki imtahanlarda variant
strukturu olmadığı üçün analiz boş qaytarılır.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from apps.exams.services.parsing import _validate_questions
from apps.exams.services.utils import _norm

# Severity prioriteti: error > warning > info > none
_SEVERITY_ORDER = ("error", "warning", "info")

# Bank daxili dublikat üçün xəbərdarlıq tipi (import-dakı "duplicate_in_import"-un
# bank ekvivalenti). Report etiketləri question_bank view-dakı lüğətlərdə var.
DUPLICATE_IN_BANK = "duplicate_in_bank"

_STRUCTURE_TYPES = {
    "missing_option",
    "option_count_recommend_5",
    "option_count_too_low",
    "empty_option_text",
}
_BALANCE_TYPES = {"correct_too_long", "correct_too_short"}
_DUPLICATE_TYPES = {DUPLICATE_IN_BANK, "duplicate_in_import", "already_in_exam"}


@dataclass
class QuestionBankAnalysis:
    """Bütün bank üzrə analizin nəticəsi."""

    analysis_by_id: dict = field(default_factory=dict)
    flagged_ids: dict = field(default_factory=dict)
    parsed_for_report: list = field(default_factory=list)
    category_counts: dict = field(default_factory=dict)
    error_count: int = 0
    warning_count: int = 0
    duplicate_count: int = 0
    clean_count: int = 0
    total_analyzed: int = 0
    enabled: bool = False


def _empty_analysis() -> QuestionBankAnalysis:
    return QuestionBankAnalysis(
        category_counts={
            "errors": 0,
            "warnings": 0,
            "duplicates": 0,
            "structure": 0,
            "balance": 0,
            "clean": 0,
        },
        flagged_ids={
            "has-error": set(),
            "has-warning": set(),
            "has-dup": set(),
            "has-structure": set(),
            "has-balance": set(),
            "is-clean": set(),
        },
        enabled=False,
    )


def _options_map(question) -> tuple[dict, list]:
    """ExamQuestion variantlarını {label: text} formatına çevirir.

    Variantda ``label`` (A-E) varsa ondan istifadə edirik, yoxdursa sıraya görə
    A..E veririk (import dublikat fingerprint məntiqi ilə eyni).
    """
    labels = list("ABCDE")
    options = list(question.options.all())
    opt_map: dict[str, str] = {}
    correct: list[str] = []
    for index, opt in enumerate(options[:5]):
        label = (opt.label or "").strip().upper() or labels[index]
        opt_map[label] = opt.text or ""
        if opt.is_correct:
            correct.append(label)
    return opt_map, correct


def _fingerprint(text: str, opt_map: dict) -> str:
    return _norm(text) + "||" + "||".join(_norm(opt_map.get(x, "")) for x in "ABCDE")


def _short_preview(text: str, length: int = 60) -> str:
    clean = (text or "").strip().replace("\n", " ")
    if len(clean) <= length:
        return clean
    return clean[: length - 1].rstrip() + "…"


def build_question_meta(warnings: list) -> dict:
    """Bir sualın xəbərdarlıqlarından UI üçün meta xülasə qurur.

    test_question_bank view-dakı meta strukturu ilə eyni açarları qaytarır ki,
    template-lər arasında davranış uyğun olsun.
    """
    counts = {"error": 0, "warning": 0, "info": 0}
    types: set[str] = set()
    for w in warnings or []:
        sev = w.get("severity", "warning")
        if sev in counts:
            counts[sev] += 1
        types.add(w.get("type"))

    top_sev = "none"
    for sev in _SEVERITY_ORDER:
        if counts[sev]:
            top_sev = sev
            break

    has_dup = bool(_DUPLICATE_TYPES & types)
    has_structure = bool(_STRUCTURE_TYPES & types)
    has_balance = bool(_BALANCE_TYPES & types)

    flags = " ".join(
        filter(
            None,
            [
                f"sev-{top_sev}" if top_sev != "none" else "sev-clean",
                "has-dup" if has_dup else "",
                "has-structure" if has_structure else "",
                "has-balance" if has_balance else "",
                "has-error" if counts["error"] else "",
                "has-warning" if counts["warning"] else "",
                "has-info" if counts["info"] else "",
                "is-clean" if not warnings else "",
            ],
        )
    )

    return {
        "top_severity": top_sev,
        "error_count": counts["error"],
        "warning_count": counts["warning"],
        "info_count": counts["info"],
        "total_count": counts["error"] + counts["warning"] + counts["info"],
        "has_duplicate": has_dup,
        "has_structure_issue": has_structure,
        "has_balance_issue": has_balance,
        "flags": flags,
    }


def analyze_question_bank(exam) -> QuestionBankAnalysis:
    """Bütün imtahan bankını analiz edir və UI/report üçün nəticə qaytarır.

    Yalnız ``exam.exam_type == "test"`` üçün işləyir; əks halda boş (enabled=False)
    nəticə qaytarır.
    """
    if getattr(exam, "exam_type", None) != "test":
        return _empty_analysis()

    questions = list(exam.questions.prefetch_related("options").order_by("order", "id"))
    if not questions:
        result = _empty_analysis()
        result.enabled = True
        return result

    # 1) Hər sual üçün parser strukturunu qur
    parsed: list[dict] = []
    fp_groups: dict[str, list[int]] = {}
    for position, question in enumerate(questions, start=1):
        opt_map, correct = _options_map(question)
        parsed.append(
            {
                "db_id": question.id,
                "q_no": question.order or position,
                "order": question.order or position,
                "position": position,
                "text": question.text or "",
                "options": opt_map,
                "correct": correct,
                "warnings": [],
            }
        )
        fp_groups.setdefault(_fingerprint(question.text or "", opt_map), []).append(position)

    # 2) Per-sual validasiya (parsing servisini təkrar istifadə)
    _validate_questions(parsed)

    # 3) Bank daxili dublikat aşkarlanması (eyni mətn + variant fingerprint)
    for indices in fp_groups.values():
        if len(indices) < 2:
            continue
        for position in enumerate(indices):
            others = [i for i in indices if i != position]
            primary_ref = others[0]
            primary_q = parsed[primary_ref - 1]
            primary_order = primary_q["order"]
            preview = _short_preview(primary_q["text"])
            msg = (
                f"Bu sual bankda başqa sualla eynidir "
                f"(sıra #{primary_order}: “{preview}”). Təkrarlardan birini silin "
                f"və ya mətnləri fərqləndirin."
            )
            parsed[position - 1]["warnings"].append(
                {
                    "type": DUPLICATE_IN_BANK,
                    "severity": "error",
                    "msg": msg,
                    "ref": primary_ref,
                    "ref_db_id": primary_q["db_id"],
                    "ref_db_order": primary_order,
                    "all_refs": others,
                }
            )

    # 4) Meta + kateqoriya aqreqasiyası
    category_counts = {
        "errors": 0,
        "warnings": 0,
        "duplicates": 0,
        "structure": 0,
        "balance": 0,
        "clean": 0,
    }
    flagged_ids = {
        "has-error": set(),
        "has-warning": set(),
        "has-dup": set(),
        "has-structure": set(),
        "has-balance": set(),
        "is-clean": set(),
    }
    analysis_by_id: dict[int, dict] = {}

    for q in parsed:
        warnings = q.get("warnings") or []
        meta = build_question_meta(warnings)
        q["meta"] = meta
        db_id = q["db_id"]
        analysis_by_id[db_id] = {"warnings": warnings, "meta": meta}

        if meta["error_count"]:
            category_counts["errors"] += 1
            flagged_ids["has-error"].add(db_id)
        if meta["warning_count"]:
            category_counts["warnings"] += 1
            flagged_ids["has-warning"].add(db_id)
        if meta["has_duplicate"]:
            category_counts["duplicates"] += 1
            flagged_ids["has-dup"].add(db_id)
        if meta["has_structure_issue"]:
            category_counts["structure"] += 1
            flagged_ids["has-structure"].add(db_id)
        if meta["has_balance_issue"]:
            category_counts["balance"] += 1
            flagged_ids["has-balance"].add(db_id)
        if not warnings:
            category_counts["clean"] += 1
            flagged_ids["is-clean"].add(db_id)

    # Üst panel sayları: info yumşaq qeyddir, sayılmır
    warning_count = sum(1 for q in parsed for w in q["warnings"] if w.get("severity", "warning") != "info")

    return QuestionBankAnalysis(
        analysis_by_id=analysis_by_id,
        flagged_ids=flagged_ids,
        parsed_for_report=parsed,
        category_counts=category_counts,
        error_count=category_counts["errors"],
        warning_count=warning_count,
        duplicate_count=category_counts["duplicates"],
        clean_count=category_counts["clean"],
        total_analyzed=len(parsed),
        enabled=True,
    )
