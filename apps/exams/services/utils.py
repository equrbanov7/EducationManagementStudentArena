import base64

from django.core.files.base import ContentFile
from django.utils import timezone

from apps.blog.utils import DATA_URL_PNG_RE
from apps.exams.services.exam_definition import effective_random_question_count
from apps.exams.services.question_bank import normalize_question_text


def _norm(text: str) -> str:
    return normalize_question_text(text)


def _effective_needed_count(exam) -> int:
    return effective_random_question_count(exam)


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
    ans.paint_data_url = data_url
    return True


def _clear_paint_from_answer(ans):
    """
    həm file-i silir, həm field-i null edir
    """
    if ans.paint_image:
        ans.paint_image.delete(save=False)
    ans.paint_image = None
    ans.has_paint = False
    ans.paint_data_url = None
    ans.paint_updated_at = timezone.now()
