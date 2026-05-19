import os
import re
from collections import defaultdict

from django.utils.translation import pgettext

from docx import Document

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

from apps.exams.constants import ANSWERLINE_RE, LABELS, OPTION_RE, QUESTION_RE
from apps.exams.services.utils import _norm

END_QUESTION_RE = re.compile(r"^\s*END_QUESTION\s*$", re.IGNORECASE)
JOINED_OPTION_BOUNDARY_RE = re.compile(r"(?<=[a-zəöüğışç])(?=[A-ZƏÖÜĞİŞÇ])")

# PDF-dən çıxan mətni parser üçün uyğun formaya salır:


def normalize_pdf_extracted_text(text: str) -> str:
    """
    PDF-dən çıxan mətni parser üçün uyğun formaya salır:
    - sual nömrələrinin qabağına boş sətir əlavə edir (… \n\n12) …)
    - A–E variantlarının qabağına newline əlavə edir (… \nA) …)
    - "Cavab:" sətrini yeni sətrə keçirir
    - '*' işarəsi ilə variant arasında boşluğu düzəldir (*A) kimi)
    """
    if not text:
        return ""

    t = text.replace("\r", "\n")

    # çoxlu boşluqları normallaşdır
    t = re.sub(r"[ \t]+", " ", t)

    # "Cavab:" həmişə yeni sətirdən başlasın
    t = re.sub(r"(?i)\s+(Cavab\s*:)", r"\n\1", t)

    # "* A)" kimi çıxırsa "*A)" et
    t = re.sub(r"\*\s+([A-E])", r"*\1", t, flags=re.IGNORECASE)

    # Sual nömrələri: " 12)" və ya " 12." -> yeni blok kimi başlasın
    # (Variant daxilində 1) 2) olsa belə parser artıq IN_OPT-də bunu sual saymır, problem olmur.)
    t = re.sub(r"(?<!\n)\s+(\d{1,4})\s*([\)\.])", r"\n\n\1\2", t)

    # Variantlar: " A)" / " *A)" / " B." və s -> yeni sətirdən başlasın
    t = re.sub(r"(?<!\n)\s+(\*?[A-E])\s*([\)\.])", r"\n\1\2", t, flags=re.IGNORECASE)

    # 3+ boş sətiri 2-yə sal
    t = re.sub(r"\n{3,}", "\n\n", t)

    return t.strip()


# Yüklənmiş fayldan mətn çıxarır. Dəstəklənən formatlar: .txt, .docx, .pdf


def extract_text_from_upload(uploaded_file) -> str:
    name = uploaded_file.name.lower()
    ext = os.path.splitext(name)[1]

    # təhlükəsizlik: böyük fayl limiti (məs: 5MB)
    if uploaded_file.size > 5 * 1024 * 1024:
        raise ValueError(pgettext("exams.service.parsing.error", "file_too_large"))

    if ext == ".txt":
        return uploaded_file.read().decode("utf-8", errors="ignore")

    if ext == ".docx":
        # docx.Document file-like də qəbul edir
        doc = Document(uploaded_file)
        lines = []
        for p in doc.paragraphs:
            t = (p.text or "").strip()
            if t:
                lines.append(t)
        return "\n".join(lines)

    if ext == ".pdf":
        if PdfReader is None:
            raise ValueError(pgettext("exams.service.parsing.error", "pdf_dependency_missing"))

        uploaded_file.seek(0)
        reader = PdfReader(uploaded_file)
        parts = []
        for page in reader.pages:
            txt = page.extract_text() or ""
            txt = txt.strip()
            if txt:
                parts.append(txt)

        raw = "\n\n".join(parts)

        # ✅ əsas fix burada
        return normalize_pdf_extracted_text(raw)

    raise ValueError(pgettext("exams.service.parsing.error", "unsupported_file_type"))


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
        current["correct"] = ["A"]

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


def _parse_unlabeled_end_question_block(lines: list[str], fallback_no: int) -> dict | None:
    if len(lines) < 2:
        return None

    q_idx = _question_line_index(lines)
    q_no, q_text = _strip_question_number(lines[q_idx], fallback_no)
    option_lines = lines[q_idx + 1 :]

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

    for raw in raw_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if END_QUESTION_RE.match(line):
            flush_block()
            continue
        block.append(line)

    flush_block()
    return questions


def _validate_questions(questions: list[dict]) -> None:
    for q in questions:
        # missing A-D
        for must in ["A", "B", "C", "D"]:
            if must not in q["options"]:
                q["warnings"].append(
                    {
                        "type": "missing_option",
                        "msg": pgettext("exams.service.parsing.warning", "missing_option").format(option=must),
                    }
                )

        # E optional warning
        if "E" not in q["options"]:
            q["warnings"].append(
                {
                    "type": "missing_option_e",
                    "msg": pgettext("exams.service.parsing.warning", "missing_option_e"),
                }
            )

        # duplicate options text warning
        norm_map = defaultdict(list)
        for lab, txt in q["options"].items():
            norm_map[_norm(txt)].append(lab)

        dup_groups = [labs for norm_txt, labs in norm_map.items() if norm_txt and len(labs) > 1]
        for labs in dup_groups:
            q["warnings"].append(
                {
                    "type": "duplicate_option_text",
                    "msg": pgettext("exams.service.parsing.warning", "duplicate_option_text").format(
                        labels=", ".join(labs)
                    ),
                }
            )

        # correct label exists?
        for c in q["correct"]:
            if c not in q["options"]:
                q["warnings"].append(
                    {
                        "type": "correct_missing",
                        "msg": pgettext("exams.service.parsing.warning", "correct_missing").format(option=c),
                    }
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
