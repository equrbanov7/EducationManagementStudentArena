"""RİM jurnal-bağlanma xəbərdarlığı — «bu tarixdən sonra jurnallar bağlanacaq».

Sahibin tələbi (2026-08): İmtahan Mərkəzinin kollokvium bildirişi kimi, RİM də
jurnalda görünən SÜRÜŞƏN zolaq göndərə bilsin — «Diqqət · Jurnallar DD.MM.YYYY
tarixindən sonra bağlanacaq». Model qəsdən ``KollokviumExtraGrant`` nümunəsi ilə
qurulub: org + dövr + əhatə (bütün universitet / fakültə / kafedra) + tarix +
aktivlik.

Bu model YALNIZ xəbərdarlıqdır — heç nəyi kilidləmir. Faktiki bağlama RİM-in
toplu əməliyyatıdır (:mod:`apps.registrar.journal_close`); bildiriş müəllimə
tarixi əvvəlcədən elan etmək üçündür.
"""

from django.conf import settings
from django.db import models
from django.utils.translation import pgettext_lazy

from core.models import TimeStampedModel, UUIDModel


class JournalCloseScope(models.TextChoices):
    """Bildirişin (və toplu bağlamanın) əhatəsi — sahibin «fakültə-fakültə» tələbi."""

    ORGANIZATION = "organization", pgettext_lazy("registrar.journal_close", "Bütün universitet")
    FACULTY = "faculty", pgettext_lazy("registrar.journal_close", "Fakültə")
    DEPARTMENT = "department", pgettext_lazy("registrar.journal_close", "Kafedra")


class JournalCloseNotice(UUIDModel, TimeStampedModel):
    """(organization, period, əhatə) üçün jurnal-bağlanma xəbərdarlığı.

    ``closes_on`` — jurnalların bağlanacağı tarix (həmin gün DAXİL: müəllim o
    günün sonuna kimi yaza bilər). Tarix keçəndə zolaq görünmür — bax
    :func:`apps.registrar.journal_close_notices.notice_state`.
    """

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="journal_close_notices",
    )
    period = models.ForeignKey(
        "organizations.AcademicPeriod",
        on_delete=models.CASCADE,
        related_name="journal_close_notices",
    )
    scope = models.CharField(
        max_length=16,
        choices=JournalCloseScope.choices,
        default=JournalCloseScope.ORGANIZATION,
    )
    org_unit = models.ForeignKey(
        "organizations.OrgUnit",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="journal_close_notices",
        help_text="Fakültə/kafedra əhatəsi üçün bölmə; org əhatəsində boşdur.",
    )
    closes_on = models.DateField(
        verbose_name=pgettext_lazy("registrar.journal_close", "bağlanma tarixi"),
        help_text="Bu tarixdən SONRA jurnala yazmaq olmayacaq (tarix özü daxildir).",
    )
    message = models.CharField(
        max_length=200,
        blank=True,
        help_text="Standart mətn əvəzinə göstəriləcək öz mətniniz (opsional).",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        verbose_name = pgettext_lazy("registrar.journal_close", "Jurnal bağlanma xəbərdarlığı")
        verbose_name_plural = pgettext_lazy("registrar.journal_close", "Jurnal bağlanma xəbərdarlıqları")
        constraints = [
            # Fakültə/kafedra əhatəsi: bölmə başına bir bildiriş.
            models.UniqueConstraint(
                fields=["organization", "period", "scope", "org_unit"],
                name="uniq_journal_close_notice_unit",
            ),
            # Org əhatəsində ``org_unit`` NULL-dur; Postgres NULL-ları fərqli
            # saydığı üçün ayrıca şərtli unikallıq lazımdır (əks halda eyni
            # dövrə saysız «bütün universitet» bildirişi yaradıla bilərdi).
            models.UniqueConstraint(
                fields=["organization", "period"],
                condition=models.Q(scope=JournalCloseScope.ORGANIZATION),
                name="uniq_journal_close_notice_org",
            ),
        ]
        indexes = [models.Index(fields=["organization", "period"])]
        ordering = ["-closes_on"]

    def __str__(self):
        return f"jurnal-bağlanma<{self.closes_on}·{self.scope}>"
