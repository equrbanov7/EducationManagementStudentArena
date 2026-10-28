"""Açılış (``CourseOffering``) → sillabus dosyesi həlli + jurnal VƏZİYYƏT kodu.

Jurnal və tələbə kabineti «bu dərsin sillabusu hanı?» sualını verir. Cavab
modelin ÜÇ qismən UNIQUE məhdudiyyətinin güzgüsüdür və eyni ardıcıllıqla
axtarılır (bax :class:`apps.syllabus.models.Syllabus` docstring-i):

1. ``offering`` üzrə — normal axın (qrup + müəllim konkretdir);
1a. PAYLAŞIM (sahib 2026-10-27, ``SyllabusShare``) — açılış başqa qrupun sillabusunu ÖZ YERİNDƏ istifadə edir
   (bir sillabus — bir neçə jurnal; yalnız eyni müəllim, bax ``services/sharing.py``);
2. ``(subject, period)`` üzrə — semestr səviyyəli dosye, açılış hələ
   bağlanmayıb;
3. ``(subject, author)`` üzrə — köhnə sistemdən köçürülmüş SEMESTRSİZ «baza
   sillabus». Köhnə bazada semestr yoxdur, uydurulmur.

⚠️ Modul-sərhəd: burada ``apps.registrar`` İDXAL EDİLMİR — funksiyalar xam
ID-lər qəbul edir. ``registrar → syllabus`` tək istiqamətli qalır, əks kənar
açılmır (``scripts/module_deps.py``).
"""

from __future__ import annotations

from django.db.models import Case, IntegerField, Q, Subquery, Value, When

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


def _share_applies(syllabus, offering_id, instructor_id) -> bool:
    """Paylaşım pilləsindən gəlibsə, tətbiq qapısı (``sharing`` qayda 4) — açılışın müəllimi dosyenin sahibidir."""
    if syllabus.offering_id is None or syllabus.offering_id == offering_id:
        return True  # öz / fənn+semestr / baza pilləsi — paylaşım deyil
    owner_ids = {syllabus.author_id, getattr(syllabus.offering, "instructor_id", None)}
    return instructor_id is not None and instructor_id in owner_ids


def syllabus_for_offering(
    *,
    organization,
    offering_id=None,
    subject_id=None,
    period_id=None,
    instructor_id=None,
    _with_share=True,
    _metadata_only=False,
):
    """Açılışa uyğun sillabus dosyesi və ya ``None`` (pilləli axtarış).

    Hər pillə AKTİV dosyelərlə məhdudlaşır; təşkilat filtri həmişə tətbiq
    olunur (RLS ikinci qatdır, birincisi bu filtrdir).  Paylaşım pilləsi (sahib 2026-10-27) alt-sorğuda
    JOIN-suzdur (PERF-1 forması qorunur); müəllim qapısı nəticədə yoxlanır — keçmirsə (fənn başqa müəllimə
    keçib) axtarış paylaşımsız təkrarlanır (nadir hal, +1 sorğu).
    """
    if organization is None:
        return None

    # Perf auditi 2026-09-13 F-04: üç pillə əvvəl üç ayrı `.first()` idi —
    # sillabusu OLMAYAN açılışda hər çağırış 3 sorğu (jurnal detalı 4 çağıran ×
    # 3 = 12 eyni SELECT, hər biri 9 cədvəllik JOIN). İndi pillələr TƏK sorğuda
    # OR-lanır, `_tier` rütbəsi eyni prioriteti saxlayır (0 → 1 → 2), hər pillə
    # daxilində əvvəlki kimi `Meta.ordering` (`subject__code`) + `pk`.
    from ..models import SyllabusShare

    tiers = []
    if offering_id is not None:
        tiers.append(Q(offering_id=offering_id))
        if _with_share:
            shared = SyllabusShare.objects.filter(offering_id=offering_id).order_by().values("syllabus_id")
            tiers.append(Q(pk__in=Subquery(shared)))
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
    # PERF-1 F-14 (2026-10-17): pillə seçimi JOIN-suz alt-sorğuda (yalnız sıralama üçün `subject`), 9 cədvəllik
    # `select_related` isə xarici sorğuda PK bərabərliyi ilə — Case/OR pillələri JOIN-larla birgə planlaşdırılmır.
    # Planlaşdırma ~6 → ~3 ms (icra 0,3 ms); round-trip yenə BİRDİR (jurnal / sərbəst iş sorğu büdcələri dəyişmir).
    tier_pick = (
        Syllabus.objects.filter(organization=organization, is_active=True)
        .filter(combined)
        .annotate(_tier=rank)
        .order_by("_tier", "subject__code", "pk")
        .values("pk")[:1]
    )
    related = ("offering", "approved_version") if _metadata_only else _RELATED
    found = Syllabus.objects.select_related(*related).filter(pk=Subquery(tier_pick)).first()
    if found is not None and _with_share and not _share_applies(found, offering_id, instructor_id):
        return syllabus_for_offering(
            organization=organization,
            offering_id=offering_id,
            subject_id=subject_id,
            period_id=period_id,
            instructor_id=instructor_id,
            _with_share=False,
            _metadata_only=_metadata_only,
        )
    return found


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


def approved_version_for(syllabus, *, metadata_only=False):
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
    versions = syllabus.versions.filter(status=SyllabusStatus.APPROVED.value)
    return versions.first() if metadata_only else versions.select_related("approved_by").first()


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
