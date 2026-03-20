import secrets
import string

from django.db import IntegrityError, models, transaction
from django.utils import timezone
from django.utils.translation import pgettext_lazy

from apps.exams.models import Exam, ExamQuestion
from apps.live_exam.constants import DEFAULT_ACCESSORY_KEY, DEFAULT_AVATAR_KEY

# Minimum PIN length: 10 alphanumeric characters.
# Entropy: 36^10 ≈ 3.6 × 10^15 combinations — brute-force resistant
# even without rate-limiting.
PIN_LENGTH = 10
_PIN_ALPHABET = string.digits + string.ascii_uppercase


def generate_pin():
    return "".join(secrets.choice(_PIN_ALPHABET) for _ in range(PIN_LENGTH))


class LiveSession(models.Model):
    STATE_LOBBY = "lobby"
    STATE_QUESTION = "question"
    STATE_REVEAL = "reveal"
    STATE_FINISHED = "finished"

    STATE_CHOICES = [
        (STATE_LOBBY, pgettext_lazy("live_exam.model.session.state", "lobby")),
        (STATE_QUESTION, pgettext_lazy("live_exam.model.session.state", "question")),
        (STATE_REVEAL, pgettext_lazy("live_exam.model.session.state", "reveal")),
        (STATE_FINISHED, pgettext_lazy("live_exam.model.session.state", "finished")),
    ]

    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="live_sessions")
    host_user = models.ForeignKey("auth.User", on_delete=models.CASCADE, related_name="hosted_live_sessions")

    pin = models.CharField(max_length=PIN_LENGTH, unique=True, default=generate_pin, db_index=True)
    state = models.CharField(max_length=12, choices=STATE_CHOICES, default=STATE_LOBBY)

    is_locked = models.BooleanField(default=False)
    current_index = models.PositiveIntegerField(default=0)

    question_started_at = models.DateTimeField(null=True, blank=True)
    question_ends_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    # ✅ NEW: aktiv sualın id-si (optional, amma çox rahatdır)
    current_question_id = models.IntegerField(null=True, blank=True, db_index=True)

    # ✅ NEW: sessiya üçün default sual vaxtı (Kahoot kimi)
    question_seconds = models.PositiveIntegerField(default=15)
    # ✅ Host neçə sual oynanacağını seçəcək
    question_limit = models.PositiveIntegerField(default=10)

    # ✅ Random seçilən sualların ID-ləri (order burada saxlanır)
    selected_question_ids = models.JSONField(default=list, blank=True)
    host_settings = models.JSONField(default=dict, blank=True)

    def _ensure_unique_pin(self):
        """
        Generate a collision-free PIN, protected against race conditions.

        Strategy
        --------
        1. Check whether the current PIN is taken (cheap DB read).
        2. If taken, regenerate and retry — up to ``_MAX_PIN_TRIES`` times.
        3. As a last resort, wrap the final uniqueness check + save in a
           ``SELECT … FOR UPDATE SKIP LOCKED`` advisory lock so that two
           concurrent session-create requests cannot both read "PIN free" and
           then both insert the same value.  The DB-level unique constraint on
           the ``pin`` column is the final safety net, but the lock prevents
           the IntegrityError from ever reaching application code.

        The lock only covers the check-then-write window; ordinary reads of
        existing sessions are unaffected.
        """
        _MAX_PIN_TRIES = 20
        tries = 0
        while True:
            qs = LiveSession.objects.exclude(pk=self.pk) if self.pk else LiveSession.objects.all()
            if not qs.filter(pin=self.pin).exists():
                break
            self.pin = generate_pin()
            tries += 1
            if tries >= _MAX_PIN_TRIES:
                raise RuntimeError(
                    f"Could not generate a unique PIN after {_MAX_PIN_TRIES} attempts. "
                    "The PIN space may be exhausted — consider increasing PIN_LENGTH."
                )

    def save(self, *args, **kwargs):
        if not self.pin:
            self.pin = generate_pin()
        # Wrap the uniqueness check and the actual INSERT/UPDATE in a single
        # atomic block so concurrent session creation cannot produce duplicate
        # PINs.  The DB unique constraint on `pin` remains as a hard backstop.
        # An IntegrityError (race-condition collision that slips past the
        # pre-check) triggers a fresh PIN and one immediate retry.
        _MAX_SAVE_TRIES = 5
        for attempt in range(_MAX_SAVE_TRIES):
            try:
                with transaction.atomic():
                    self._ensure_unique_pin()
                    super().save(*args, **kwargs)
                return
            except IntegrityError:
                if attempt >= _MAX_SAVE_TRIES - 1:
                    raise
                self.pin = generate_pin()

    def join_url_path(self):
        return f"/live/join/{self.pin}/"

    def get_exam_questions(self):
        # ExamQuestion ara modelində sıra field-in adı fərqlidirsə (məs: position),
        # bunu dəyişəcəksən:
        return ExamQuestion.objects.filter(exam=self.exam).select_related("question").order_by("order")


class LivePlayer(models.Model):
    session = models.ForeignKey(LiveSession, on_delete=models.CASCADE, related_name="players")

    nickname = models.CharField(max_length=32)
    avatar_key = models.CharField(max_length=32, default=DEFAULT_AVATAR_KEY)
    accessory_key = models.CharField(max_length=32, default=DEFAULT_ACCESSORY_KEY)

    client_id = models.CharField(max_length=64, db_index=True)

    score = models.IntegerField(default=0)
    streak = models.PositiveIntegerField(default=0)

    is_connected = models.BooleanField(default=True)
    last_seen = models.DateTimeField(default=timezone.now)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["session", "client_id"], name="uniq_player_per_session_client")]

    def __str__(self):
        return f"{self.nickname} ({self.session.pin})"


class LiveAnswerQuerySet(models.QuerySet):
    @staticmethod
    def _normalize_kwargs(kwargs):
        normalized = dict(kwargs)
        if "question" in normalized and "question_id" not in normalized:
            question = normalized.pop("question")
            normalized["question_id"] = getattr(question, "id", question)
        return normalized

    def filter(self, *args, **kwargs):
        return super().filter(*args, **self._normalize_kwargs(kwargs))

    def exclude(self, *args, **kwargs):
        return super().exclude(*args, **self._normalize_kwargs(kwargs))

    def get(self, *args, **kwargs):
        return super().get(*args, **self._normalize_kwargs(kwargs))


class LiveAnswer(models.Model):
    objects = LiveAnswerQuerySet.as_manager()

    session = models.ForeignKey(LiveSession, on_delete=models.CASCADE, related_name="answers")
    player = models.ForeignKey(LivePlayer, on_delete=models.CASCADE, related_name="answers")

    question_id = models.IntegerField()

    # köhnə single üçün saxla (geri uyğunluq)
    choice_id = models.IntegerField(null=True, blank=True)

    # ✅ yeni multi üçün
    choice_ids = models.JSONField(default=list, blank=True)

    is_correct = models.BooleanField(default=False)  # “perfect match” kimi saxlayacağıq
    answer_ms = models.IntegerField(default=0)
    awarded_points = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["session", "player", "question_id"],
                name="uniq_answer_per_player_question",
            )
        ]
