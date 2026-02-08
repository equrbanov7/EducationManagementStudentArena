import base64
from datetime import timezone
import re

from blog.utils import DATA_URL_PNG_RE
from django.core.files.base import ContentFile


# Bu, sual mətnini normallaşdırır: boşluqları təmizləyir, kiçik hərflərə çevirir və çoxlu boşluqları tək boşluğa çevirir.
def _norm(text: str) -> str:
    if not text:
        return ""
    t = text.strip().lower()
    t = re.sub(r"\s+", " ", t)
    return t


# 0, 1, 10, boş/None kimi dəyərlər üçün lazım olan sual sayını qaytarır.

def _effective_needed_count(exam) -> int:
    """
    0 -> hamısı
    1 -> 1
    10 -> 10
    boş/None -> 10 (default)
    """
    total = exam.questions.count()

    val = getattr(exam, "random_question_count", None)
    if val is None:
        return min(10, total)

    try:
        val = int(val)
    except (TypeError, ValueError):
        return min(10, total)

    if val <= 0:
        return total  # 0 -> hamısı

    return min(val, total)

# Tələbənin həqiqətən nəsə yazıb/seçib-seçmədiyini yoxlamaq üçün istifadə olunur.

def _attempt_has_any_answer(attempt) -> bool:
    """
    Tələbə həqiqətən nəsə yazıb/seçibsə True.
    False-positive verməsin deyə count-based yoxlayırıq.
    """
    # text
    if attempt.answers.exclude(text_answer__isnull=True).exclude(text_answer="").exists():
        return True

    # selected options
    if attempt.answers.filter(selected_options__isnull=False).distinct().exists():
        # bu da bəzən false-positive ola bilər, ona görə bir addım da:
        return attempt.answers.filter(selected_options__isnull=False).values("id").distinct().count() > 0

    # files
    if attempt.answers.filter(files__isnull=False).distinct().exists():
        return True

    return False

def _save_paint_png_to_answer(ans, data_url: str):
    """
    data_url format: data:image/png;base64,....
    """
    if not data_url:
        return False

    m = DATA_URL_PNG_RE.match((data_url or "").strip())
    if not m:
        return False

    b64_data = m.group(1)

    # çox böyük payload-ları blokla (təhlükəsizlik)
    if len(b64_data) > 3_500_000:  # ~2.6MB binary civarı
        return False

    try:
        binary = base64.b64decode(b64_data)
    except Exception:
        return False

    filename = f"paint_answer_{ans.id}.png"
    ans.paint_image.save(filename, ContentFile(binary), save=False)
    ans.paint_updated_at = timezone.now()
    ans.has_paint = True
    return True

def _clear_paint_from_answer(ans):
    """
    həm file-i silir, həm field-i null edir
    """
    if ans.paint_image:
        ans.paint_image.delete(save=False)
    ans.paint_image = None
    ans.has_paint = False
    ans.paint_updated_at = timezone.now()