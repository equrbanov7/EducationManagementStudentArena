
import os
import re
from collections import defaultdict
from importlib.readers import ZipReader

from docx import Document
try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None

from exams.constants import ANSWERLINE_RE, OPTION_RE, QUESTION_RE
from exams.services.utils import _norm


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
        raise ValueError("Fayl çox böyükdür (max 5MB).")

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
        if ZipReader is None:
            raise ValueError("PDF oxuma üçün 'pypdf' quraşdırılmayıb. `pip install pypdf` edin.")

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


    raise ValueError("Yalnız .docx, .pdf, .txt qəbul olunur.")


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

        # Correct müəyyən et:
        # 1) option-larda * ilə işarələnənlər
        if not current["correct"]:
            # 2) Cavab: A,C sətri ilə verilənlər
            if current.get("_answerline_correct"):
                current["correct"] = current["_answerline_correct"]

        # 3) Heç biri yoxdursa default A
        if not current["correct"]:
            current["correct"] = ["A"]

        # answer_mode set
        current["answer_mode"] = "multiple" if len(current["correct"]) > 1 else "single"

        # cleanup
        current.pop("_answerline_correct", None)
        questions.append(current)

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
            current = {
                "q_no": m_q.group(1),
                "text": m_q.group(2).strip(),
                "options": {},
                "correct": [],
                "answer_mode": "single",
                "warnings": [],
            }
            state = IN_Q
            continue

        # Əgər artıq sualın içindəyiksə:
        if current:
            # Əgər option bitib və yeni sual başlayırsa
            if state == IN_OPT and m_q and len(current["options"]) >= 4:
                # əvvəlki sualı bağla, yenisini başlat
                close_question()
                current = {
                    "q_no": m_q.group(1),
                    "text": m_q.group(2).strip(),
                    "options": {},
                    "correct": [],
                    "answer_mode": "single",
                    "warnings": [],
                }
                state = IN_Q
                continue
            # IN_Q vəziyyətində və yeni sual gəlirsə
            elif state == IN_Q and m_q and current["options"]:
                close_question()
                current = {
                    "q_no": m_q.group(1),
                    "text": m_q.group(2).strip(),
                    "options": {},
                    "correct": [],
                    "answer_mode": "single",
                    "warnings": [],
                }
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

    # Validations per question
    for q in questions:
        # missing A-D
        for must in ["A", "B", "C", "D"]:
            if must not in q["options"]:
                q["warnings"].append({
                    "type": "missing_option",
                    "msg": f"{must} variantı tapılmadı."
                })

        # E optional warning
        if "E" not in q["options"]:
            q["warnings"].append({
                "type": "missing_option_e",
                "msg": "E variantı yoxdur (opsional)."
            })

        # duplicate options text warning
        norm_map = defaultdict(list)
        for lab, txt in q["options"].items():
            norm_map[_norm(txt)].append(lab)

        dup_groups = [labs for norm_txt, labs in norm_map.items() if norm_txt and len(labs) > 1]
        for labs in dup_groups:
            q["warnings"].append({
                "type": "duplicate_option_text",
                "msg": f"Təkrar variant mətni: {', '.join(labs)} eynidir."
            })

        # correct label exists?
        for c in q["correct"]:
            if c not in q["options"]:
                q["warnings"].append({
                    "type": "correct_missing",
                    "msg": f"Düz cavab kimi işarələnən {c} variantı yoxdur."
                })

    return questions

