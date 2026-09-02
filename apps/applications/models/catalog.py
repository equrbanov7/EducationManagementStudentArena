"""Per-tenant kataloq: şöbələr, müraciət növləri, nömrə sayğacı.

Niyə DB-də və niyə ROL adları ilə? Bu kod bazasında mərkəzi şöbələr (RİM, HR,
imtahan mərkəzi, prorektor) ``OrgUnit`` DEYİL — onlar ORGANIZATION scope-lu
ROLLARDIR (``default_roles_university.py``). Dekan / kafedra müdiri /
koordinator isə UNIT scope-ludur. Ona görə «müraciət hara gedir» sualının
cavabı iki hissəlidir: (a) hansı ROL onu emal edir, (b) göndərənin hansı
ƏCDAD bölməsinə bağlanır (``resolve_by``).
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import pgettext_lazy

from core.models import OrderedModel, TimeStampedModel, UUIDModel

from ..constants import ResolveBy, SenderFamily

_CTX = "applications"


class ApplicationUnit(UUIDModel, TimeStampedModel, OrderedModel):
    """Müraciəti emal edən şöbə — tenant üzrə konfiqurasiya olunur."""

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="application_units",
    )
    code = models.SlugField(max_length=40)
    name = models.CharField(max_length=160)
    note = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Yönləndirmə dialoqunda göstərilən qısa izah.",
    )
    handler_role_names = models.JSONField(
        default=list,
        blank=True,
        help_text="Bu şöbəni emal edən Role.name siyahısı (məs. ['dean']).",
    )
    resolve_by = models.CharField(
        max_length=20,
        choices=ResolveBy.choices,
        default=ResolveBy.ORGANIZATION,
        help_text="Müraciət göndərənin hansı əcdad bölməsinə bağlanır.",
    )
    default_sla_days = models.PositiveSmallIntegerField(default=5)
    is_active = models.BooleanField(default=True, db_index=True)

    objects = models.Manager()

    class Meta:
        ordering = ["organization", "order", "name"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "code"], name="uniq_application_unit_code"),
        ]
        indexes = [models.Index(fields=["organization", "is_active"])]
        verbose_name = pgettext_lazy(_CTX, "müraciət şöbəsi")
        verbose_name_plural = pgettext_lazy(_CTX, "müraciət şöbələri")

    def __str__(self):
        return f"{self.code} · {self.name}"

    @property
    def role_names(self) -> list:
        return [str(name) for name in (self.handler_role_names or []) if name]


class ApplicationKind(UUIDModel, TimeStampedModel, OrderedModel):
    """Müraciət növü — marşrut və cavab müddətinin mənbəyi.

    Marşrut SERVER tərəfdə hesablanır: göndərən şöbəni SEÇMİR (dizayn §3.2).
    ``route_overrides`` ailəyə görə fərqli ünvan verir (məs. «Digər» tələbədən
    koordinatora, müəllimdən kafedraya, əməkdaşdan RİM-ə).
    """

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="application_kinds",
    )
    code = models.SlugField(max_length=40)
    label = models.CharField(max_length=160)
    note = models.CharField(max_length=255, blank=True, default="")
    allowed_sender_families = models.JSONField(
        default=list,
        blank=True,
        help_text="SenderFamily dəyərləri: student / teacher / staff.",
    )
    target_unit = models.ForeignKey(
        ApplicationUnit,
        on_delete=models.PROTECT,
        related_name="kinds",
    )
    route_overrides = models.JSONField(
        default=dict,
        blank=True,
        help_text="{'student': 'koordinator', …} — ailəyə görə fərqli şöbə kodu.",
    )
    sla_days = models.PositiveSmallIntegerField(default=5)
    badge_palette = models.CharField(max_length=20, default="neutral")
    is_active = models.BooleanField(default=True, db_index=True)

    objects = models.Manager()

    class Meta:
        ordering = ["organization", "order", "label"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "code"], name="uniq_application_kind_code"),
        ]
        indexes = [models.Index(fields=["organization", "is_active"])]
        verbose_name = pgettext_lazy(_CTX, "müraciət növü")
        verbose_name_plural = pgettext_lazy(_CTX, "müraciət növləri")

    def __str__(self):
        return f"{self.code} · {self.label}"

    @property
    def families(self) -> list:
        allowed = {choice.value for choice in SenderFamily}
        return [str(item) for item in (self.allowed_sender_families or []) if str(item) in allowed]

    def allows(self, family: str) -> bool:
        return family in self.families

    def unit_code_for(self, family: str) -> str:
        """Ailəyə görə hədəf şöbə kodu (override varsa o, yoxsa ``target_unit``)."""
        overrides = self.route_overrides or {}
        code = overrides.get(family)
        return str(code) if code else self.target_unit.code


class ApplicationCounter(TimeStampedModel):
    """Təşkilat üzrə ardıcıl müraciət nömrəsi (``MR-000001``).

    Ayrıca cədvəl QƏSDƏNDİR: nömrə ``select_for_update`` ilə bir SƏTİR üzərində
    kilidlənir, yəni paralel göndərişlər ``Application`` cədvəlini bloklamır və
    boşluqsuz ardıcıllıq alınır (``MAX(number)+1`` yarışa açıqdır).
    """

    organization = models.OneToOneField(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="application_counter",
        primary_key=True,
    )
    last_number = models.PositiveIntegerField(default=0)

    objects = models.Manager()

    class Meta:
        verbose_name = pgettext_lazy(_CTX, "müraciət nömrə sayğacı")
        verbose_name_plural = pgettext_lazy(_CTX, "müraciət nömrə sayğacları")

    def __str__(self):
        return f"{self.organization_id}: {self.last_number}"
