"""Tədris planının versiya/təsdiq qatı + plan sətrinin saat sahələri.

Dizayn handoff Mərhələ 2 (ekran 05 «Tədris planı redaktoru», 07 «Semestr açılışı»).

NİYƏ AYRI MODUL? ``models/academic.py`` 600 sətir büdcəsinə yaxındır
(``scripts/check_module_size.py``). Sahələr burada TƏRİF olunur, ``academic.py``
onları bir sətirlə çağırır — ``catalog_meta.py`` ilə eyni naxış.

──────────────────────────────────────────────────────────────────────────────
TƏSDİQLƏNMİŞ PLAN IMMUTABLE-DIR (handoff §8 qayda 1)
──────────────────────────────────────────────────────────────────────────────
``status == APPROVED`` olan planın sətirləri NƏ redaktə, NƏ də silinə bilər;
dəyişiklik yalnız YENİ VERSİYA yaradır (``version`` artır, ``previous_version``
köhnəyə göstərir, köhnə plan ``is_active=False`` olur — SİLİNMİR). Qapı servis
qatındadır (``apps.registrar.curriculum_state``) və HTTP-də 409 qaytarır.

──────────────────────────────────────────────────────────────────────────────
SAAT HESABI (docs/workload/TEDRIS_PLANI_SPEC.md §3)
──────────────────────────────────────────────────────────────────────────────
    ümumi saat      = kredit × 30                 (NK 348 b. 3.2.2 — qanunla sabit)
    auditoriya saat = ümumi − sərbəst iş
    auditoriya saat = mühazirə + seminar + laboratoriya
    həftəlik yük    = auditoriya ÷ 15             (effektiv həftə)

Auditoriya/sərbəst iş NİSBƏTİ qanunla sabitlənməyib (universitetdən asılı:
QKU 25%, AzTU 31%, NMİ ~38%) — ona görə burada yalnız CƏMLƏRİN uzlaşması
yoxlanılır, nisbət YOX. Uyğunsuzluq təsdiqə göndərməni BLOKLAYIR (§8 qayda 11).
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import pgettext_lazy

#: 1 AKTS krediti = 30 saat (auditoriya + sərbəst iş birlikdə) — NK 348 b. 3.2.2.
CREDIT_HOURS = 30

#: Auditoriya saatının yayıldığı effektiv həftə sayı (bayram itkisi ilə 14-ə enə
#: bilər; hesablama üçün 15 götürülür — TEDRIS_PLANI_SPEC §3.3).
EFFECTIVE_WEEKS = 15

#: Əyani təhsilin bir semestrindəki hədəf kredit (NK 348 b. 3.2.2).
SEMESTER_CREDIT_TARGET = 30

#: Səbəb tələb edən əməllərin minimum uzunluğu (handoff §8 qayda 6).
PLAN_REASON_MIN_LENGTH = 20


class PlanStatus(models.TextChoices):
    """Tədris planının təsdiq zənciri — handoff §6.1.

    ``returned`` zəncirin İÇİNDƏ deyil, ondan KƏNARA çıxan haldır: hər hansı
    baxış mərhələsindən səbəblə geri qaytarılan plan bura düşür və yalnız
    yenidən ``draft``-a keçib göndərilə bilər.
    """

    DRAFT = "draft", pgettext_lazy("registrar.plan_status", "Qaralama")
    CHAIR_REVIEW = "chair_review", pgettext_lazy("registrar.plan_status", "Kafedra baxışı")
    FACULTY_COUNCIL = "faculty_council", pgettext_lazy("registrar.plan_status", "Fakültə şurası")
    TEACHING_OFFICE = "teaching_office", pgettext_lazy("registrar.plan_status", "Tədris şöbəsi")
    APPROVED = "approved", pgettext_lazy("registrar.plan_status", "Təsdiqlənib")
    RETURNED = "returned", pgettext_lazy("registrar.plan_status", "Qaytarılıb")


class AssessmentForm(models.TextChoices):
    """Plan sətrinin qiymətləndirmə forması (QKU sənədinin «imtahan forması»)."""

    EXAM = "exam", pgettext_lazy("registrar.assessment_form", "İmtahan")
    CREDIT = "credit", pgettext_lazy("registrar.assessment_form", "Hesabat")
    COURSEWORK = "coursework", pgettext_lazy("registrar.assessment_form", "Kurs işi")
    PRACTICE = "practice", pgettext_lazy("registrar.assessment_form", "Təcrübə")
    THESIS = "thesis", pgettext_lazy("registrar.assessment_form", "Buraxılış işi")


def plan_status_field():
    return models.CharField(
        max_length=20,
        choices=PlanStatus.choices,
        default=PlanStatus.DRAFT,
        db_index=True,
        help_text="Təsdiq zəncirindəki mövqe (qaralama → … → təsdiqlənib).",
    )


def plan_version_field():
    return models.PositiveSmallIntegerField(
        default=1,
        help_text="Plan versiyası — təsdiqlənmiş plan dəyişmir, yeni versiya yaranır.",
    )


def plan_previous_version_field():
    return models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="next_versions",
        help_text="Bu versiyanın törədiyi əvvəlki plan (silinmir — tarixçədir).",
    )


def plan_actor_field(related_name: str):
    return models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name=related_name,
    )


def plan_reason_field():
    return models.TextField(blank=True, help_text="Son qaytarma/təsdiq səbəbi (≥20 simvol).")


def plan_protocol_field():
    return models.CharField(
        max_length=64, blank=True, help_text="Elmi Şura protokolunun nömrəsi/tarixi (təsdiqdə yazılır)."
    )


def plan_hours_field(help_text: str):
    return models.PositiveSmallIntegerField(default=0, help_text=help_text)


def plan_credits_field():
    return models.PositiveSmallIntegerField(
        default=0,
        help_text="Sətrin kredit dəyəri — Subject.ects-i ÖVERRIDE edir (kredit ixtisasa görə dəyişir).",
    )


def plan_assessment_field():
    return models.CharField(
        max_length=16,
        choices=AssessmentForm.choices,
        default=AssessmentForm.EXAM,
        help_text="Qiymətləndirmə forması (imtahan/hesabat/kurs işi/təcrübə/buraxılış işi).",
    )


def plan_language_field():
    return models.CharField(
        max_length=8,
        blank=True,
        help_text="Tədris dili / sektor kodu (AZ/EN/RU) — tenant-konfiqurasiyalıdır, hardcode edilmir.",
    )


def plan_teaching_chair_field():
    """Sətri TƏDRİS EDƏN kafedra (xidməti tədris marşrutu).

    String-ref FK: ``registrar`` ``organizations``-ı STATİK import ETMİR
    (``scripts/module_deps.py`` ratchet-i).
    """
    return models.ForeignKey(
        "organizations.OrgUnit",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="taught_plan_rows",
        help_text="Fənni bu planda tədris edən kafedra (OrgUnit: chair/department).",
    )


def plan_row_code_field():
    return models.CharField(max_length=32, blank=True, help_text="Plan şifri (məs. MİF-B04.01).")


# --------------------------------------------------------------------------- #
# Saat balansı — SAF funksiyalar (model importu YOXDUR, testdən birbaşa çağırılır)
# --------------------------------------------------------------------------- #


def expected_total_hours(credits: int) -> int:
    """Kredit → ümumi saat (qanunla sabit nisbət)."""
    return int(credits or 0) * CREDIT_HOURS


def contact_hours(lecture: int, seminar: int, lab: int) -> int:
    return int(lecture or 0) + int(seminar or 0) + int(lab or 0)


def weekly_load(lecture: int, seminar: int, lab: int) -> float:
    """Həftəlik auditoriya yükü (auditoriya ÷ effektiv həftə)."""
    return contact_hours(lecture, seminar, lab) / EFFECTIVE_WEEKS


def row_hour_errors(*, credits, total_hours, lecture_hours, seminar_hours, lab_hours, selfwork_hours) -> list[str]:
    """Sətrin saat uzlaşması — XƏTA AÇARLARI siyahısı (boş = uyğundur).

    Açarlar (etiket UI qatındadır, burada yalnız maşın açarı):
      ``credits_required``  — kredit 0 ola bilməz;
      ``total_mismatch``    — ümumi ≠ kredit × 30;
      ``split_mismatch``    — mühazirə+seminar+lab+sərbəst ≠ ümumi.
    """
    errors: list[str] = []
    credits = int(credits or 0)
    total = int(total_hours or 0)
    if credits <= 0:
        errors.append("credits_required")
    elif total != expected_total_hours(credits):
        errors.append("total_mismatch")
    split = contact_hours(lecture_hours, seminar_hours, lab_hours) + int(selfwork_hours or 0)
    if total and split != total:
        errors.append("split_mismatch")
    return errors


__all__ = [
    "AssessmentForm",
    "CREDIT_HOURS",
    "EFFECTIVE_WEEKS",
    "PLAN_REASON_MIN_LENGTH",
    "PlanStatus",
    "SEMESTER_CREDIT_TARGET",
    "contact_hours",
    "expected_total_hours",
    "plan_actor_field",
    "plan_assessment_field",
    "plan_credits_field",
    "plan_hours_field",
    "plan_language_field",
    "plan_previous_version_field",
    "plan_protocol_field",
    "plan_reason_field",
    "plan_row_code_field",
    "plan_status_field",
    "plan_teaching_chair_field",
    "plan_version_field",
    "row_hour_errors",
    "weekly_load",
]
