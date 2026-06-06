"""
Apellyasiya sistemi üçün sabitlər.

Bütün status, tip və limitlər burada mərkəzləşdirilib — view/şablon/servislərdə
string hardcode edilmir.
"""

from django.utils.translation import pgettext_lazy

# ---------------------------------------------------------------------------
# Apellyasiya tipləri (universitet/imtahan praktikasına uyğun)
# ---------------------------------------------------------------------------
APPEAL_TYPE_WRONG_QUESTION = "wrong_question"
APPEAL_TYPE_WRONG_ANSWER_KEY = "wrong_answer_key"
APPEAL_TYPE_UNCLEAR_QUESTION = "unclear_question"
APPEAL_TYPE_OUT_OF_SYLLABUS = "out_of_syllabus"
APPEAL_TYPE_TECHNICAL_ISSUE = "technical_issue"
APPEAL_TYPE_GRADING_ISSUE = "grading_issue"
APPEAL_TYPE_OTHER = "other"

APPEAL_TYPE_CHOICES = (
    (APPEAL_TYPE_WRONG_QUESTION, pgettext_lazy("appeals.choice.type", "Sual səhvdir")),
    (APPEAL_TYPE_WRONG_ANSWER_KEY, pgettext_lazy("appeals.choice.type", "Cavab açarı səhvdir")),
    (APPEAL_TYPE_UNCLEAR_QUESTION, pgettext_lazy("appeals.choice.type", "Sual aydın deyil")),
    (APPEAL_TYPE_OUT_OF_SYLLABUS, pgettext_lazy("appeals.choice.type", "Proqramdan kənardır")),
    (APPEAL_TYPE_TECHNICAL_ISSUE, pgettext_lazy("appeals.choice.type", "Texniki problem")),
    (APPEAL_TYPE_GRADING_ISSUE, pgettext_lazy("appeals.choice.type", "Qiymətləndirmə səhvi")),
    (APPEAL_TYPE_OTHER, pgettext_lazy("appeals.choice.type", "Digər")),
)
APPEAL_TYPE_VALUES = frozenset(code for code, _ in APPEAL_TYPE_CHOICES)

# ---------------------------------------------------------------------------
# Başlıq (Appeal) statusları + state-machine keçidləri
# ---------------------------------------------------------------------------
APPEAL_STATUS_PENDING = "pending"
APPEAL_STATUS_UNDER_REVIEW = "under_review"
APPEAL_STATUS_ACCEPTED = "accepted"
APPEAL_STATUS_REJECTED = "rejected"
APPEAL_STATUS_PARTIALLY_ACCEPTED = "partially_accepted"

APPEAL_STATUS_CHOICES = (
    (APPEAL_STATUS_PENDING, pgettext_lazy("appeals.choice.status", "Gözləyir")),
    (APPEAL_STATUS_UNDER_REVIEW, pgettext_lazy("appeals.choice.status", "Baxılır")),
    (APPEAL_STATUS_ACCEPTED, pgettext_lazy("appeals.choice.status", "Qəbul edildi")),
    (APPEAL_STATUS_REJECTED, pgettext_lazy("appeals.choice.status", "Rədd edildi")),
    (APPEAL_STATUS_PARTIALLY_ACCEPTED, pgettext_lazy("appeals.choice.status", "Qismən qəbul edildi")),
)
APPEAL_STATUS_VALUES = frozenset(code for code, _ in APPEAL_STATUS_CHOICES)
APPEAL_STATUS_FINAL = frozenset({APPEAL_STATUS_ACCEPTED, APPEAL_STATUS_REJECTED, APPEAL_STATUS_PARTIALLY_ACCEPTED})

# İcazəli status keçidləri (nəzarətli state-machine). Yekun statuslardan yalnız
# yenidən baxış üçün `under_review`-a qayıtmaq mümkündür (icazə yoxlaması ilə).
APPEAL_STATUS_TRANSITIONS = {
    APPEAL_STATUS_PENDING: {APPEAL_STATUS_UNDER_REVIEW, APPEAL_STATUS_REJECTED},
    APPEAL_STATUS_UNDER_REVIEW: {
        APPEAL_STATUS_ACCEPTED,
        APPEAL_STATUS_REJECTED,
        APPEAL_STATUS_PARTIALLY_ACCEPTED,
    },
    APPEAL_STATUS_ACCEPTED: {APPEAL_STATUS_UNDER_REVIEW},
    APPEAL_STATUS_REJECTED: {APPEAL_STATUS_UNDER_REVIEW},
    APPEAL_STATUS_PARTIALLY_ACCEPTED: {APPEAL_STATUS_UNDER_REVIEW},
}

# ---------------------------------------------------------------------------
# Hər sual üzrə (AppealItem) statusları
# ---------------------------------------------------------------------------
APPEAL_ITEM_STATUS_PENDING = "pending"
APPEAL_ITEM_STATUS_ACCEPTED = "accepted"
APPEAL_ITEM_STATUS_REJECTED = "rejected"

APPEAL_ITEM_STATUS_CHOICES = (
    (APPEAL_ITEM_STATUS_PENDING, pgettext_lazy("appeals.choice.item_status", "Gözləyir")),
    (APPEAL_ITEM_STATUS_ACCEPTED, pgettext_lazy("appeals.choice.item_status", "Qəbul edildi")),
    (APPEAL_ITEM_STATUS_REJECTED, pgettext_lazy("appeals.choice.item_status", "Rədd edildi")),
)
APPEAL_ITEM_STATUS_VALUES = frozenset(code for code, _ in APPEAL_ITEM_STATUS_CHOICES)

# ---------------------------------------------------------------------------
# Biznes qaydaları
# ---------------------------------------------------------------------------
# Apellyasiya yalnız imtahan bitdikdən sonra bu qədər gün ərzində verilə bilər.
APPEAL_WINDOW_DAYS = 3
# Hər apellyasiya şərhinin minimum uzunluğu (simvol).
APPEAL_MIN_COMMENT_LENGTH = 30

# RBAC icazələri (apps/organizations/permissions.py-də artıq təyin olunub).
PERM_APPEAL_CREATE = "appeal.create"
PERM_APPEAL_RESPOND = "appeal.respond"
PERM_APPEAL_DECIDE = "appeal.decide"
