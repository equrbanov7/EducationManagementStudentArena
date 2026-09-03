"""Fənnin başqa müəllimə TƏHVİLİ — icazə, əhatə, blokerlər və önizləmə (OXU qatı).

Yazma qatı ayrıdır: :mod:`apps.registrar.handover_actions`.

──────────────────────────────────────────────────────────────────────────────
QƏRARLAR (sahibin sualları ilə eyni sırada)
──────────────────────────────────────────────────────────────────────────────

**1. Nə köçür?** YALNIZ ``CourseOffering.instructor``. Jurnal sahibliyi bu
sahədən oxunur (``journal_access._is_live_assigned_instructor``), ona görə bir
sahə kifayətdir. KöçürülMƏYƏNlər və səbəbləri :mod:`apps.registrar.models.handover`
başlığında sənədlidir (bal, davamiyyət, ``Lesson.instructor``, sillabus).

**Sillabus (yalnız oxundu, DƏYİŞDİRİLMƏDİ).** ``apps.syllabus``-da sənəd
MÜƏLLİFƏ (``SyllabusDossier.author``) bağlıdır, açılışa yox; redaktə hüququ da
müəlliflikdən gəlir. Deməli təhvildən sonra:

* köhnə müəllimin sillabusu ONUN adında qalır — təsdiqlənmiş akademik sənəddir,
  müəllifini dəyişmək saxtalaşdırma olardı;
* yeni müəllim həmin fənn üçün ÖZ dossierini açır (adi müəllim axını) və ya
  kafedra ``syllabus.manage`` ilə köçürməni ayrıca aparır;
* jurnaldakı «sillabus yoxdur» xəbərdarlığı (``syllabus_notice``) yeni müəllimə
  bunu onsuz da xatırladır — yəni boşluq səssiz qalmır.

Bu axın QƏSDƏN avtomatlaşdırılmır: sillabus köçürməsi paralel iş axınındadır və
təhvil əməli onun sxemindən asılı olmamalıdır.

**2. Kim edə bilər?** ``journal.reassign`` + struktur əhatəsi (fail-closed).
RİM/prorektor org-wide, dekan öz fakültəsi, kafedra müdiri öz kafedrası.
Müəllimin özündə açar YOXDUR; üstəlik :func:`blockers` aktoru açılışın CARİ
müəllimi olanda ayrıca bloklayır ki, açarı təsadüfən almış müəllim öz jurnalını
başqasının üstünə ata bilməsin.

**3. Tarixi/bağlı semestrlər — TƏHVİL YOXDUR.** İki blokerlə:
``journal_closed`` (RİM jurnalı bağlayıb) və ``past_period`` (dövr bitib və cari
deyil). Səbəb: bağlanmış jurnal YEKUNLAŞMIŞ sənəddir — transkript, giriş balı və
imtahan buraxılışı ondan oxunur. Müəllimini sonradan dəyişmək «bu balı kim
yazdı» sualının cavabını dəyişər, halbuki balı yazan adam dəyişmir. Səhv
təyinatın düzəlişi üçün AYRICA yol var: ``revert`` (geri qaytarma).

⚠️ **Geri qaytarma da EYNİ blokerlərdən keçir.** Əvvəllər burada «revert bağlı
jurnala toxunmur, çünki təhvilin özü heç vaxt bağlı jurnalda baş verə bilmir»
yazılmışdı — bu arqument SƏHVDİR: təhvil ilə geri qaytarma ARASINDA vaxt keçir
və dövr məhz o aralıqda bitə bilər (jurnalını bağlamayan universitetdə dekan
beləcə keçmiş semestrin sahibliyini istənilən vaxt çevirə bilərdi). Ona görə
``handover_actions.revert`` :data:`~apps.registrar.handover_actions.REVERT_BLOCKER_CODES`
dəsti üzrə :func:`blockers` çağırır.

Bağlı semestrdə həqiqətən düzəliş lazımdırsa kanonik yol dəyişməyib: RİM
``journal.close`` ilə jurnalı açır, təhvil edilir, yenidən bağlanır — üç addımın
hər biri auditli.
"""

from __future__ import annotations

import datetime

from apps.registrar import journal_scope
from apps.registrar.exam_eligibility import _LOCKED_STATUSES
from apps.registrar.models import AssessmentScheme, CourseOffering, TeachingHandover

#: Fənni başqa müəllimə təhvil vermək icazəsi (kataloq: organizations.permissions).
HANDOVER_PERMISSION = "journal.reassign"

#: Səbəb mətninin sərhədləri — ``rim.lifecycle`` ilə eyni ölçülər.
MIN_REASON_LENGTH = 3
MAX_REASON_LENGTH = 1000

#: Blokerlərin kanonik kodları. UI mətnləri ``apps/accounts/views/handover``-dədir;
#: burada YALNIZ kod qalır ki, servis qatı tərcümədən asılı olmasın.
BLOCKER_CODES = (
    "outside_scope",
    "journal_closed",
    "past_period",
    "offering_inactive",
    "same_instructor",
    "target_not_eligible",
    "actor_is_current_instructor",
    "no_target",
)


def _org_unit_model():
    from django.apps import apps as django_apps

    return django_apps.get_model("organizations", "OrgUnit")


# ── İcazə + əhatə ────────────────────────────────────────────────────────────


def actor_scope(user, organization):
    """Aktorun ``journal.reassign`` struktur əhatəsi (``UnitScope``).

    MODUL SƏRHƏDİ: registrar ``apps.organizations``-u Python səviyyəsində import
    ETMİR — model app registry ilə həll olunur (``journal_scope`` naxışı).
    ``get_permission_scope`` özü ``organization is None`` / anonim istifadəçi
    hallarında BOŞ scope qaytarır, ona görə burada ayrıca yoxlama lazım deyil.
    """
    return _org_unit_model().user_permission_scope(user, organization, HANDOVER_PERMISSION)


def can_reassign(user, organization) -> bool:
    """İcazə struktur əhatəsi verirmi (org və ya unit) — fail-closed."""
    return actor_scope(user, organization).has_structure_access


def offering_in_scope(user, organization, offering) -> bool:
    """Bu açılış aktorun alt-ağacındadırmı (qrupsuz açılış yalnız org-wide üçün)."""
    return journal_scope.offering_in_actor_scope(user, organization, offering, permission=HANDOVER_PERMISSION)


def scoped_offerings(user, organization):
    """Aktorun təhvil verə biləcəyi açılışların BAZA queryset-i (fail-closed).

    Əhatəsi olmayan aktor BOŞ queryset alır — çağıran unutsa belə heç nə sızmır.
    Blokerlər (bağlı jurnal, keçmiş dövr) burada SÜZÜLMÜR: siyahı onları
    göstərməli, amma «təhvil oluna bilməz» kimi işarələməlidir (istifadəçi niyə
    edə bilmədiyini görməlidir, sətir sadəcə yoxa çıxmamalıdır).
    """
    scope = actor_scope(user, organization)
    if not scope.has_structure_access:
        return CourseOffering.objects.none()
    queryset = CourseOffering.objects.filter(organization=organization)
    if scope.is_org_wide:
        return queryset
    units = _org_unit_model().objects.filter(organization=organization).filter(scope.unit_subtree_q())
    return queryset.filter(group__in=units.values("pk"))


# ── Blokerlər ────────────────────────────────────────────────────────────────


def closed_offering_ids(offering_ids) -> set:
    """Jurnalı BAĞLI açılışlar (tək sorğu, sxem YARATMADAN).

    Kilid meyarı ``gradebook.journal_is_locked`` ilə eyni mənbədəndir
    (``exam_eligibility._LOCKED_STATUSES``) — iki tərif sürüşməsin. Sxemi olmayan
    açılış bağlı sayılmır: təzə yaradılan sxem heç vaxt ``is_published`` olmur.
    """
    ids = [oid for oid in offering_ids if oid is not None]
    if not ids:
        return set()
    rows = AssessmentScheme.objects.filter(offering_id__in=ids).values_list(
        "offering_id", "is_published", "approval_status"
    )
    return {oid for oid, published, status in rows if published or status in _LOCKED_STATUSES}


def period_is_past(period, today) -> bool:
    """Dövr TARİXİDİRMİ — bitib və cari kimi işarələnməyib.

    ``is_current`` üstünlük təşkil edir: universitet semestri rəsmi olaraq
    uzatsa (son tarix keçsə də) təhvil bağlanmamalıdır.
    """
    if period is None:
        return True
    if getattr(period, "is_current", False):
        return False
    end_date = _as_date(getattr(period, "end_date", None))
    return bool(end_date and end_date < today)


def _as_date(value):
    """``DateField`` dəyərini date-ə gətirir (yaddaşdakı obyektdə sətir ola bilər).

    ``AcademicPeriod(... end_date="2025-01-31")`` kimi yaradılmış, hələ DB-dən
    oxunmamış obyektlərdə sahə SƏTİRDİR; birbaşa müqayisə ``TypeError`` verirdi.
    Blokerlər səssizcə çökməməlidir — fail-closed davranış üçün tarix normallaşır.
    """
    if value is None or isinstance(value, datetime.date):
        return value
    try:
        return datetime.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def blockers(offering, *, actor=None, organization=None, closed_ids=None, today=None, new_instructor_id=None) -> list:
    """Bu açılışın təhvilinə mane olan kodların siyahısı (boş = mümkündür).

    Toplu səth üçün ``closed_ids`` və ``today`` xaricdən verilir ki, hər sətir
    üçün ayrıca sorğu getməsin (N+1 qarşısı).
    """
    from django.utils import timezone

    today = today or timezone.localdate()
    organization = organization or offering.organization
    codes = []

    if actor is not None and not offering_in_scope(actor, organization, offering):
        codes.append("outside_scope")
    if not offering.is_active:
        codes.append("offering_inactive")

    closed = closed_ids if closed_ids is not None else closed_offering_ids([offering.pk])
    if offering.pk in closed:
        codes.append("journal_closed")
    if period_is_past(offering.period, today):
        codes.append("past_period")

    # Müəllim ÖZ jurnalını başqasına ata bilməz (səlahiyyət ayrılığı).
    if actor is not None and offering.instructor_id and offering.instructor_id == getattr(actor, "pk", None):
        codes.append("actor_is_current_instructor")

    if new_instructor_id is not None:
        if not new_instructor_id:
            codes.append("no_target")
        elif str(new_instructor_id) == str(offering.instructor_id or ""):
            codes.append("same_instructor")
        elif not is_eligible_target(organization, new_instructor_id):
            codes.append("target_not_eligible")
    return codes


# ── Hədəf müəllimlər ─────────────────────────────────────────────────────────


def eligible_target_ids(organization) -> set:
    """Bu təşkilatda bal yaza bilən (``grade.input``) AKTİV üzvlərin id-ləri.

    Mövcud ``integrity.eligible_instructor_user_ids`` təkrar işlədilir — açılış
    forması (``CourseOfferingForm``) da eyni siyahını işlədir, yəni təhvil heç
    vaxt formanın qəbul etməyəcəyi müəllimi təyin edə bilmir.
    """
    from apps.registrar.integrity import eligible_instructor_user_ids

    return eligible_instructor_user_ids(organization=organization)


def is_eligible_target(organization, user_id) -> bool:
    if not user_id:
        return False
    return str(user_id) in {str(pk) for pk in eligible_target_ids(organization)}


def target_queryset(organization, *, search="", exclude_ids=()):
    """Hədəf müəllim axtarışı — ad/soyad/istifadəçi adı/e-poçt üzrə.

    Səhifələmə çağıran tərəfdədir (endpoint ``page``/``page_size`` ilə kəsir).
    """
    from django.contrib.auth import get_user_model
    from django.db.models import Q

    queryset = get_user_model().objects.filter(pk__in=eligible_target_ids(organization), is_active=True)
    if exclude_ids:
        queryset = queryset.exclude(pk__in=[pk for pk in exclude_ids if pk])
    term = (search or "").strip()
    if term:
        queryset = queryset.filter(
            Q(first_name__icontains=term)
            | Q(last_name__icontains=term)
            | Q(username__icontains=term)
            | Q(email__icontains=term)
        )
    return queryset.order_by("last_name", "first_name", "username")


# ── Köhnə müəllimin YALNIZ-OXU görünüşü ──────────────────────────────────────


def is_handover_observer(user, offering) -> bool:
    """Bu istifadəçi açılışı təhvil VERMİŞ köhnə müəllimdirmi (yalnız-oxu).

    SAHİBİN SUALI: «köhnə müəllimin jurnal görünüşü itməlidirmi?»
    QƏRAR: yazma hüququ DƏRHAL gedir, görünüş isə qalır. Səbəb: müəllim öz
    yazdığı balın arxasında durur — apellyasiya, komissiya və ya sadəcə «mən nə
    qoymuşdum» sualı təhvildən sonra da gəlir. Görünüşü kəsmək onu öz işinin
    qeydindən məhrum edərdi; yazma hüququnu saxlamaq isə jurnalın iki sahibi
    olması demək olardı. İkisi AYRILIR.

    Görünüş qeyri-müəyyən müddətə açıq qalmır: yalnız GERİ QAYTARILMAMIŞ təhvil
    sətri sayılır və zəncirin sonunda kim varsa (``to_instructor``) yazan odur.
    """
    user_id = getattr(user, "pk", None)
    if not user_id or not getattr(user, "is_authenticated", False):
        return False
    if offering.instructor_id == user_id:
        return False
    return TeachingHandover.objects.filter(
        offering=offering,
        from_instructor_id=user_id,
        reverted_at__isnull=True,
    ).exists()


def observer_offering_ids(user, organization) -> set:
    """Bu istifadəçinin yalnız-oxu görə bildiyi (təhvil verdiyi) açılışlar."""
    user_id = getattr(user, "pk", None)
    if not user_id or organization is None:
        return set()
    return set(
        TeachingHandover.objects.filter(
            organization=organization,
            from_instructor_id=user_id,
            reverted_at__isnull=True,
        )
        .exclude(offering__instructor_id=user_id)
        .values_list("offering_id", flat=True)
    )


# ── Tarixçə ──────────────────────────────────────────────────────────────────


def offering_history(offering):
    """Bu açılışın təhvil tarixçəsi (ən yenisi əvvəldə)."""
    return (
        TeachingHandover.objects.filter(offering=offering)
        .select_related("from_instructor", "to_instructor", "performed_by", "reverted_by")
        .order_by("-created_at")
    )


def scoped_history(user, organization):
    """Aktorun əhatəsindəki bütün təhvillər (bölmənin «tarixçə» tabı)."""
    offerings = scoped_offerings(user, organization)
    return (
        TeachingHandover.objects.filter(organization=organization, offering__in=offerings.values("pk"))
        .select_related(
            "offering",
            "offering__subject",
            "offering__group",
            "offering__period",
            "from_instructor",
            "to_instructor",
            "performed_by",
        )
        .order_by("-created_at")
    )


__all__ = [
    "BLOCKER_CODES",
    "HANDOVER_PERMISSION",
    "MAX_REASON_LENGTH",
    "MIN_REASON_LENGTH",
    "actor_scope",
    "blockers",
    "can_reassign",
    "closed_offering_ids",
    "eligible_target_ids",
    "is_eligible_target",
    "is_handover_observer",
    "observer_offering_ids",
    "offering_history",
    "offering_in_scope",
    "period_is_past",
    "scoped_history",
    "scoped_offerings",
    "target_queryset",
]
