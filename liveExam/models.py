import random
import string
from django.db import models
from django.utils import timezone

from blog.models import Exam, ExamQuestion  


def generate_pin():
    return "".join(random.choices(string.digits, k=6))


class LiveSession(models.Model):
    STATE_LOBBY = "lobby"
    STATE_QUESTION = "question"
    STATE_REVEAL = "reveal"
    STATE_FINISHED = "finished"

    STATE_CHOICES = [
        (STATE_LOBBY, "Lobby"),
        (STATE_QUESTION, "Question"),
        (STATE_REVEAL, "Reveal"),
        (STATE_FINISHED, "Finished"),
    ]

    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="live_sessions")
    host_user = models.ForeignKey("auth.User", on_delete=models.CASCADE, related_name="hosted_live_sessions")

    pin = models.CharField(max_length=6, unique=True, default=generate_pin, db_index=True)
    state = models.CharField(max_length=12, choices=STATE_CHOICES, default=STATE_LOBBY)

    is_locked = models.BooleanField(default=False)
    current_index = models.PositiveIntegerField(default=0)

    question_started_at = models.DateTimeField(null=True, blank=True)
    question_ends_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    
    current_index = models.PositiveIntegerField(default=0)

    # ✅ NEW: aktiv sualın id-si (optional, amma çox rahatdır)
    current_question_id = models.IntegerField(null=True, blank=True, db_index=True)

    # ✅ NEW: sessiya üçün default sual vaxtı (Kahoot kimi)
    question_seconds = models.PositiveIntegerField(default=15)

    question_started_at = models.DateTimeField(null=True, blank=True)
    question_ends_at = models.DateTimeField(null=True, blank=True)
        # ✅ Host neçə sual oynanacağını seçəcək
    question_limit = models.PositiveIntegerField(default=10)

    # ✅ Random seçilən sualların ID-ləri (order burada saxlanır)
    selected_question_ids = models.JSONField(default=list, blank=True)

    def _ensure_unique_pin(self):
        tries = 0
        while LiveSession.objects.filter(pin=self.pin).exists():
            self.pin = generate_pin()
            tries += 1
            if tries > 10:
                raise RuntimeError("PIN generate failed")

    def save(self, *args, **kwargs):
        if not self.pin:
            self.pin = generate_pin()
        self._ensure_unique_pin()
        super().save(*args, **kwargs)

    def join_url_path(self):
        return f"/live/join/{self.pin}/"

    def get_exam_questions(self):
        # ExamQuestion ara modelində sıra field-in adı fərqlidirsə (məs: position),
        # bunu dəyişəcəksən:
        return (
            ExamQuestion.objects
            .filter(exam=self.exam)
            .select_related("question")
            .order_by("order")
        )


class LivePlayer(models.Model):
    session = models.ForeignKey(LiveSession, on_delete=models.CASCADE, related_name="players")

    nickname = models.CharField(max_length=32)
    avatar_key = models.CharField(max_length=32, default="avatar_1")

    client_id = models.CharField(max_length=64, db_index=True)

    score = models.IntegerField(default=0)
    streak = models.PositiveIntegerField(default=0)

    is_connected = models.BooleanField(default=True)
    last_seen = models.DateTimeField(default=timezone.now)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["session", "client_id"], name="uniq_player_per_session_client")
        ]
        unique_together = [("session", "client_id")]

    def __str__(self):
        return f"{self.nickname} ({self.session.pin})"


class LiveAnswer(models.Model):
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
        unique_together = [("session", "player", "question_id")]
