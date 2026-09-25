"""``apps.surveys`` PUBLIC API — digər modullar (accounts kabineti, F2 analitika UI)
YALNIZ bu fasaddan istifadə edir.

══════════════════════════════════════════════════════════════════════════════
ANONİMLİK ZƏMANƏTLƏRİ (dəyişdirməzdən əvvəl oxu)
══════════════════════════════════════════════════════════════════════════════
* ``SurveyReceipt`` (kim doldurdu) və ``SurveyResponse``/``SurveyAnswer`` (nə yazdı)
  ortaq açarsızdır; cavabda tələbə FK-sı, vaxt damğası, tarix YOXDUR; bütün PK-lar
  təsadüfi UUID-dir. Bu API heç vaxt ikisini birləşdirmir və heç bir funksiya
  cavab id-si, qəbz, tələbə və ya vaxt qaytarmır.
* k-anonimlik: ``n < k`` qrupun qiymətləri ``None`` + ``suppressed=True``;
  ``k`` = kampaniyanın ``min_group_size``-ı (≥ 3; bir neçə kampaniya → ən böyüyü).
  **Tamamlayıcı qayda**: daraldıcı filtr (fənn/qrup/ixtisas/kurs) varsa, daralmamış
  ümumi sayla fərq ``0 < N−n < k`` olduqda da gizlədilir (çıxma hücumu).
* Sərbəst mətn yalnız dəst ``k``-nı keçəndə, identifikatorsuz, təsadüfi sırada.
* Cavab snapshot-u (fənn, açılışın qrupu, müəllimin kafedrası/fakültəsi, ixtisas,
  kurs) açılışdan/müəllimdən törəyir — tələbəyə aid atribut YOXDUR (ümumi bölmə
  istisna: tələbənin qrupu/ixtisası/fakültəsi, k-həddi altında).
* QALIQ RİSK: DB-yə birbaşa çıxışı olan administrator ``xmin`` (eyni tranzaksiya),
  fiziki sıra (``ctid``) və ya veb-jurnaldakı POST vaxtı ilə cavabı qəbzə bağlaya
  bilər; tək tələbəli açılışda cavab onsuz da bir nəfərindir (UI/API onu
  göstərmir). Qoruma tətbiq istifadəçilərinə qarşı tamdır, DB adminə qarşı deyil.
* Fərqləndirmə (differencing) hücumuna qarşı qoruma bir səviyyəlidir (tamamlayıcı
  qayda); müxtəlif filtr kombinasiyalarının ardıcıl çıxılması nəzəri olaraq qalır —
  F2 UI xam sətir ixracı ETMƏMƏLİDİR, yalnız bu funksiyaların nəticələrini göstərməlidir.

══════════════════════════════════════════════════════════════════════════════
ƏHATƏ (scope) — hər funksiya ``scope`` qəbul edir
══════════════════════════════════════════════════════════════════════════════
``scope = results_scope(user, organization, request=None)`` → ``UnitScope``
(``apps.organizations.public``): ``is_org_wide`` / ``is_unit_scoped`` /
``has_structure_access``. Kafedra müdiri → öz kafedrası (müəllim cavabı
``teacher_department`` alt-ağacı, ümumi cavab ``group`` alt-ağacı); tədris şöbəsi,
keyfiyyət rolları, prorektor, rektor, RİM rəhbəri, superadmin → bütün təşkilat.
``has_structure_access`` yalandırsa bütün funksiyalar boş/suppressed qaytarır.

══════════════════════════════════════════════════════════════════════════════
FİLTRLƏR
══════════════════════════════════════════════════════════════════════════════
``ResultFilters(campaign_ids=(), faculty_id=None, department_id=None, teacher_id=None,
subject_id=None, group_id=None, program_id=None, course_year=None, question_code="",
text_query="")`` — ``ResultFilters.from_params(request.GET)`` GET açarları:
``campaign`` (çox), ``faculty``, ``department``, ``teacher``, ``subject``, ``group``,
``program``, ``course_year``, ``question``, ``q``. ``campaign_ids`` boşdursa BÜTÜN
kampaniyalar birləşir.

══════════════════════════════════════════════════════════════════════════════
FUNKSİYALAR VƏ QAYTARDIQLARI
══════════════════════════════════════════════════════════════════════════════
Ortaq «metrics» açarları: ``n`` (cavab sayı), ``suppressed`` (bool), ``avg_overall``
(1–10), ``likert_index`` (1–5, indeksə daxil Likert sualları), ``likert_index_pct``
(0–100), ``recommend_top2`` (0–1, «tövsiyə edərdim» 4–5 payı).

* ``campaigns_for(organization)`` → ``[{"id", "period_id", "period_name",
  "academic_year", "start_date", "status", "effective_status", "opens_on",
  "closes_on", "grace_until", "mandatory", "min_group_size", "opened_via",
  "responses", "receipts"}]`` (yeni dövr birinci).
* ``summary(organization, scope, filters)`` → ``{"k", "campaign_ids", **metrics,
  "teachers", "questions": [{"code", "kind", "section", "text", "n", "avg", "top2"}],
  "general_n", "general_questions": [...], "participation": {"receipts",
  "expected", "rate", "general_receipts"}}``.
* ``teacher_table(organization, scope, filters, order_by="-avg_overall", limit=500)``
  → ``{"k", "org": metrics, "rows": [{"teacher_id", "teacher_name",
  "department_id", "department_name", **metrics, "delta_department_overall",
  "delta_org_overall", "delta_department_index", "delta_org_index"}]}``.
  ``order_by``: ``avg_overall`` | ``likert_index`` | ``n`` | ``teacher_name`` (``-`` azalan).
* ``teacher_detail(organization, scope, teacher_id, filters)`` → ``{"found": False}``
  və ya ``{"found": True, "k", "teacher_id", "teacher_name", "department_id",
  "department_name", **metrics, delta_* (4), "questions": [...], "distributions":
  {code: {score: count}}, "offerings": [{"subject_id", "subject_name", "group_id",
  "group_name", **metrics}], "comments": [{"question_code", "text"}], "trend": [...]}``.
* ``distribution(organization, scope, question_code, filters)`` → ``{"code", "kind",
  "k", "n", "suppressed", "buckets": [{"score", "count"}]}``.
* ``trend(organization, scope, teacher_id=None, department_id=None, faculty_id=None,
  limit=12)`` → ``[{"campaign_id", "period_id", "period_name", "academic_year", "k",
  **metrics}]`` (köhnədən yeniyə; teacher/department/faculty yoxdursa — təşkilat).
* ``breakdown(organization, scope, filters, by="faculty"|"department"|"subject"|
  "program"|"course_year"|"group", section="teacher"|"general")`` → ``{"k", "rows":
  [{"key", "label", **metrics, "satisfaction", "facilities"}]}``.
* ``general_suggestions(organization, scope, filters, query="", limit=50, offset=0)``
  → ``{"k", "n", "suppressed", "items": [{"question_code", "text"}]}``.
* ``filter_options(organization, scope, campaign_ids=None)`` → ``{"faculties",
  "departments", "teachers", "subjects", "groups", "programs"}`` hər biri
  ``[{"id", "label", "n"}]`` (yalnız əhatədəki cavablarda olan dəyərlər).
* ``search_teachers(organization, scope, query, campaign_ids=None, limit=20)`` →
  ``[{"id", "label", "n"}]`` (az/ing klaviaturaya dözümlü, ``core.search_text``).
* ``participation(organization, scope, filters, campaign_ids)`` / ``daily_timeline(
  campaign_ids, scope)`` → iştirak sayları (şəxs siyahısı YOX).
* ``question_catalog(campaign)`` → sual siyahısı ``[{"code", "section", "kind", "text",
  "required", "in_index"}]``.

Sorğu büdcəsi: hər funksiya sabit sayda aqreqat sorğu işlədir (sətir sayından
asılı deyil); ``summary`` iştirak hesabı kampaniya başına ~6 sorğu əlavə edir.

══════════════════════════════════════════════════════════════════════════════
KABİNET (accounts) ÜÇÜN
══════════════════════════════════════════════════════════════════════════════
* ``cabinet_state(user)`` — qapı middleware-inin bu sorğuda hesabladığı vəziyyət
  (``None`` — tələbə deyil / açıq kampaniya yoxdur / view-as). Sıfır sorğu.
* ``student_section_visible(user)`` / ``pending_badge(user)`` — «Anonim sorğu»
  bölməsi və ``evaluation_survey`` sayğacı üçün (sıfır sorğu).
* ``can_view_results`` / ``can_manage_campaigns`` / ``PERM_RESULTS_VIEW`` / ``PERM_MANAGE``.
"""

from __future__ import annotations

from django.db.models import Count
from django.utils import timezone
from django.utils.translation import pgettext

from .constants import PERM_MANAGE, PERM_RESULTS_VIEW, Section
from .services.access import can_manage_campaigns, can_view_results, results_scope
from .services.analytics import distribution, summary, teacher_table
from .services.analytics_detail import (
    breakdown,
    filter_options,
    general_suggestions,
    search_teachers,
    teacher_detail,
    trend,
)
from .services.filters import ResultFilters
from .services.participation import daily_timeline, participation


def cabinet_state(user):
    return getattr(user, "_survey_gate_state", None)


def student_section_visible(user) -> bool:
    state = cabinet_state(user)
    return bool(state is not None and state.total > 0)


def pending_badge(user) -> int:
    state = cabinet_state(user)
    return int(state.pending) if state is not None else 0


def campaigns_for(organization) -> list:
    """Kampaniyalar (yeni dövr birinci) — cavab/qəbz SAYLARI ilə (bax modul sənədi)."""
    from .models import SurveyCampaign, SurveyReceipt, SurveyResponse

    if organization is None:
        return []
    today = timezone.localdate()
    campaigns = list(
        SurveyCampaign.objects.filter(organization=organization)
        .select_related("period")
        .order_by("-period__start_date", "-created_at")
    )
    ids = [campaign.pk for campaign in campaigns]
    # İki ayrı qruplaşdırılmış sorğu: iki əks əlaqə üzrə tək JOIN sətirləri çoxaldardı.
    responses = dict(
        SurveyResponse.objects.filter(campaign_id__in=ids, scope=Section.TEACHER)
        .values("campaign_id")
        .annotate(c=Count("id"))
        .values_list("campaign_id", "c")
    )
    receipts = dict(
        SurveyReceipt.objects.filter(campaign_id__in=ids, scope=Section.TEACHER)
        .values("campaign_id")
        .annotate(c=Count("id"))
        .values_list("campaign_id", "c")
    )
    return [
        {
            "id": campaign.pk,
            "period_id": campaign.period_id,
            "period_name": campaign.period.name,
            "academic_year": campaign.period.academic_year,
            "start_date": campaign.period.start_date,
            "status": campaign.status,
            "effective_status": campaign.effective_status(today),
            "opens_on": campaign.opens_on,
            "closes_on": campaign.closes_on,
            "grace_until": campaign.grace_until,
            "mandatory": campaign.mandatory,
            "min_group_size": campaign.min_group_size,
            "opened_via": campaign.opened_via,
            "responses": responses.get(campaign.pk, 0),
            "receipts": receipts.get(campaign.pk, 0),
        }
        for campaign in campaigns
    ]


def question_catalog(campaign) -> list:
    return [
        {
            "code": question.code,
            "section": question.section,
            "kind": question.kind,
            "text": pgettext("surveys.question", question.text),
            "required": question.required,
            "in_index": question.in_index,
        }
        for question in campaign.template.questions.order_by("order", "code")
    ]


__all__ = [
    "PERM_MANAGE",
    "PERM_RESULTS_VIEW",
    "ResultFilters",
    "Section",
    "breakdown",
    "cabinet_state",
    "campaigns_for",
    "can_manage_campaigns",
    "can_view_results",
    "daily_timeline",
    "distribution",
    "filter_options",
    "general_suggestions",
    "participation",
    "pending_badge",
    "question_catalog",
    "results_scope",
    "search_teachers",
    "student_section_visible",
    "summary",
    "teacher_detail",
    "teacher_table",
    "trend",
]
