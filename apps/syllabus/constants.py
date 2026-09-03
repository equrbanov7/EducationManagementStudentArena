"""Sillabus axınının SABİTLƏRİ — status kataloqu, bölmə kataloqu, siyasət limitləri.

Bu modul dizayn təhvil paketinin (`design_handoff_sillabus/README.md`) §3.1, §3.2
və §4 cədvəllərinin YEGANƏ kod qarşılığıdır. Status açarı, etiketi və rəng
tokenləri, bölmə ``id``-ləri və validasiya limitləri BURADA saxlanılır ki,
model, servis, API və şablon eyni mənbədən oxusun.

⚠️ Rəng HARDCODE edilmir: cədvəllərdə `--ems-*` TOKEN ADLARI saxlanılır
(`static/css/design-tokens.css`). README §1-in bilinən ziddiyyəti burada da
qorunur — «təsdiqlənib» MƏTNİ ``--ems-success-700`` (#15803d, AA keçir),
``--ems-success`` isə yalnız ikon/accent tokenidir.
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import pgettext_lazy

_STATUS_CTX = "syllabus.status"
_SECTION_CTX = "syllabus.section"
_NEXT_CTX = "syllabus.next_step"
_SELFWORK_CTX = "syllabus.selfwork"


class SyllabusStatus(models.TextChoices):
    """7 status — README §3.1 cədvəli ilə açar/etiket üzrə EYNİ."""

    DRAFT = "draft", pgettext_lazy(_STATUS_CTX, "Qaralama")
    SUBMITTED = "submitted", pgettext_lazy(_STATUS_CTX, "Təqdim edilib")
    REVIEW = "review", pgettext_lazy(_STATUS_CTX, "Baxışdadır")
    REVISION = "revision", pgettext_lazy(_STATUS_CTX, "Düzəliş tələb olunur")
    APPROVED = "approved", pgettext_lazy(_STATUS_CTX, "Təsdiqlənib")
    REJECTED = "rejected", pgettext_lazy(_STATUS_CTX, "Rədd edilib")
    ARCHIVED = "archived", pgettext_lazy(_STATUS_CTX, "Arxivlənib")


#: Statusa görə sıralama ardıcıllığı (README §3.1): əməl tələb edən əvvəl.
STATUS_SORT_ORDER = (
    SyllabusStatus.REVISION,
    SyllabusStatus.REJECTED,
    SyllabusStatus.DRAFT,
    SyllabusStatus.SUBMITTED,
    SyllabusStatus.REVIEW,
    SyllabusStatus.APPROVED,
    SyllabusStatus.ARCHIVED,
)

#: Status → sıra nömrəsi (queryset `Case/When` və Python sort üçün).
STATUS_SORT_INDEX = {status.value: index for index, status in enumerate(STATUS_SORT_ORDER)}

#: Status → (fon, mətn, accent) TOKEN adları. README §3.1 rəng cədvəli.
STATUS_TOKENS = {
    SyllabusStatus.DRAFT.value: ("--ems-neutral-100", "--ems-neutral-700", "--ems-neutral-300"),
    SyllabusStatus.SUBMITTED.value: ("--ems-primary-100", "--ems-primary-800", "--ems-primary-600"),
    SyllabusStatus.REVIEW.value: ("--ems-primary-50", "--ems-primary-800", "--ems-primary-600"),
    SyllabusStatus.REVISION.value: ("--ems-warning-bg", "--ems-warning-800", "--ems-warning"),
    SyllabusStatus.APPROVED.value: ("--ems-success-bg", "--ems-success-700", "--ems-success"),
    SyllabusStatus.REJECTED.value: ("--ems-danger-bg", "--ems-danger-strong", "--ems-danger"),
    SyllabusStatus.ARCHIVED.value: ("--ems-neutral-100", "--ems-neutral-500", "--ems-neutral-200"),
}

#: Status → «növbəti addım» mətni (README §3.1, sətir altında göstərilir).
STATUS_NEXT_STEP = {
    SyllabusStatus.DRAFT.value: pgettext_lazy(_NEXT_CTX, "Qaralamanı tamamlayıb təsdiqə göndər"),
    SyllabusStatus.SUBMITTED.value: pgettext_lazy(_NEXT_CTX, "Kafedra müdirinin baxışı gözlənilir"),
    SyllabusStatus.REVIEW.value: pgettext_lazy(_NEXT_CTX, "Baxış nəticəsi gözlənilir"),
    SyllabusStatus.REVISION.value: pgettext_lazy(_NEXT_CTX, "Kafedra qeydlərini nəzərə alıb yenidən göndər"),
    SyllabusStatus.APPROVED.value: pgettext_lazy(_NEXT_CTX, "Əməl tələb olunmur — versiya kilidlidir"),
    SyllabusStatus.REJECTED.value: pgettext_lazy(_NEXT_CTX, "Rədd səbəbini oxuyub yeni versiya yarat"),
    SyllabusStatus.ARCHIVED.value: pgettext_lazy(_NEXT_CTX, "Arxiv qeydi — yalnız baxış"),
}

#: Redaktəyə AÇIQ statuslar. Qalan hər status kilidlidir (APPROVED daxil).
EDITABLE_STATUSES = frozenset({SyllabusStatus.DRAFT.value, SyllabusStatus.REVISION.value})

#: Kafedra növbəsində görünən statuslar.
QUEUE_STATUSES = frozenset({SyllabusStatus.SUBMITTED.value, SyllabusStatus.REVIEW.value})

#: «Açıq» (hələ qərar verilməmiş) statuslar — bir sillabusda YALNIZ BİRİ ola bilər.
OPEN_STATUSES = frozenset(
    {
        SyllabusStatus.DRAFT.value,
        SyllabusStatus.SUBMITTED.value,
        SyllabusStatus.REVIEW.value,
        SyllabusStatus.REVISION.value,
    }
)

#: Səbəbin MƏCBURİ olduğu statuslar (README §4). DB CheckConstraint ilə də qorunur.
REASON_REQUIRED_STATUSES = frozenset({SyllabusStatus.REVISION.value, SyllabusStatus.REJECTED.value})


class SectionKey(models.TextChoices):
    """Redaktorun 10 bölməsi — ``id`` dəyərləri README §3.2 ilə EYNİ."""

    INFO = "info", pgettext_lazy(_SECTION_CTX, "Ümumi məlumat")
    DESC = "desc", pgettext_lazy(_SECTION_CTX, "Fənnin təsviri və məqsədi")
    OUT = "out", pgettext_lazy(_SECTION_CTX, "Təlim nəticələri")
    WEEK = "week", pgettext_lazy(_SECTION_CTX, "Həftəlik mövzular")
    METHOD = "method", pgettext_lazy(_SECTION_CTX, "Tədris metodları")
    ASSESS = "assess", pgettext_lazy(_SECTION_CTX, "Qiymətləndirmə strukturu")
    SELF = "self", pgettext_lazy(_SECTION_CTX, "Sərbəst iş strukturu")
    LIT = "lit", pgettext_lazy(_SECTION_CTX, "Əsas və əlavə ədəbiyyat")
    # Dizayn mock-unda bu bölmənin adı ingiliscə «Preview»-dur; AZ etiketi
    # mock-un ÖZ izah mətnindən götürülüb («Sillabusun yekun görünüşü»), çünki
    # AZ interfeysdə ingilis sözü qalmamalıdır. Bölmə `id`-si dəyişməyib.
    PREV = "prev", pgettext_lazy(_SECTION_CTX, "Yekun görünüş")
    SEND = "send", pgettext_lazy(_SECTION_CTX, "Təsdiqə göndərmə")


#: Redaktorda göstərilmə sırası (sol naviqasiya).
SECTION_ORDER = tuple(choice.value for choice in SectionKey)

#: TAMAMLANMA faizinin hesablandığı bölmələr (mock-dakı ``RULE`` massivi).
#: ``prev`` və ``send`` yoxlama bölmələridir — faizə DAXİL DEYİL.
RULE_SECTIONS = (
    SectionKey.INFO.value,
    SectionKey.DESC.value,
    SectionKey.OUT.value,
    SectionKey.WEEK.value,
    SectionKey.METHOD.value,
    SectionKey.ASSESS.value,
    SectionKey.SELF.value,
    SectionKey.LIT.value,
)

# ── Biznes-qayda limitləri (README §3.2). Tamamlanma faizi DOLDURULMUŞ INPUT
# SAYINA görə YOX, məhz bu qaydalara görə hesablanır (bax completion.py).
MIN_DESCRIPTION_CHARS = 120
MIN_GOAL_CHARS = 60
MIN_OUTCOME_CHARS = 15
MIN_OUTCOMES = 3
MIN_TOPIC_CHARS = 4
WEEK_ROWS = 16
MIN_FILLED_WEEKS = 14
MIN_METHODS = 2
MIN_PRIMARY_SOURCES = 2
MIN_ADDITIONAL_SOURCES = 1
MIN_SOURCE_CHARS = 8
MIN_OFFICE_HOURS_CHARS = 6
MIN_SELFWORK_TOPIC_CHARS = 10

#: Auditoriya saatı növləri — həftəlik cədvəldəki sütunlar və tədris planı açarları.
LESSON_HOUR_KINDS = ("lecture", "seminar", "lab")

#: Sərbəst iş strukturu — universitet siyasətinin İCAZƏ VERDİYİ variantlar.
#: Hər variantın cəmi 10 baldır.
SELFWORK_OPTIONS = {
    "1x10": {"count": 1, "per_score": 10},
    "2x5": {"count": 2, "per_score": 5},
    "10x1": {"count": 10, "per_score": 1},
}

#: Siyasətə UYĞUN OLMAYAN variant — UI-da izahlı `disabled` kart kimi qalır
#: (cəmi 15 bal edir). Servis qatı bu açarı QƏBUL ETMİR.
SELFWORK_DISALLOWED = {"3x5": {"count": 3, "per_score": 5}}

#: Sərbəst işin universitet siyasəti ilə təyin olunmuş ümumi balı.
SELFWORK_TOTAL_SCORE = 10

#: Tədris metodları kataloqu (README §3.2 checkbox siyahısı).
TEACHING_METHODS = (
    pgettext_lazy(_SELFWORK_CTX, "Mühazirə"),
    pgettext_lazy(_SELFWORK_CTX, "İnteraktiv müzakirə"),
    pgettext_lazy(_SELFWORK_CTX, "Problem əsaslı öyrənmə"),
    pgettext_lazy(_SELFWORK_CTX, "Layihə əsaslı iş"),
    pgettext_lazy(_SELFWORK_CTX, "Laboratoriya təcrübəsi"),
    pgettext_lazy(_SELFWORK_CTX, "Case study təhlili"),
    pgettext_lazy(_SELFWORK_CTX, "Kod baxışı (peer review)"),
    pgettext_lazy(_SELFWORK_CTX, "Fərdi məsləhət"),
)

# ── İcazə açarları (apps.organizations.permissions kataloqu ilə eyni sətirlər).
PERM_VIEW = "syllabus.view"
PERM_EDIT = "syllabus.edit"
PERM_SUBMIT = "syllabus.submit"
PERM_REVIEW = "syllabus.review"
PERM_APPROVE = "syllabus.approve"
PERM_REVISE = "syllabus.revise"
PERM_REJECT = "syllabus.reject"
PERM_MANAGE = "syllabus.manage"

__all__ = [
    "EDITABLE_STATUSES",
    "LESSON_HOUR_KINDS",
    "OPEN_STATUSES",
    "QUEUE_STATUSES",
    "REASON_REQUIRED_STATUSES",
    "RULE_SECTIONS",
    "SECTION_ORDER",
    "SELFWORK_DISALLOWED",
    "SELFWORK_OPTIONS",
    "SELFWORK_TOTAL_SCORE",
    "STATUS_NEXT_STEP",
    "STATUS_SORT_INDEX",
    "STATUS_SORT_ORDER",
    "STATUS_TOKENS",
    "SectionKey",
    "SyllabusStatus",
    "TEACHING_METHODS",
]
