"""Sual blok parsinqi, validasiya və parse_bulk_mcq orkestrasiyası.
parsing paketinin nüvə alt-modulu — `extraction`-dan yalnız lazım olan
köməkçiləri import edir (tək-istiqamətli asılılıq, dövr yoxdur).
"""

import logging
import re
from collections import defaultdict

from django.utils.translation import pgettext

from apps.exams.constants import ANSWERLINE_RE, LABELS, OPTION_RE, QUESTION_RE
from apps.exams.services.utils import _norm

from .extraction import (
    END_QUESTION_RE,
    JOINED_OPTION_BOUNDARY_RE,
    _convert_marker_options,
    _merge_bare_question_numbers,
    _normalize_cyrillic_option_labels,
)

logger = logging.getLogger(__name__)

# PDF mətn qatında END_QUESTION çox vaxt sonuncu variantın SONUNA yapışır
# ("...işləyir. END_QUESTION"). END_QUESTION_RE yalnız müstəqil sətri tanıyır,
# ona görə markerlər əvvəlcə ayrıca sətrə çıxarılmalıdır — əks halda bloklar
# heç vaxt bağlanmır və sənədin böyük hissəsi bir "sual"a yapışıb itir.
_INLINE_END_QUESTION_RE = re.compile(r"[ \t]*\bEND_QUESTION\b[ \t]*", re.IGNORECASE)


def _isolate_end_question_markers(raw_text: str) -> str:
    if "END_QUESTION" not in raw_text.upper():
        return raw_text
    return _INLINE_END_QUESTION_RE.sub("\nEND_QUESTION\n", raw_text)


def _new_question(q_no: str, text: str) -> dict:
    return {
        "q_no": q_no,
        "text": text.strip(),
        "options": {},
        "correct": [],
        "answer_mode": "single",
        "warnings": [],
    }


def _strip_question_number(line: str, fallback_no: int) -> tuple[str, str]:
    m_q = QUESTION_RE.match(line)
    if m_q:
        return m_q.group(1), m_q.group(2).strip()
    return str(fallback_no), line.strip()


def _finish_question(current: dict | None) -> dict | None:
    if not current:
        return None

    if not current["correct"] and current.get("_answerline_correct"):
        current["correct"] = current["_answerline_correct"]

    if not current["correct"]:
        # Mətn içində düzgün cavab işarəsi tapılmadı — "A" yalnız texniki
        # default-dur, real cavab açarı deyil. Müəllim workbench-də mütləq
        # görsün deyə ERROR severity ilə xəbərdarlıq qoyulur.
        current["correct"] = ["A"]
        _add_warning(
            current,
            "correct_defaulted",
            pgettext("exams.service.parsing.warning", "correct_defaulted"),
            severity=SEVERITY_ERROR,
        )

    current["answer_mode"] = "multiple" if len(current["correct"]) > 1 else "single"
    current.pop("_answerline_correct", None)
    return current


def _is_option_continuation(line: str) -> bool:
    if not line:
        return False
    return line[0].islower() or line[0] in ",;:-)]}"


def _coerce_unlabeled_options(option_lines: list[str]) -> list[str]:
    cleaned = [line.strip() for line in option_lines if line.strip()]
    if len(option_lines) <= len(LABELS):
        while len(cleaned) < len(LABELS):
            for idx in range(len(cleaned) - 1, -1, -1):
                parts = JOINED_OPTION_BOUNDARY_RE.split(cleaned[idx], maxsplit=1)
                if len(parts) == 2 and all(len(part.strip()) > 2 for part in parts):
                    cleaned[idx : idx + 1] = [parts[0].strip(), parts[1].strip()]
                    break
            else:
                break
        return cleaned

    options: list[str] = []
    total = len(option_lines)

    for idx, line in enumerate(option_lines):
        text = line.strip()
        if not text:
            continue

        remaining_lines = total - idx
        remaining_slots_after_new_option = len(LABELS) - len(options) - 1
        can_start_new_option = len(options) < len(LABELS) and remaining_lines - 1 >= remaining_slots_after_new_option

        if options and _is_option_continuation(text):
            options[-1] += " " + text
        elif can_start_new_option:
            options.append(text)
        elif options:
            options[-1] += " " + text

    return options[: len(LABELS)]


def _question_line_index(lines: list[str]) -> int:
    last_possible_question_index = max(0, len(lines) - len(LABELS))
    for idx in range(last_possible_question_index, -1, -1):
        line = lines[idx]
        if QUESTION_RE.match(line) or "?" in line:
            return idx
    if len(lines) > len(LABELS):
        return len(lines) - len(LABELS) - 1
    return 0


def _looks_like_question_prompt(line: str) -> bool:
    text = (line or "").strip()
    if not text:
        return False

    lower = text.lower()
    question_markers = (
        "?",
        ":",
        # az
        "hansı",
        "hansıdır",
        "hansidir",
        "nədir",
        "nedir",
        "nəyi",
        "neyi",
        "kimdir",
        "harada",
        "necə",
        "nece",
        "aiddir",
        "aid edilir",
        "istifadə",
        "istifade",
        "aşağıdakı",
        "asagidaki",
        # en
        "which",
        "what",
        "following",
        # ru
        "какой",
        "какая",
        "какое",
        "которы",
        "что такое",
        "является",
        "следующ",
        # tr
        "hangisi",
        "aşağıdaki",
        "nelerdir",
    )
    return any(marker in lower for marker in question_markers)


def _split_unlabeled_question_and_options(lines: list[str], q_idx: int) -> tuple[list[str], list[str]]:
    question_lines = [lines[q_idx]]
    option_start = q_idx + 1

    while option_start < len(lines) and len(lines) - option_start > len(LABELS):
        candidate = lines[option_start]
        if not _looks_like_question_prompt(candidate):
            break
        question_lines.append(candidate)
        option_start += 1

    return question_lines, lines[option_start:]


def _parse_unlabeled_end_question_block(lines: list[str], fallback_no: int) -> dict | None:
    if len(lines) < 2:
        return None

    q_idx = _question_line_index(lines)
    question_lines, option_lines = _split_unlabeled_question_and_options(lines, q_idx)
    q_no, q_text = _strip_question_number(" ".join(question_lines), fallback_no)

    if len(option_lines) < 2:
        return None

    options = _coerce_unlabeled_options(option_lines)
    current = _new_question(q_no, q_text)
    for label, option_text in zip(LABELS, options, strict=False):
        current["options"][label] = option_text

    return _finish_question(current)


def _parse_labeled_end_question_block(lines: list[str], fallback_no: int) -> dict | None:
    question_lines: list[str] = []
    current = None
    current_opt_label = None

    for line in lines:
        m_ans = ANSWERLINE_RE.match(line)
        if m_ans and current:
            labels = re.split(r"\s*[,;/]\s*", m_ans.group(2).upper())
            seen = set()
            current["_answerline_correct"] = [
                label for label in labels if label in LABELS and not (label in seen or seen.add(label))
            ]
            continue

        m_opt = OPTION_RE.match(line)
        if m_opt:
            if current is None:
                question_text = " ".join(question_lines).strip()
                if not question_text:
                    return None
                q_no, q_text = _strip_question_number(question_text, fallback_no)
                current = _new_question(q_no, q_text)

            star = bool(m_opt.group(1))
            label = m_opt.group(2).upper()
            text = m_opt.group(3).strip()
            current["options"][label] = text
            current_opt_label = label
            if star and label not in current["correct"]:
                current["correct"].append(label)
            continue

        if current is not None and current_opt_label:
            current["options"][current_opt_label] += " " + line.strip()
        elif current is not None:
            current["text"] += " " + line.strip()
        else:
            question_lines.append(line.strip())

    return _finish_question(current)


def _parse_end_question_blocks(raw_text: str) -> list[dict]:
    questions = []
    block: list[str] = []

    def flush_block() -> None:
        nonlocal block
        if not block:
            return

        fallback_no = len(questions) + 1
        parser = (
            _parse_labeled_end_question_block
            if any(OPTION_RE.match(line) for line in block)
            else _parse_unlabeled_end_question_block
        )
        parsed = parser(block, fallback_no)
        if parsed:
            questions.append(parsed)
        block = []

    def _block_has_option(current_block):
        return any(OPTION_RE.match(entry) for entry in current_block)

    for raw in raw_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if END_QUESTION_RE.match(line):
            flush_block()
            continue
        # END_QUESTION unudulmuş sual: variantlardan SONRA yeni "N." sual
        # sətri gəlirsə bu, faktiki yeni blokdur — əvvəlkini bağlayırıq ki,
        # iki sual bir-birinə yapışıb itməsin.
        if block and _block_has_option(block) and QUESTION_RE.match(line) and not OPTION_RE.match(line):
            flush_block()
        block.append(line)

    flush_block()
    return questions


# Severity səviyyələri — UI-da rəngləməni və "blok edirmi?" qərarını bunlara görə veririk
SEVERITY_ERROR = "error"  # qırmızı — saxlanışı blok etməyə bilər, amma diqqət vacibdir
SEVERITY_WARNING = "warning"  # sarı — informativ xəbərdarlıq
SEVERITY_INFO = "info"  # mavi — sadəcə yumşaq qeyd


def _add_warning(q: dict, w_type: str, msg: str, severity: str = SEVERITY_WARNING, **extra) -> None:
    payload = {"type": w_type, "msg": msg, "severity": severity}
    payload.update(extra)
    q["warnings"].append(payload)


def _validate_questions(questions: list[dict]) -> None:
    for q in questions:
        opts = q.get("options", {}) or {}

        # missing A-D — bunlar minimum tələbdir, ERROR
        for must in ["A", "B", "C", "D"]:
            if must not in opts:
                _add_warning(
                    q,
                    "missing_option",
                    pgettext("exams.service.parsing.warning", "missing_option").format(option=must),
                    severity=SEVERITY_ERROR,
                )

        # Variant sayı: standart 5 (A-E). 4 olarsa — sarı warning, 3 və daha az — minimum_option warning-i artıq qoyulub.
        present_labels = [lab for lab in ["A", "B", "C", "D", "E"] if lab in opts]
        option_count = len(present_labels)
        if option_count == 4 and "E" not in opts:
            _add_warning(
                q,
                "option_count_recommend_5",
                pgettext("exams.service.parsing.warning", "option_count_recommend_5").format(count=option_count),
                severity=SEVERITY_WARNING,
            )
        elif option_count < 4:
            # missing A/B/C/D artıq error verdi — bunu info səviyyəsində əlavə eləyirik
            _add_warning(
                q,
                "option_count_too_low",
                pgettext("exams.service.parsing.warning", "option_count_too_low").format(count=option_count),
                severity=SEVERITY_ERROR,
            )

        # duplicate options text warning
        norm_map = defaultdict(list)
        for lab, txt in opts.items():
            norm_map[_norm(txt)].append(lab)

        dup_groups = [labs for norm_txt, labs in norm_map.items() if norm_txt and len(labs) > 1]
        for labs in dup_groups:
            _add_warning(
                q,
                "duplicate_option_text",
                pgettext("exams.service.parsing.warning", "duplicate_option_text").format(labels=", ".join(labs)),
                severity=SEVERITY_WARNING,
            )

        # correct label exists?
        for c in q.get("correct", []):
            if c not in opts:
                _add_warning(
                    q,
                    "correct_missing",
                    pgettext("exams.service.parsing.warning", "correct_missing").format(option=c),
                    severity=SEVERITY_ERROR,
                )

        # boş və ya çox qısa variant mətnləri (UX faydası: spam/yanlış parse halı)
        for lab in present_labels:
            txt = (opts.get(lab) or "").strip()
            if not txt:
                _add_warning(
                    q,
                    "empty_option_text",
                    pgettext("exams.service.parsing.warning", "empty_option_text").format(option=lab),
                    severity=SEVERITY_ERROR,
                )

        # uzunluq/balans xəbərdarlığı — yalnız doğru cavabı çox uzun/qısa olduqda
        correct_labels = [c for c in q.get("correct", []) if c in opts]
        wrong_labels = [lab for lab in present_labels if lab not in correct_labels]
        if correct_labels and wrong_labels:
            correct_lengths = [len((opts.get(c) or "").strip()) for c in correct_labels]
            wrong_lengths = [len((opts.get(w) or "").strip()) for w in wrong_labels]
            if correct_lengths and wrong_lengths:
                max_correct = max(correct_lengths)
                max_wrong = max(wrong_lengths)
                avg_wrong = sum(wrong_lengths) / max(1, len(wrong_lengths))
                # yalnız doğru cavab çox uzundursa (≥1.8x ortalama yanlışdan və ≥15 simvol)
                if max_correct >= 15 and avg_wrong > 0 and max_correct >= avg_wrong * 1.8:
                    _add_warning(
                        q,
                        "correct_too_long",
                        pgettext("exams.service.parsing.warning", "correct_too_long"),
                        severity=SEVERITY_INFO,
                    )
                # və ya yalnız doğru cavab çox qısadır (≤0.4x və yanlışlar uzundur)
                elif max_wrong >= 15 and max_correct > 0 and max_correct <= avg_wrong * 0.4:
                    _add_warning(
                        q,
                        "correct_too_short",
                        pgettext("exams.service.parsing.warning", "correct_too_short"),
                        severity=SEVERITY_INFO,
                    )


# PDF-dən çıxan və ya digər mənbədən alınan raw mətni parser üçün strukturlaşdırılmış sual formatına çevirir


def parse_bulk_mcq(raw_text: str):
    """
    Output:
      questions: list[
        {
          "q_no": "12" (mətn içindəki nömrə),
          "text": "...",
          "options": {"A": "...", ..., "E": "..."},
          "correct": ["A"] or ["A","C"],
          "answer_mode": "single"|"multiple",
          "warnings": [ {type, msg, ref?}, ... ]
        }
      ]
    """
    # Ön-emal: kiril etiketləri (rus tərcümələri), tək qalmış sual nömrələri
    # və bullet/√ markerləri parserin tanıdığı "A) / *B)" formasına salınır.
    raw_text = _normalize_cyrillic_option_labels(raw_text or "")
    raw_text = _isolate_end_question_markers(raw_text)
    raw_text = _merge_bare_question_numbers(raw_text)
    raw_text = _convert_marker_options(raw_text)

    if any(END_QUESTION_RE.match(line) for line in raw_text.splitlines()):
        questions = _parse_end_question_blocks(raw_text)
        if questions:
            _validate_questions(questions)
            return questions

    lines = raw_text.splitlines()
    OUTSIDE, IN_Q, IN_OPT = 0, 1, 2

    state = OUTSIDE
    current = None
    current_opt_label = None

    def close_option():
        nonlocal current_opt_label
        current_opt_label = None

    def close_question():
        nonlocal current, current_opt_label, state
        if not current:
            return
        close_option()

        finished = _finish_question(current)
        if finished:
            questions.append(finished)

        current = None
        current_opt_label = None
        state = OUTSIDE

    questions = []

    for raw in lines:
        line = raw.rstrip("\n")
        if not line.strip():
            continue

        # Answer line (istənilən yerdə ola bilər)
        m_ans = ANSWERLINE_RE.match(line)
        if m_ans and current:
            labels = re.split(r"\s*[,;/]\s*", m_ans.group(2).upper())
            labels = [x for x in labels if x in list("ABCDE")]
            # uniq preserve order
            seen = set()
            uniq = []
            for x in labels:
                if x not in seen:
                    uniq.append(x)
                    seen.add(x)
            current["_answerline_correct"] = uniq
            continue

        # OPTION?
        m_opt = OPTION_RE.match(line)
        if m_opt and current:
            star = bool(m_opt.group(1))
            label = m_opt.group(2).upper()
            text = m_opt.group(3).strip()

            current["options"][label] = text
            current_opt_label = label
            state = IN_OPT
            if star and label not in current["correct"]:
                current["correct"].append(label)
            continue

        # QUESTION START?
        m_q = QUESTION_RE.match(line)

        if state == OUTSIDE and m_q:
            # yeni sual
            current = _new_question(m_q.group(1), m_q.group(2).strip())
            state = IN_Q
            continue

        # Əgər artıq sualın içindəyiksə:
        if current:
            # Əgər option bitib və yeni sual başlayırsa
            if state == IN_OPT and m_q and len(current["options"]) >= 4:
                # əvvəlki sualı bağla, yenisini başlat
                close_question()
                current = _new_question(m_q.group(1), m_q.group(2).strip())
                state = IN_Q
                continue
            # IN_Q vəziyyətində və yeni sual gəlirsə
            elif state == IN_Q and m_q and current["options"]:
                close_question()
                current = _new_question(m_q.group(1), m_q.group(2).strip())
                state = IN_Q
                continue

            # Əks halda bu sətir ya sualın davamıdır, ya da variantın davamıdır
            if state == IN_OPT and current_opt_label:
                current["options"][current_opt_label] += " " + line.strip()
            else:
                current["text"] += " " + line.strip()
        else:
            # OUTSIDE ikən sual formatına düşməyən mətn → ignore
            pass

    # axırı bağla
    if current:
        close_question()

    _validate_questions(questions)

    return questions
