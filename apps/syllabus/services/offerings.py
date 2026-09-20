"""Açılış (``CourseOffering``) → sillabus dosyesi həlli + jurnal VƏZİYYƏT kodu.

Jurnal və tələbə kabineti «bu dərsin sillabusu hanı?» sualını verir. Cavab
modelin ÜÇ qismən UNIQUE məhdudiyyətinin güzgüsüdür və eyni ardıcıllıqla
axtarılır (bax :class:`apps.syllabus.models.Syllabus` docstring-i):

1. ``offering`` üzrə — normal axın (qrup + müəllim konkretdir);
2. ``(subject, period)`` üzrə — semestr səviyyəli dosye, açılış hələ
   bağlanmayıb;
3. ``(subject, author)`` üzrə — köhnə sistemdən köçürülmüş SEMESTRSİZ «baza
   sillabus». Köhnə bazada semestr yoxdur, uydurulmur.

⚠️ Modul-sərhəd: burada ``apps.registrar`` İDXAL EDİLMİR — funksiyalar xam
ID-lər qəbul edir. ``registrar → syllabus`` tək istiqamətli qalır, əks kənar
açılmır (``scripts/module_deps.py``).
"""

from __future__ import annotations

from django.db.models import Case, IntegerField, Q, Value, When

from ..constants import OPEN_STATUSES, SyllabusStatus
from ..models import Syllabus

#: Jurnal banneri üçün VƏZİYYƏT kodları. Mətn UI qatındadır
#: (``apps.registrar.syllabus_notice``) — burada yalnız kod.
STATE_MISSING = "missing"  #: dosye yoxdur → «əvvəlcə sillabusunuzu yazın»
STATE_DRAFT = "draft"  #: qaralama var, hələ göndərilməyib
STATE_PENDING = "pending"  #: SUBMITTED/REVIEW — kafedra müdirinin baxışındadır
STATE_REVISION = "revision"  #: düzəliş tələb olunur (səbəb göstərilir)
STATE_REJECTED = "rejected"  #: rədd edilib (səbəb göstərilir)
STATE_APPROVED = "approved"  #: təsdiqlənib — banner yoxdur, yalnız keçid
STATE_ARCHIVED = "archived"  #: yalnız arxiv nüsxəsi qalıb

#: Cari versiyanın statusu → banner vəziyyəti.
_STATUS_TO_STATE = {
    SyllabusStatus.DRAFT.value: STATE_DRAFT,
    SyllabusStatus.SUBMITTED.value: STATE_PENDING,
    SyllabusStatus.REVIEW.value: STATE_PENDING,
    SyllabusStatus.REVISION.value: STATE_REVISION,
    SyllabusStatus.REJECTED.value: STATE_REJECTED,
    SyllabusStatus.APPROVED.value: STATE_APPROVED,
    SyllabusStatus.ARCHIVED.value: STATE_ARCHIVED,
}

#: Müəllimin ƏMƏL etməli olduğu vəziyyətlər — jurnalda xəbərdarlıq zolağı çıxır.
ACTION_STATES = frozenset({STATE_MISSING, STATE_DRAFT, STATE_REVISION, STATE_REJECTED, STATE_ARCHIVED})

_RELATED = (
    "subject",
    "period",
    "program",
    "chair_unit",
    "author",
    "offering",
    "current_version",
    "approved_version",
    "approved_version__approved_by",
)


def syllabus_for_offering(*, organization, offering_id=None, subject_id=None, period_id=None, instructor_id=None):
    """Açılışa uyğun sillabus dosyesi və ya ``None`` (üç pilləli axtarış).

    Hər pillə AKTİV dosyelərlə məhdudlaşır; təşkilat filtri həmişə tətbiq
    olunur (RLS ikinci qatdır, birincisi bu filtrdir).
    """
    if organization is None:
        return None

    # Perf auditi 2026-09-13 F-04: üç pillə əvvəl üç ayrı `.first()` idi —
    # sillabusu OLMAYAN açılışda hər çağırış 3 sorğu (jurnal detalı 4 çağıran ×
    # 3 = 12 eyni SELECT, hər biri 9 cədvəllik JOIN). İndi pillələr TƏK sorğuda
    # OR-lanır, `_tier` rütbəsi eyni prioriteti saxlayır (0 → 1 → 2), hər pillə
    # daxilində əvvəlki kimi `Meta.ordering` (`subject__code`) + `pk`.
    tiers = []
    if offering_id is not None:
        tiers.append(Q(offering_id=offering_id))
    if subject_id is not None and period_id is not None:
        tiers.append(Q(subject_id=subject_id, period_id=period_id, offering__isnull=True))
    if subject_id is not None and instructor_id is not None:
        tiers.append(
            Q(subject_id=subject_id, author_id=instructor_id, offering__isnull=True, period__isnull=True),
        )
    if not tiers:
        return None

    combined = tiers[0]
    for tier in tiers[1:]:
        combined = combined | tier
    rank = Case(
        *[When(tier, then=Value(index)) for index, tier in enumerate(tiers)],
        default=Value(len(tiers)),
        output_field=IntegerField(),
    )
    return (
        Syllabus.objects.filter(organization=organization, is_active=True)
        .filter(combined)
        .select_related(*_RELATED)
        .annotate(_tier=rank)
        .order_by("_tier", "subject__code", "pk")
        .first()
    )


_SYLLABUS_MEMO_ATTR = "_syllabus_memo"


def syllabus_for_offering_obj(offering):
    """`syllabus_for_offering`-in offering OBYEKTİ ilə qısa forması.

    Jurnal səhifəsi eyni açılış üçün bunu 4 dəfə çağırır (bildiriş zolağı, mövzu
    seçimləri, mövzu meta…); view `preload_syllabus_for_offering` ilə memo
    qoyubsa oradan qayıdır — memo yoxdursa həmişə canlı sorğu (yazı yolları və
    testlər dəyişmir). ``None`` də memo-lanır (sillabussuz açılış)."""
    if hasattr(offering, _SYLLABUS_MEMO_ATTR):
        return getattr(offering, _SYLLABUS_MEMO_ATTR)
    return syllabus_for_offering(
        organization=offering.organization,
        offering_id=offering.id,
        subject_id=offering.subject_id,
        period_id=offering.period_id,
        instructor_id=offering.instructor_id,
    )


def preload_syllabus_for_offering(offering):
    """YALNIZ oxu yolu: dosyeni bir dəfə tapıb offering obyektinə yapışdırır."""
    if hasattr(offering, _SYLLABUS_MEMO_ATTR):
        delattr(offering, _SYLLABUS_MEMO_ATTR)
    setattr(offering, _SYLLABUS_MEMO_ATTR, syllabus_for_offering_obj(offering))


def approved_version_for(syllabus):
    """Tələbənin GÖRDÜYÜ versiya — qüvvədə olan təsdiqlənmiş nüsxə.

    ⚠️ Yeni versiya təsdiqlənməyibsə ƏVVƏLKİ təsdiqlənmiş versiya görünməyə
    davam edir: ``approved_version`` yalnız yeni təsdiq zamanı dəyişir, ona
    görə burada ``current_version``-a heç vaxt geri düşülmür.
    """
    if syllabus is None:
        return None
    version = syllabus.approved_version
    if version is not None and version.status == SyllabusStatus.APPROVED.value:
        return version
    # Dosyedəki göstərici köhnəlibsə (məsələn əl ilə düzəliş) statusa görə tap.
    return syllabus.versions.filter(status=SyllabusStatus.APPROVED.value).select_related("approved_by").first()


def offering_syllabus_state(syllabus) -> dict:
    """Jurnal banneri üçün strukturlaşmış vəziyyət (MƏTNSİZ — yalnız kodlar).

    ``open_version`` — hazırda qərar gözləyən/redaktə olunan versiya;
    ``approved_version`` — tələbənin gördüyü nüsxə. İkisi eyni anda mövcud ola
    bilər: müəllim v2.0-ı göndərib, tələbə hələ v1.1-i görür.
    """
    if syllabus is None:
        return {
            "state": STATE_MISSING,
            "syllabus": None,
            "version": None,
            "approved_version": None,
            "reason": "",
            "needs_action": True,
            "has_approved": False,
        }

    approved = approved_version_for(syllabus)
    open_version = syllabus.versions.filter(status__in=sorted(OPEN_STATUSES)).first()
    # Banner AÇIQ versiyanı izləyir: təsdiqlənmiş nüsxə dursa da, göndərilmiş
    # v2.0 «baxışdadır» xəbərdarlığı müəllim üçün aktual məlumatdır.
    version = open_version or approved or syllabus.current_version
    status = version.status if version is not None else SyllabusStatus.DRAFT.value
    state = _STATUS_TO_STATE.get(status, STATE_DRAFT)
    return {
        "state": state,
        "syllabus": syllabus,
        "version": version,
        "approved_version": approved,
        "reason": (version.decision_reason or "") if version is not None else "",
        "needs_action": state in ACTION_STATES,
        "has_approved": approved is not None,
    }


__all__ = [
    "ACTION_STATES",
    "STATE_APPROVED",
    "STATE_ARCHIVED",
    "STATE_DRAFT",
    "STATE_MISSING",
    "STATE_PENDING",
    "STATE_REJECTED",
    "STATE_REVISION",
    "approved_version_for",
    "offering_syllabus_state",
    "syllabus_for_offering",
]
