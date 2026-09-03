"""Registrar akademik-struktur modelləri (U1/U2/U4).

Program → Curriculum → CurriculumSubject kataloqu; tələbə qeydi, fənn açılışı,
qeydiyyat, qrup-seçmə qərarı və həftəlik dərs cədvəli slotu. Hər model tenant-
scoped (``organization`` FK) və RLS-qorumalıdır. Qiymətləndirmə/jurnal modelləri
:mod:`apps.registrar.models.grading`-dədir.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import pgettext_lazy

from core.models import ActiveManager, TimeStampedModel, UUIDModel

from ..reference_identity import ReferenceIdentityValidationMixin
from ._program_codes import (
    ProgramCodeLabelsMixin,
    legacy_official_code_field,
    official_code_field,
)
from .admission_meta import AdmissionRecordFields
from .catalog_meta import (
    ArchivableCatalogModel,
    education_form_field,
    owning_chair_field,
    subject_kind_field,
)


class DegreeLevel(models.TextChoices):
    BACHELOR = "bachelor", pgettext_lazy("registrar.degree", "Bachelor")
    MASTER = "master", pgettext_lazy("registrar.degree", "Master")
    PHD = "phd", pgettext_lazy("registrar.degree", "PhD")


class Program(ProgramCodeLabelsMixin, ArchivableCatalogModel, UUIDModel, TimeStampedModel):
    """An academic program (İxtisas) offered by the university.

    Optionally anchored to a specialty ``OrgUnit`` so the hierarchy
    (Faculty → Chair → Specialty) and the program catalogue stay linked.

    İKİ AYRI KOD — qarışdırılmamalıdır
    ----------------------------------
    ``code`` — **DAXİLİ sabit identifikator**. Tenant daxilində UNİKALDIR
    (``uniq_program_code_per_org``) və köçürmə xəttinin (``apps.legacy_import``)
    indeks açarıdır: köhnə bazadan gələn proqramlar ``MYEDU-<legacy_id>``
    formasında sintetik kod alır və repetisiya fazaları (``program_pk_index``,
    ``rehearsal_structure_targets``, ``rehearsal_catalog_targets``) məhz bu
    kodun tək-mənalılığına söykənir. Ona görə sahə NƏ boşaldıla, NƏ də
    təkrarlana bilər — və istifadəçiyə GÖSTƏRİLMİR: uydurma açardır, insan
    üçün mənası yoxdur.

    ÜÇ KOD — qarışdırılmamalıdır (tam izah: :mod:`._program_codes`)
    -------------------------------------------------------------
    ``code``
        **DAXİLİ** sabit identifikator (``MYEDU-<legacy_id>``); tenant daxilində
        unikaldır, köçürmə xəttinin (``apps.legacy_import``) indeks açarıdır və
        istifadəçiyə **HEÇ VAXT GÖSTƏRİLMİR**.
    ``official_code``
        **CARİ** rəsmi dövlət şifri (NK 503/2024) — ``6XXXXXX``/``7XXXXXX``.
    ``legacy_official_code``
        **ƏVVƏLKİ** nəsil rəsmi şifr — ``050XXX``/``060XXX``; köhnə tələbələrin
        diplomundakı şifr, ona görə silinmir.

    Uyğunluq bire-bir DEYİL (ixtisas ləğv oluna, yenidən yarana və ya bölünə
    bilər), ona görə iki sütun bir sütuna yığıla bilməz — bax miqrasiya
    ``0061_program_legacy_official_code``.

    HƏR İKİSİ ``blank=True`` və QƏSDƏN UNİKAL DEYİL: bir rəsmi şifr həqiqətən
    bir neçə proqrama aid olur (``7002013`` — dörd magistr psixologiya proqramı;
    ``6002006`` — AZ/EN bölmə variantları; ``6006022`` — əyani/qiyabi formalar).
    Daxili tək-mənalılıq onsuz da ``code``-un üzərindədir.

    İstifadəçiyə göstərmək üçün HƏMİŞƏ :attr:`display_label` (kompakt) və ya
    :attr:`official_code_pair` (hər iki şifr) işlədilir — heç bir səthdə
    sahələr ƏL İLƏ birləşdirilmir.
    """

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="programs")
    specialty_unit = models.ForeignKey(
        "organizations.OrgUnit",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="programs",
        help_text="İxtisas (OrgUnit: specialty) — iyerarxiya bağlantısı.",
    )
    code = models.CharField(
        max_length=32,
        help_text="Daxili sabit identifikator (tenant daxilində unikal) — istifadəçiyə göstərilmir.",
    )
    official_code = official_code_field()
    legacy_official_code = legacy_official_code_field()
    name = models.CharField(max_length=255)
    degree_level = models.CharField(max_length=16, choices=DegreeLevel.choices, default=DegreeLevel.BACHELOR)
    # Təhsil forması + arxiv qatı: bax `catalog_meta` (silmə yoxdur, arxivləmə var).
    education_form = education_form_field()
    ects_total = models.PositiveIntegerField(
        default=240, help_text="Məzuniyyət üçün tələb olunan tam ECTS kredit yükü (Boloniya)."
    )
    # Qayıb (absence) limiti: dərs saatlarının bu %-ini üzrsüz buraxan tələbə
    # imtahana buraxılmır ("kəsilir"). AZ universitetlərində adətən 25% —
    # universitetə/proqrama görə konfiqurasiya olunur.
    absence_limit_percent = models.PositiveSmallIntegerField(
        default=25, help_text="Üzrsüz qayıb həddi (dərs saatının %-i); keçilərsə imtahana buraxılmır."
    )
    is_active = models.BooleanField(default=True, db_index=True)

    objects = models.Manager()
    active = ActiveManager()

    class Meta:
        verbose_name = pgettext_lazy("registrar.model.program.meta", "program")
        verbose_name_plural = pgettext_lazy("registrar.model.program.meta", "programs")
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "code"], name="uniq_program_code_per_org"),
        ]

    def __str__(self):
        return self.display_label


class Subject(ArchivableCatalogModel, UUIDModel, TimeStampedModel):
    """A subject/course catalogue entry (Fənn) — the reusable definition that
    curricula reference and semester offerings instantiate."""

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="subjects")
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=255)
    ects = models.PositiveSmallIntegerField(default=5, help_text="Fənnin ECTS kredit dəyəri.")
    # Kataloq metadatası (ekran 04) + arxiv qatı — bax `catalog_meta`.
    kind = subject_kind_field()
    chair_unit = owning_chair_field()
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    objects = models.Manager()
    active = ActiveManager()

    class Meta:
        verbose_name = pgettext_lazy("registrar.model.subject.meta", "subject")
        verbose_name_plural = pgettext_lazy("registrar.model.subject.meta", "subjects")
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "code"], name="uniq_subject_code_per_org"),
        ]

    def __str__(self):
        return f"{self.code} — {self.name}"


# ── Enrollment layer (U2): student record, offerings, enrollments, group choice ──


class EnrollmentKind(models.TextChoices):
    MANDATORY = "mandatory", pgettext_lazy("registrar.enrollment_kind", "Mandatory")
    ELECTIVE = "elective", pgettext_lazy("registrar.enrollment_kind", "Elective")
    RETAKE = "retake", pgettext_lazy("registrar.enrollment_kind", "Retake")


class AcademicStatus(models.TextChoices):
    """Where a student stands academically (U5+ status state-machine)."""

    ENROLLED = "enrolled", pgettext_lazy("registrar.academic_status", "Enrolled")
    ACADEMIC_LEAVE = "academic_leave", pgettext_lazy("registrar.academic_status", "Academic leave")
    EXPELLED = "expelled", pgettext_lazy("registrar.academic_status", "Expelled")
    GRADUATED = "graduated", pgettext_lazy("registrar.academic_status", "Graduated")


class StudentAcademicRecord(ReferenceIdentityValidationMixin, AdmissionRecordFields, UUIDModel, TimeStampedModel):
    """A student's academic profile within a program: which curriculum + group
    they belong to. Drives the mandatory/elective enrollment flow (roadmap §2)."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="student_records"
    )
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="academic_records")
    program = models.ForeignKey(Program, on_delete=models.PROTECT, related_name="student_records")
    curriculum = models.ForeignKey("registrar.Curriculum", on_delete=models.PROTECT, related_name="student_records")
    group = models.ForeignKey(
        "organizations.OrgUnit",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="student_records",
        help_text="Tələbənin qrupu (bölmə/sektor OrgUnit: group).",
    )
    admission_year = models.PositiveIntegerField()
    status = models.CharField(
        max_length=20,
        choices=AcademicStatus.choices,
        default=AcademicStatus.ENROLLED,
        db_index=True,
        help_text="Akademik status (qeydiyyatlı / akademik məzuniyyət / xaric / məzun).",
    )
    # ── Rəsmi davamiyyət istisnası: idmançı-tələbə (milli yığma) ─────────────
    # «DAVAMİYYƏT BALININ HESABLANMASI» cədvəlinin qeydi: Gənclər və İdman
    # Nazirliyinin Kollegiyası tərəfindən təsdiq edilmiş milli yığma komandaların
    # üzvü olan idmançı-tələbələr 25% həddinə görə imtahana buraxılmamazlıq
    # qaydasından İSTİSNA olunur.
    #
    # Bu, üzrlü qayıbdan (``LessonMark`` EXCUSED) FƏRQLİ mexanizmdir: üzrlü qayıb
    # saatı ``Enrollment.absence_hours``-a heç vaxt daxil olmur, yəni həm balı,
    # həm həddi dəyişir.  İstisna isə saatları olduğu kimi saxlayır və YALNIZ
    # buraxılış qərarını ləğv edir — davamiyyət balı yenə real qayıba görə düşür
    # (bax ``apps.registrar.attendance.attendance_score(exempt=...)``).
    #
    # ⚠️ Köçürmə bu sahəni AVTOMATİK DOLDURMUR.  Köhnə sistemdə istisna üçün
    # struktur sahə yox idi (idman açar sözlü icazələr adi üzrlü qayıb kimi
    # işlənirdi), ona görə tarixi datadan onu bərpa etmək olmaz.  Sahə yalnız
    # gələcək semestrlərdə, dekanlığın rəsmi qərarı ilə əl ilə qoyulur.
    #
    # ⚠️ ``db_default`` QƏSDƏNDİR (yalnız ``default`` KİFAYƏT ETMİR).  Django
    # ``default``-u tətbiq qatında tətbiq edir və miqrasiyadan sonra DB-dəki
    # DEFAULT-u geri götürür; bu cədvələ isə XAM SQL ilə də INSERT edilir
    # (köçürmə/RLS testləri, gələcək toplu COPY yolları).  ``db_default``
    # olmasa həmin xam INSERT-lər NOT NULL pozuntusu ilə çökür.
    national_athlete_exemption = models.BooleanField(
        default=False,
        db_default=False,
        db_index=True,
        help_text=(
            "Milli yığma komandanın üzvü olan idmançı-tələbə — 25% qayıb həddi "
            "imtahana buraxılışı ləğv etmir (bal yenə real qayıba görə hesablanır)."
        ),
    )
    national_athlete_exemption_note = models.CharField(
        max_length=255,
        blank=True,
        db_default="",
        help_text="İstisnanın rəsmi əsası (Kollegiya qərarının nömrəsi/tarixi) — audit üçün.",
    )
    is_active = models.BooleanField(default=True, db_index=True)

    objects = models.Manager()
    active = ActiveManager()

    class Meta:
        verbose_name = pgettext_lazy("registrar.model.student_record.meta", "student academic record")
        verbose_name_plural = pgettext_lazy("registrar.model.student_record.meta", "student academic records")
        constraints = [
            models.UniqueConstraint(fields=["organization", "student", "program"], name="uniq_student_program"),
        ]
        indexes = [models.Index(fields=["organization", "group"])]

    def __str__(self):
        return f"{self.student_id} · {self.program.display_label}"


class CourseOffering(ReferenceIdentityValidationMixin, UUIDModel, TimeStampedModel):
    """A subject taught in a specific semester for a specific group (a section).

    Optionally links to the LMS ``courses.Course`` so the subject's content
    (topics/resources) is the existing course dashboard (roadmap §2.2)."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="course_offerings"
    )
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="offerings")
    period = models.ForeignKey("organizations.AcademicPeriod", on_delete=models.PROTECT, related_name="offerings")
    group = models.ForeignKey(
        "organizations.OrgUnit",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="course_offerings",
        help_text="Bu bölmənin/qrupun dərsi (boşdursa — bütün ixtisas üçün).",
    )
    course = models.ForeignKey(
        "courses.Course",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="offerings",
        help_text="LMS kursu (fənn içi = mövzular/resurslar) — opsional.",
    )
    instructor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="taught_offerings",
        help_text="Fənni tədris edən müəllim (elektron jurnal sahibi).",
    )
    lesson_hours = models.PositiveSmallIntegerField(
        default=0, help_text="Semestrdə fənnin tam dərs (kontakt) saatı — qayıb limiti üçün baza."
    )
    is_active = models.BooleanField(default=True, db_index=True)

    objects = models.Manager()
    active = ActiveManager()

    class Meta:
        verbose_name = pgettext_lazy("registrar.model.offering.meta", "course offering")
        verbose_name_plural = pgettext_lazy("registrar.model.offering.meta", "course offerings")
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "subject", "period", "group"], name="uniq_offering_subject_period_group"
            ),
        ]
        indexes = [models.Index(fields=["organization", "period"])]

    def __str__(self):
        return f"{self.subject.code} @ {self.period_id}"


class Enrollment(ReferenceIdentityValidationMixin, UUIDModel, TimeStampedModel):
    """A student's enrollment in one course offering (mandatory / elective / retake)."""

    class Status(models.TextChoices):
        ENROLLED = "enrolled", pgettext_lazy("registrar.enrollment_status", "Enrolled")
        COMPLETED = "completed", pgettext_lazy("registrar.enrollment_status", "Completed")
        DROPPED = "dropped", pgettext_lazy("registrar.enrollment_status", "Dropped")

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="enrollments")
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="enrollments",
    )
    offering = models.ForeignKey(CourseOffering, on_delete=models.CASCADE, related_name="enrollments")
    kind = models.CharField(max_length=16, choices=EnrollmentKind.choices, default=EnrollmentKind.MANDATORY)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ENROLLED, db_index=True)
    superseded_by = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="superseded_enrollments",
        help_text="Qrup köçürməsində bu qeydiyyatı əvəz edən cari qeydiyyat.",
    )
    absence_hours = models.PositiveSmallIntegerField(
        default=0, help_text="Bu fənn üzrə toplanmış üzrsüz qayıb saatı (qayıb limiti üçün)."
    )
    # ── «Alt qrupdan əlavə olunub» (guest) provenansı ────────────────────────
    # Tələbənin ÖZ qrupu açılışın qrupu DEYİLSƏ, koordinator/dekanlıq onu bu
    # jurnala ƏLAVƏ qeydiyyatla salır. Yeni model YARADILMIR: jurnal onsuz da
    # ``offering.enrollments``-dan qurulur, ona görə lazım olan tək şey MƏNBƏ
    # işarəsidir. ``source_group`` doludursa sətir jurnalda «alt qrup» çipi ilə
    # göstərilir; boşdursa adi (öz qrupundan) tələbədir.
    source_group = models.ForeignKey(
        "organizations.OrgUnit",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="guest_enrollments",
        help_text="Doludursa: tələbə BU açılışa başqa (alt) qrupdan əlavə olunub — mənbə qrup.",
    )
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="guest_enrollments_added",
        help_text="Alt qrupdan əlavəni edən aktor (koordinator/dekanlıq).",
    )
    added_at = models.DateTimeField(null=True, blank=True, help_text="Alt qrupdan əlavə vaxtı.")

    objects = models.Manager()

    class Meta:
        verbose_name = pgettext_lazy("registrar.model.enrollment.meta", "enrollment")
        verbose_name_plural = pgettext_lazy("registrar.model.enrollment.meta", "enrollments")
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "student", "offering"],
                name="uniq_student_offering",
            ),
            models.CheckConstraint(
                condition=models.Q(superseded_by__isnull=True) | models.Q(status="dropped"),
                name="superseded_enrollment_is_dropped",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "student"]),
            models.Index(fields=["offering", "status"]),
        ]

    @property
    def is_guest(self) -> bool:
        """Bu sətir başqa (alt) qrupdan əlavə olunmuş tələbədirmi."""
        return self.source_group_id is not None

    def clean(self):
        """Validate transfer lineage in Python; PostgreSQL repeats it in a trigger."""
        super().clean()
        if self.superseded_by_id is None:
            return

        errors = {}
        successor = self.superseded_by
        if self.status != self.Status.DROPPED:
            errors["status"] = "Əvəzlənmiş qeydiyyat tarixçə statusunda olmalıdır."
        if self.pk is not None and successor.pk == self.pk:
            errors["superseded_by"] = "Qeydiyyat özünü əvəz edə bilməz."
        elif successor.organization_id != self.organization_id:
            errors["superseded_by"] = "Əvəz edən qeydiyyat eyni təşkilata aid olmalıdır."
        elif successor.student_id != self.student_id:
            errors["superseded_by"] = "Əvəz edən qeydiyyat eyni tələbəyə aid olmalıdır."
        elif self.offering_id and successor.offering_id:
            source_offering = self.offering
            target_offering = successor.offering
            if source_offering.subject_id != target_offering.subject_id:
                errors["superseded_by"] = "Əvəz edən qeydiyyat eyni fənnə aid olmalıdır."
            elif source_offering.period_id != target_offering.period_id:
                errors["superseded_by"] = "Əvəz edən qeydiyyat eyni akademik dövrə aid olmalıdır."

        if "superseded_by" not in errors and self.pk is not None:
            seen = {self.pk}
            cursor = successor
            while cursor is not None:
                if cursor.pk in seen:
                    errors["superseded_by"] = "Qeydiyyat əvəzləmə zəncirində dövr yarana bilməz."
                    break
                seen.add(cursor.pk)
                cursor = cursor.superseded_by

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.student_id} → {self.offering_id} ({self.kind})"


class GroupElectiveChoice(UUIDModel, TimeStampedModel):
    """A GROUP's decision for one elective block in one semester.

    In the AZ university model the elective is chosen at group level: once the
    group's choice is recorded, every group member is enrolled in the chosen
    subject (roadmap §2.5). Enforced one-choice-per (group, period, block)."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="group_elective_choices"
    )
    group = models.ForeignKey("organizations.OrgUnit", on_delete=models.CASCADE, related_name="group_elective_choices")
    period = models.ForeignKey(
        "organizations.AcademicPeriod", on_delete=models.PROTECT, related_name="group_elective_choices"
    )
    elective_group = models.CharField(max_length=50, help_text="CurriculumSubject.elective_group blok adı.")
    chosen_subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="group_elective_choices")
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="group_elective_decisions",
    )

    objects = models.Manager()

    class Meta:
        verbose_name = pgettext_lazy("registrar.model.group_elective.meta", "group elective choice")
        verbose_name_plural = pgettext_lazy("registrar.model.group_elective.meta", "group elective choices")
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "group", "period", "elective_group"],
                name="uniq_group_elective_block",
            ),
        ]

    def __str__(self):
        return f"{self.group_id} · {self.elective_group} → {self.chosen_subject.code}"


# ── Dərs cədvəli (timetable, U4) ─────────────────────────────────────────────
#
# Həftəlik təkrarlanan dərs slotu: fənn (offering) + həftənin günü + vaxt +
# auditoriya. Qrup və müəllim offering-dən gəlir. Konflikt yoxlaması (eyni qrup /
# müəllim / otaq × gün+vaxt üst-üstə düşməsin) servis qatındadır. Görünüş rol-
# aware: tələbə öz qrupunun, müəllim öz slotlarının cədvəlini görür.


class WeekType(models.TextChoices):
    ALL = "all", pgettext_lazy("registrar.week_type", "Every week")
    ODD = "odd", pgettext_lazy("registrar.week_type", "Odd weeks")  # üst həftə
    EVEN = "even", pgettext_lazy("registrar.week_type", "Even weeks")  # alt həftə


class SlotKind(models.TextChoices):
    """Cədvəl hüceyrəsinin dərs növü — rəng kodu və jurnal dərs növü ilə eyni dəyərlər."""

    LECTURE = "lecture", pgettext_lazy("registrar.slot_kind", "Lecture")
    SEMINAR = "seminar", pgettext_lazy("registrar.slot_kind", "Seminar")
    LAB = "lab", pgettext_lazy("registrar.slot_kind", "Laboratory")


class ScheduleSlot(ReferenceIdentityValidationMixin, UUIDModel, TimeStampedModel):
    """One weekly recurring class slot (a timetable row)."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="schedule_slots"
    )
    offering = models.ForeignKey(CourseOffering, on_delete=models.CASCADE, related_name="schedule_slots")
    weekday = models.PositiveSmallIntegerField(help_text="Həftənin günü (1=Bazar ertəsi … 7=Bazar).")
    start_time = models.TimeField()
    end_time = models.TimeField()
    room = models.CharField(max_length=64, blank=True, help_text="Auditoriya (opsional).")
    week_type = models.CharField(max_length=8, choices=WeekType.choices, default=WeekType.ALL)
    kind = models.CharField(
        max_length=16,
        choices=SlotKind.choices,
        default=SlotKind.LECTURE,
        help_text="Dərs növü (mühazirə/məşğələ/laboratoriya) — cədvəl rəng kodu.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    objects = models.Manager()

    class Meta:
        ordering = ["weekday", "start_time"]
        verbose_name = pgettext_lazy("registrar.model.slot.meta", "schedule slot")
        verbose_name_plural = pgettext_lazy("registrar.model.slot.meta", "schedule slots")
        indexes = [models.Index(fields=["organization", "offering", "weekday"])]

    def __str__(self):
        return f"{self.offering_id} · gün {self.weekday} {self.start_time}-{self.end_time}"
