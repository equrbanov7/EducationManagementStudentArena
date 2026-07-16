"""Kollokvium bal-yazma pəncərəsi — İmtahan Mərkəzinin idarə etdiyi açıq/bağlı aralıq.

İmtahan Mərkəzi hər semestr (AcademicPeriod) üçün K1/K2/K3 üzrə org-səviyyə
bal-yazma aralığı təyin edib aktivləşdirir. Müəllim YALNIZ pəncərə aktiv və açıq
olduqda jurnalda kollokvium balı yaza/dəyişə bilər. Pəncərə bağlananda tam
kilidlənir. Kollokvium üçün adi 2-saat kilidi YOXDUR — bu pəncərə onu əvəz edir
(bax: gradebook_components.save_component_scores → kollokvium ayrıca yoxlanır).

Rəhbər əlavə gün verə bilər (``KollokviumExtraGrant``) — bütün universitet,
fakültə və ya kafedra əhatəsində; effektiv son tarix = closes_on + əlavə gün.
"""

from django.conf import settings
from django.db import models
from django.utils.translation import pgettext_lazy

from core.models import TimeStampedModel, UUIDModel

#: Bir semestrdə neçə kollokvium (K1/K2/K3) — journal_extras.KOLLOKVIUM_COUNT ilə eyni.
KOLLOKVIUM_WINDOW_COUNT = 3


class KollokviumWindow(UUIDModel, TimeStampedModel):
    """(organization, period, k_index) üçün bal-yazma aralığı.

    ``k_index`` 0/1/2 = K1/K2/K3 (offering-in sıralanmış kollokvium
    komponentlərindəki mövqe). Org-səviyyədir: bütün fənlərin K{n}-i eyni aralığı
    paylaşır.
    """

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="kollokvium_windows",
    )
    period = models.ForeignKey(
        "organizations.AcademicPeriod",
        on_delete=models.CASCADE,
        related_name="kollokvium_windows",
    )
    k_index = models.PositiveSmallIntegerField(
        verbose_name=pgettext_lazy("registrar.kollokvium_window", "kollokvium indeksi (0=K1)"),
    )
    opens_on = models.DateField(
        verbose_name=pgettext_lazy("registrar.kollokvium_window", "açılış tarixi"),
    )
    closes_on = models.DateField(
        verbose_name=pgettext_lazy("registrar.kollokvium_window", "bağlanış tarixi"),
    )
    is_active = models.BooleanField(default=False, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        verbose_name = pgettext_lazy("registrar.kollokvium_window", "Kollokvium pəncərəsi")
        verbose_name_plural = pgettext_lazy("registrar.kollokvium_window", "Kollokvium pəncərələri")
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "period", "k_index"],
                name="uniq_kollokvium_window",
            )
        ]
        indexes = [models.Index(fields=["organization", "period"])]
        ordering = ["period", "k_index"]

    def __str__(self):
        return f"K{self.k_index + 1} · {self.opens_on}–{self.closes_on}"


class KollokviumExtraGrant(UUIDModel, TimeStampedModel):
    """Rəhbərin verdiyi əlavə gün — bal-yazma pəncərəsini uzadır.

    Əhatə (``scope``): bütün universitet / fakültə / kafedra. Fakültə və kafedra
    üçün ``org_unit`` (OrgUnit) tələb olunur; org əhatəsində NULL-dur. Bir
    offering üçün effektiv əlavə gün = tətbiq olunan grant-ların ƏN BÖYÜYÜ.
    """

    class Scope(models.TextChoices):
        ORGANIZATION = "organization", pgettext_lazy("registrar.kollokvium_window", "Bütün universitet")
        FACULTY = "faculty", pgettext_lazy("registrar.kollokvium_window", "Fakültə")
        DEPARTMENT = "department", pgettext_lazy("registrar.kollokvium_window", "Kafedra")

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="kollokvium_extra_grants",
    )
    window = models.ForeignKey(
        KollokviumWindow,
        on_delete=models.CASCADE,
        related_name="extra_grants",
    )
    scope = models.CharField(max_length=16, choices=Scope.choices)
    org_unit = models.ForeignKey(
        "organizations.OrgUnit",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="kollokvium_extra_grants",
    )
    extra_days = models.PositiveSmallIntegerField(default=0)
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        verbose_name = pgettext_lazy("registrar.kollokvium_window", "Kollokvium əlavə gün")
        verbose_name_plural = pgettext_lazy("registrar.kollokvium_window", "Kollokvium əlavə günlər")
        constraints = [
            models.UniqueConstraint(
                fields=["window", "scope", "org_unit"],
                name="uniq_kollokvium_extra_grant",
            )
        ]
        indexes = [models.Index(fields=["organization", "window"])]

    def __str__(self):
        return f"+{self.extra_days}g · {self.get_scope_display()}"
