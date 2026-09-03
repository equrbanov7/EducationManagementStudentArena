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
    base = Syllabus.objects.filter(organization=organization, is_active=True).select_related(*_RELATED)

    if offering_id is not None:
        found = base.filter(offering_id=offering_id).first()
        if found is not None:
            return found
    if subject_id is None:
        return None
    if period_id is not None:
        found = base.filter(subject_id=subject_id, period_id=period_id, offering__isnull=True).first()
        if found is not None:
            return found
    if instructor_id is None:
        return None
    return base.filter(
        subject_id=subject_id,
        author_id=instructor_id,
        offering__isnull=True,
        period__isnull=True,
    ).first()


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
