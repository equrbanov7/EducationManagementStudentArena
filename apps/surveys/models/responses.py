"""Tamamlanma qəbzi (şəxsli) və anonim cavab (şəxssiz) — İKİ AYRI cədvəl.

ANONİMLİK MÜQAVİLƏSİ (dəyişdirməzdən əvvəl oxu):

* ``SurveyReceipt`` KİMİN nəyi doldurduğunu sübut edir (tələbə × kampaniya ×
  açılış × müəllim) — «1 müəllim üzrə tələbədən 1 dəfə» qaydası bu cədvəlin
  şərtli unikal məhdudiyyətləridir. Cavabın MƏZMUNU burada YOXDUR.
* ``SurveyResponse`` + ``SurveyAnswer`` cavabın MƏZMUNUNU saxlayır və tələbəyə
  heç bir bağ daşımır: tələbə FK-sı YOXDUR, ``created_at``/``updated_at`` YOXDUR,
  tarix/saat sahəsi YOXDUR (qəbzin ``completed_on`` günü ilə «eyni gün + eyni
  açılış + eyni müəllim» birləşməsi SQL ilə kimliyi bərpa edərdi), birincil
  açarlar təsadüfi UUID-dir (ardıcıl id-lər daxiletmə sırası ilə qəbzlərə
  «zip» oluna bilərdi).
* Qəbz və cavab EYNİ tranzaksiyada yazılır (ikisi birlikdə və ya heç biri),
  amma ortaq açarları yoxdur; UI/API onları heç vaxt birləşdirmir.
* Cavabın analitika «snapshot»-u yalnız AÇILIŞDAN/MÜƏLLİMDƏN törəyən atributlardır
  (fənn, açılışın qrupu, müəllimin kafedrası/fakültəsi, ixtisas, kurs) — yəni
  cavab «O açılışın hansısa tələbəsi T müəllimini qiymətləndirdi»dən artıq heç
  nə demir. Ümumi bölmə cavabı tələbənin öz qrupunu/ixtisasını daşıyır —
  nəticələr k-həddi altında gizlədilir.

QALIQ RİSK (bilinən, sənədləşdirilmiş): DB-yə birbaşa çıxışı olan administrator
MVCC sistem sütunları (``xmin`` — eyni tranzaksiya), fiziki daxiletmə sırası
(``ctid``) və ya veb-server jurnalındakı POST vaxtı ilə cavabı qəbzə bağlaya
bilər; tək tələbəli açılışda isə cavab onsuz da tək nəfərindir. Tətbiq
istifadəçiləri (UI/API) üçün qoruma tamdır; bax ``apps/surveys/public.py``.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import pgettext_lazy

from ..constants import Section
from .campaigns import SurveyCampaign
from .templates import SurveyQuestion

_CTX = "surveys.model"


class SurveyReceipt(models.Model):
    """Tamamlanma sübutu — cavabın məzmunu YOXDUR."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="+")
    campaign = models.ForeignKey(SurveyCampaign, on_delete=models.CASCADE, related_name="receipts")
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    scope = models.CharField(max_length=16, choices=Section.choices)
    offering = models.ForeignKey(
        "registrar.CourseOffering", null=True, blank=True, on_delete=models.CASCADE, related_name="+"
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="+"
    )
    #: İştirak faizinin kafedra əhatəsində sayılması üçün (müəllimdən törəyir).
    teacher_department = models.ForeignKey(
        "organizations.OrgUnit", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    completed_on = models.DateField()

    class Meta:
        verbose_name = pgettext_lazy(_CTX, "sorğu qəbzi")
        verbose_name_plural = pgettext_lazy(_CTX, "sorğu qəbzləri")
        constraints = [
            models.UniqueConstraint(
                fields=["campaign", "student", "offering", "teacher"],
                condition=models.Q(scope=Section.TEACHER),
                name="surveys_receipt_teacher_once",
            ),
            models.UniqueConstraint(
                fields=["campaign", "student"],
                condition=models.Q(scope=Section.GENERAL),
                name="surveys_receipt_general_once",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(scope=Section.TEACHER, offering__isnull=False, teacher__isnull=False)
                    | models.Q(scope=Section.GENERAL, offering__isnull=True, teacher__isnull=True)
                ),
                name="surveys_receipt_scope_shape",
            ),
        ]
        indexes = [models.Index(fields=["campaign", "scope"], name="surveys_receipt_camp_scope")]

    def __str__(self):
        return f"receipt<{self.campaign_id}:{self.scope}>"


class SurveyResponse(models.Model):
    """ANONİM cavab — tələbə FK-sı və vaxt damğası QƏSDƏN yoxdur."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="+")
    campaign = models.ForeignKey(SurveyCampaign, on_delete=models.CASCADE, related_name="responses")
    scope = models.CharField(max_length=16, choices=Section.choices)
    offering = models.ForeignKey(
        "registrar.CourseOffering", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    # ── Analitika snapshot-u (cavab anındakı struktur; sonrakı köçürmə tarixçəni dəyişmir) ──
    subject = models.ForeignKey("registrar.Subject", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    group = models.ForeignKey(
        "organizations.OrgUnit", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    teacher_department = models.ForeignKey(
        "organizations.OrgUnit", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    faculty = models.ForeignKey(
        "organizations.OrgUnit", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    program = models.ForeignKey("registrar.Program", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    course_year = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        verbose_name = pgettext_lazy(_CTX, "anonim cavab")
        verbose_name_plural = pgettext_lazy(_CTX, "anonim cavablar")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(scope=Section.GENERAL, offering__isnull=True, teacher__isnull=True)
                | models.Q(scope=Section.TEACHER),
                name="surveys_response_general_shape",
            ),
        ]
        indexes = [
            models.Index(fields=["campaign", "scope"], name="surveys_resp_camp_scope"),
            models.Index(fields=["campaign", "teacher"], name="surveys_resp_camp_teacher"),
            models.Index(fields=["campaign", "teacher_department"], name="surveys_resp_camp_dept"),
            models.Index(fields=["campaign", "faculty"], name="surveys_resp_camp_faculty"),
            models.Index(fields=["campaign", "subject"], name="surveys_resp_camp_subject"),
        ]

    def __str__(self):
        return f"response<{self.campaign_id}:{self.scope}>"


class SurveyAnswer(models.Model):
    """Bir sualın cavabı — SQL aqreqasiyası üçün sətir-sətir (vaxt damğası yoxdur)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="+")
    response = models.ForeignKey(SurveyResponse, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(SurveyQuestion, on_delete=models.PROTECT, related_name="+")
    score = models.SmallIntegerField(null=True, blank=True)
    text = models.TextField(blank=True)

    class Meta:
        verbose_name = pgettext_lazy(_CTX, "sorğu cavabı")
        verbose_name_plural = pgettext_lazy(_CTX, "sorğu cavabları")
        constraints = [
            models.UniqueConstraint(fields=["response", "question"], name="surveys_answer_once"),
            models.CheckConstraint(
                condition=models.Q(score__isnull=True) | models.Q(score__gte=1, score__lte=10),
                name="surveys_answer_score_range",
            ),
        ]
        indexes = [models.Index(fields=["question", "score"], name="surveys_answer_q_score")]

    def __str__(self):
        return f"answer<{self.question_id}>"
