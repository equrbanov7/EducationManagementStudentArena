"""«Alt qrupa yerləşdirmə» hadisə jurnalı — append-only tarixçə (sahib 2026-09-07 / 2026-10-18).

Sahib: «alt qrupa yazılıbsa onun da tarixçəsi qalsın, biz də bilək» + «alt qrupa tələbə əlavə et yeri olsun —
tələbə seçilir, uyğun olursa yerləşir». Qeydiyyatın özü mövcud ``Enrollment`` sətridir (``source_group`` dolu —
:mod:`apps.registrar.guest_roster`); bu cədvəl isə HƏR əməli (yerləşdirmə / geri götürmə) sənədi, səbəbi və
qərar anındakı kredit yükü ilə birlikdə saxlayır. Sətir YARADILDIQDAN SONRA nə dəyişir, nə silinir
(``ImmutableCorrectionEvidence`` + PostgreSQL trigger-i, miqrasiya 0092). Geri götürmə ayrıca ``undo`` sətridir
(``undoes`` → ``place`` sətri) — əvvəlki sətir toxunulmaz qalır.

Sənəd iki formadan biri ilə MƏCBURİDİR (servis yoxlayır, ``place_in_subgroup``):

* yüklənmiş fayl (PDF / JPG / PNG) — :class:`GuestRosterDocument` sətri kimi saxlanılır (qorunan media,
  təsadüfi ad) və ``document`` ilə bağlanır — jurnal modalı da eyni sənədi göstərir;
* sərəncam / təqdimat nömrəsi + tarixi (``order_number`` + ``order_date``).
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import pgettext_lazy

from .corrections import ImmutableCorrectionEvidence


class SubgroupPlacementKind(models.TextChoices):
    PLACE = "place", pgettext_lazy("registrar.model.subgroup_placement", "Alt qrupa yerləşdirildi")
    UNDO = "undo", pgettext_lazy("registrar.model.subgroup_placement", "Yerləşdirmə geri götürüldü")


class SubgroupPlacementEvent(ImmutableCorrectionEvidence):
    """Bir yerləşdirmə / geri götürmə əməli (append-only)."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="subgroup_placement_events"
    )
    kind = models.CharField(max_length=8, choices=SubgroupPlacementKind.choices)
    enrollment = models.ForeignKey(
        "registrar.Enrollment", on_delete=models.PROTECT, related_name="subgroup_placement_events"
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="subgroup_placement_events"
    )
    offering = models.ForeignKey(
        "registrar.CourseOffering", on_delete=models.PROTECT, related_name="subgroup_placement_events"
    )
    source_group = models.ForeignKey(
        "organizations.OrgUnit", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    target_group = models.ForeignKey(
        "organizations.OrgUnit", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    undoes = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="undone_by",
        help_text="Geri götürmə sətri — hansı yerləşdirməni geri götürür.",
    )  # fmt: skip
    document = models.ForeignKey(
        "registrar.GuestRosterDocument", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    order_number = models.CharField(max_length=64, blank=True)
    order_date = models.DateField(null=True, blank=True)
    reason = models.TextField()
    credits_before = models.PositiveSmallIntegerField(default=0)
    credits_after = models.PositiveSmallIntegerField(default=0)
    credit_limit = models.PositiveSmallIntegerField(default=0)
    #: Təsdiq anındakı cədvəl toqquşmaları (xəbərdarlıq kimi qəbul edilibsə) və birləşmə (öz jurnalından azad).
    details = models.JSONField(default=dict, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="subgroup_placements_made"
    )
    actor_name = models.CharField(max_length=200, editable=False, default="")

    objects = models.Manager()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = pgettext_lazy("registrar.model.subgroup_placement", "subgroup placement event")
        verbose_name_plural = pgettext_lazy("registrar.model.subgroup_placement", "subgroup placement events")
        indexes = [
            models.Index(fields=["organization", "-created_at"]),
            models.Index(fields=["organization", "student", "-created_at"]),
            models.Index(fields=["enrollment", "-created_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(kind="place", undoes__isnull=True) | models.Q(kind="undo", undoes__isnull=False),
                name="subgroup_event_undo_points_to_place",
            ),
            # Bir yerləşdirmə yalnız bir dəfə geri götürülür (sətir kilidindən əlavə DB qapısı).
            models.UniqueConstraint(
                fields=["undoes"], condition=models.Q(undoes__isnull=False), name="subgroup_event_single_undo"
            ),
        ]

    def save(self, *args, **kwargs):
        if self.actor_id and not self.actor_name:
            user = self.actor
            self.actor_name = ((user.get_full_name() or "").strip() or user.username)[:200]
        return super().save(*args, **kwargs)


__all__ = ["SubgroupPlacementEvent", "SubgroupPlacementKind"]
