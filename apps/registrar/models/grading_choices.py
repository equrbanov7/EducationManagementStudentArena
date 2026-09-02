"""Elektron jurnal / qiymətləndirmə enum-ları (``TextChoices``).

Bu enum-lar model tərifindən ASILI DEYİL — onları ayrı modulda saxlamaq
``grading.py``-ni modul-ölçü büdcəsi altında saxlayır. Bütün adlar geriyə
uyğunluq üçün ``grading.py``-dən (deməli ``apps.registrar.models``-dən də)
əvvəlki kimi import oluna bilər.
"""

from django.db import models
from django.utils.translation import pgettext_lazy


class LessonKind(models.TextChoices):
    LECTURE = "lecture", pgettext_lazy("registrar.lesson_kind", "Lecture")  # yalnız iə/qb
    SEMINAR = "seminar", pgettext_lazy("registrar.lesson_kind", "Seminar")  # iə/qb + bal
    LAB = "lab", pgettext_lazy("registrar.lesson_kind", "Laboratory")  # iə/qb + bal


class AttendanceStatus(models.TextChoices):
    PRESENT = "present", pgettext_lazy("registrar.attendance", "Present")  # iştirak (iə)
    ABSENT = "absent", pgettext_lazy("registrar.attendance", "Absent")  # qayıb (qb)
    # Üzrlü qayıb (ü/q): YALNIZ rəsmi sənədli jurnal-düzəliş axını ilə qoyulur
    # (apps/registrar/corrections.py) — müəllim UI-ında seçim kimi YOXDUR.
    # Qayıb-limit hesabına DAXİL DEYİL (absence_hours bunu saymır).
    EXCUSED = "excused", pgettext_lazy("registrar.attendance", "Excused absence")


class ApprovalStatus(models.TextChoices):
    """Jurnalın kilid vəziyyəti — indi YALNIZ İKİ məna daşıyır.

    SAHİBİN QƏRARI (2026-08): müəllim → kafedra → dekan təsdiq zənciri LƏĞV
    edildi. Müəllim balı yazır və bitir; semestr sonunda RİM jurnalları toplu
    BAĞLAYIR (bax :mod:`apps.registrar.journal_close`).

    * ``DRAFT``    — jurnal açıqdır (müəllim adi kilid qaydaları çərçivəsində yazır);
    * ``APPROVED`` — jurnal BAĞLIDIR (``is_published=True`` ilə birlikdə —
      CheckConstraint ``registrar_scheme_publish_state_valid`` bu cütü qoruyur).

    ``SUBMITTED`` / ``CHAIR_APPROVED`` / ``RETURNED`` sahə dəyərləri QƏSDƏN
    saxlanılır (köhnə sətirlərin oxunması + legacy import J7 fazası sxemə
    bağlıdır), lakin YENİ heç bir kod onları yazmır; miqrasiya
    ``registrar.0048`` mövcud sətirləri DRAFT-a endirir.
    """

    DRAFT = "draft", pgettext_lazy("registrar.approval", "Draft")
    #: LEGACY — artıq yaradılmır (təsdiq zənciri ləğv edilib).
    SUBMITTED = "submitted", pgettext_lazy("registrar.approval", "Submitted (awaiting chair)")
    #: LEGACY — artıq yaradılmır.
    CHAIR_APPROVED = "chair_approved", pgettext_lazy("registrar.approval", "Chair approved (awaiting dean)")
    APPROVED = "approved", pgettext_lazy("registrar.approval", "Approved (official)")
    #: LEGACY — artıq yaradılmır.
    RETURNED = "returned", pgettext_lazy("registrar.approval", "Returned for revision")


class ComponentKind(models.TextChoices):
    """Komponentin tipi — UI hansı tabda göstərəcəyini və xüsusi davranışı seçir.

    KOLLOKVIUM: 3 kollokvium (K1-K3) + keçirilmə tarixi (``held_on``).
    SELF_WORK: sərbəst iş — balı mövzu-çeklist cəmindən avtomatik yazılır."""

    GENERIC = "generic", pgettext_lazy("registrar.component_kind", "Generic")
    KOLLOKVIUM = "kollokvium", pgettext_lazy("registrar.component_kind", "Kollokvium")
    SELF_WORK = "self_work", pgettext_lazy("registrar.component_kind", "Independent work")


class ResitReason(models.TextChoices):
    ABSENCE = "absence", pgettext_lazy("registrar.resit_reason", "Barred by absence")
    TOTAL = "total", pgettext_lazy("registrar.resit_reason", "Total below pass mark")
    EXAM = "exam", pgettext_lazy("registrar.resit_reason", "Exam below minimum")


class ResitStatus(models.TextChoices):
    ELIGIBLE = "eligible", pgettext_lazy("registrar.resit_status", "Eligible")
    COMPLETED = "completed", pgettext_lazy("registrar.resit_status", "Completed")
