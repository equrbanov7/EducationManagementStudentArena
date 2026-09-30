"""Sorğu modulunun sabitləri — seçimlər, icazə açarları, tənzimləmə defoltları.

Tənzimləmə ``Organization.settings["surveys"]`` altında saxlanılır (bax
:mod:`apps.surveys.services.config`); burada yalnız DEFOLT dəyərlər var.
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import pgettext_lazy

_CTX = "surveys.choice"

#: Nəticələrə baxış — əhatə ``get_permission_scope`` ilə həll olunur
#: (kafedra müdiri → öz kafedrası; ORGANIZATION rolları → bütün təşkilat).
PERM_RESULTS_VIEW = "survey.results.view"
#: Kampaniyaların idarəsi (açmaq/bağlamaq/uzatmaq/k-həddi) — yalnız org-wide əhatə ilə.
PERM_MANAGE = "survey.manage"


class Section(models.TextChoices):
    TEACHER = "teacher", pgettext_lazy(_CTX, "Müəllim")
    GENERAL = "general", pgettext_lazy(_CTX, "Ümumi")


class QuestionKind(models.TextChoices):
    LIKERT5 = "likert5", pgettext_lazy(_CTX, "Razılıq şkalası (1–5)")
    SCALE10 = "scale10", pgettext_lazy(_CTX, "Bal şkalası (1–10)")
    TEXT = "text", pgettext_lazy(_CTX, "Sərbəst mətn")
    # Sorğu qurucusu (2026-09-30) — ümumi sorğuların əlavə növləri.
    SINGLE = "single", pgettext_lazy(_CTX, "Tək seçim")
    MULTI = "multi", pgettext_lazy(_CTX, "Çox seçim")
    NPS = "nps", pgettext_lazy(_CTX, "Reytinq / NPS (0–10)")
    YESNO = "yesno", pgettext_lazy(_CTX, "Bəli / Xeyr")
    SHORT_TEXT = "short_text", pgettext_lazy(_CTX, "Qısa mətn")


class CampaignStatus(models.TextChoices):
    DRAFT = "draft", pgettext_lazy(_CTX, "Qaralama")
    OPEN = "open", pgettext_lazy(_CTX, "Açıq")
    CLOSED = "closed", pgettext_lazy(_CTX, "Bağlı")


class OpenedVia(models.TextChoices):
    JOURNAL_CLOSE = "journal_close", pgettext_lazy(_CTX, "Jurnal bağlanması")
    MANUAL = "manual", pgettext_lazy(_CTX, "Əl ilə")


#: Balla qiymətləndirilən növlər və onların diapazonu.
SCORE_RANGES = {QuestionKind.LIKERT5: (1, 5), QuestionKind.SCALE10: (1, 10)}

#: k-anonimlik həddi: nəticə bu saydan AZ cavablı qrup üçün GÖSTƏRİLMİR.
DEFAULT_MIN_GROUP_SIZE = 3
#: Həddin aşağı sərhədi — 1 və ya 2 anonimliyi faktiki ləğv edir (2 cavablı
#: qrupda hər iştirakçı digərinin cavabını hesablaya bilər).
MIN_GROUP_SIZE_FLOOR = 3
MIN_GROUP_SIZE_CEIL = 50

DEFAULT_CLOSE_AFTER_DAYS = 30
DEFAULT_GRACE_DAYS = 3
MAX_CAMPAIGN_DAYS = 180

#: Sərbəst mətn cavabının maksimum uzunluğu (simvol).
TEXT_MAX_LENGTH = 1500

#: ``Organization.settings`` açarları.
SETTINGS_KEY = "surveys"
GATE_SNAPSHOT_KEY = "surveys_gate"

#: Sessiya açarları — gözləyən hədəf sayının keşi və «Sonra doldur» bayrağı.
SESSION_STATE_KEY = "survey_gate_state"
SESSION_DEFER_KEY = "survey_gate_defer"
STATE_TTL_SECONDS = 600
DEFER_SECONDS = 24 * 60 * 60

#: Qapının tətbiq olunduğu hesablar: tələbə ailəsi; `member` neytraldır.
STUDENT_ROLE_NAMES = frozenset({"student", "lead_student"})
NON_STAFF_ROLE_NAMES = STUDENT_ROLE_NAMES | {"member"}

#: Bildiriş hadisəsi (metadata.event).
EVENT_CAMPAIGN_OPENED = "survey_campaign_opened"
AUDIT_RESOURCE_TYPE = "surveys.campaign"


# ── Sorğu qurucusu (2026-09-30) ─────────────────────────────────────────────


class SurveyKind(models.TextChoices):
    #: Mövcud semestr axını (müəllim × fənn, anonim) — sual dəsti kampaniyalarda işlənir.
    TEACHER_EVALUATION = "teacher_evaluation", pgettext_lazy(_CTX, "Müəllim qiymətləndirməsi")
    GENERAL = "general", pgettext_lazy(_CTX, "Ümumi sorğu")
    COURSE_FEEDBACK = "course_feedback", pgettext_lazy(_CTX, "Fənn / kurs rəyi")
    EVENT = "event", pgettext_lazy(_CTX, "Tədbir / digər")


class Audience(models.TextChoices):
    STUDENTS = "students", pgettext_lazy(_CTX, "Tələbələr")
    TEACHERS = "teachers", pgettext_lazy(_CTX, "Müəllimlər")
    STAFF = "staff", pgettext_lazy(_CTX, "İnzibati heyət")
    EVERYONE = "everyone", pgettext_lazy(_CTX, "Hamı")


class GatePolicy(models.TextChoices):
    BLOCK = "block", pgettext_lazy(_CTX, "Doldurulmayınca kabinet bağlıdır")
    SKIP_ONCE = "skip_once", pgettext_lazy(_CTX, "Bir dəfə keçmək olar")
    DEFER_DAYS = "defer_days", pgettext_lazy(_CTX, "«Sonra doldur» möhləti (gün)")


class SurveyStatus(models.TextChoices):
    DRAFT = "draft", pgettext_lazy(_CTX, "Qaralama")
    PUBLISHED = "published", pgettext_lazy(_CTX, "Dərc olunub")
    CLOSED = "closed", pgettext_lazy(_CTX, "Bağlı")
    ARCHIVED = "archived", pgettext_lazy(_CTX, "Arxivdə")


#: Müəllim qiymətləndirməsinin analitikası (indeks, «ümumi bal», tövsiyə) yalnız bu növləri oxuyur.
TEACHER_EVAL_KINDS = (QuestionKind.LIKERT5, QuestionKind.SCALE10, QuestionKind.TEXT)
GENERIC_KINDS = (
    QuestionKind.LIKERT5,
    QuestionKind.SINGLE,
    QuestionKind.MULTI,
    QuestionKind.NPS,
    QuestionKind.YESNO,
    QuestionKind.SHORT_TEXT,
    QuestionKind.TEXT,
)
CHOICE_KINDS = (QuestionKind.SINGLE, QuestionKind.MULTI)
TEXT_KINDS = (QuestionKind.TEXT, QuestionKind.SHORT_TEXT)
#: Rəqəmli cavab diapazonları (``SurveySubmissionAnswer.number``); bəli = 1, xeyr = 0.
NUMBER_RANGES = {
    QuestionKind.LIKERT5: (1, 5),
    QuestionKind.SCALE10: (1, 10),
    QuestionKind.NPS: (0, 10),
    QuestionKind.YESNO: (0, 1),
}

SHORT_TEXT_MAX_LENGTH = 300
QUESTION_TEXT_MAX_LENGTH = 1000
HELP_TEXT_MAX_LENGTH = 300
OPTION_MAX_LENGTH = 200
TITLE_MAX_LENGTH = 200
DESCRIPTION_MAX_LENGTH = 2000
MAX_QUESTIONS = 80
MAX_PAGES = 20
MAX_OPTIONS = 30
MIN_OPTIONS = 2
MAX_FILTER_ITEMS = 60
MAX_DEFER_DAYS = 60
DEFAULT_DEFER_DAYS = 3
#: Kilidli (cavablanmış) sualda mətn düzəlişi «yazı səhvi» səviyyəsində olmalıdır (difflib nisbəti).
TYPO_EDIT_MIN_RATIO = 0.8

#: Ümumi sorğu qapısının sessiya açarları (kampaniyanınkından AYRI — mövcud axın toxunulmur).
SESSION_SURVEY_STATE_KEY = "survey_gate_generic"
SESSION_SURVEY_DEFER_KEY = "survey_gate_generic_defer"
SESSION_SURVEY_SKIP_KEY = "survey_gate_generic_skip"

EVENT_SURVEY_OPENED = "survey_opened"
AUDIT_SURVEY_RESOURCE = "surveys.survey"
