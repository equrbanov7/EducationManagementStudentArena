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
