"""Tarixsiz üzrlü qayıb saatı: dəyişdirilməz əlavə və onun ayrıca geri-alma izi."""

from django.conf import settings
from django.core.validators import MinLengthValidator
from django.db import models

from .corrections import ImmutableCorrectionEvidence


class AbsenceCredit(ImmutableCorrectionEvidence):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT)
    enrollment = models.ForeignKey("registrar.Enrollment", on_delete=models.PROTECT, related_name="absence_credits")
    hours = models.PositiveSmallIntegerField()
    reason = models.CharField(max_length=1000, validators=[MinLengthValidator(10)])
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    request_token = models.UUIDField()
    reverses = models.OneToOneField("self", null=True, blank=True, on_delete=models.PROTECT, related_name="reversed_by")
    old_absence_hours = models.PositiveIntegerField()
    new_absence_hours = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["organization", "request_token"], name="reg_abs_credit_token_unique"),
            models.CheckConstraint(condition=models.Q(hours__gt=0), name="reg_abs_credit_positive"),
        ]
