"""Sərbəst iş STRUKTURU — təsdiqlənmiş sillabusun seçimi (1×10 / 2×5 / 10×1) → jurnal mövzuları.

Sillabusun «Sərbəst iş strukturu» bölməsi (``self.option``) N slot × P bal
müəyyən edir (cəmi həmişə 10). Jurnalda hər slot bir ``SelfWorkTopic``-dir
(``slot_index`` = 1…N, ``max_points`` = P). Bu modul mövcud mövzularla
sillabusu müqayisə edib PLAN qurur və (yazı yolunda) onu tətbiq edir.

VƏZİYYƏTLƏR (:class:`Plan.state`):

* ``none`` — sillabusda struktur yoxdur → köhnə çeklist rejimi (≤10 mövzu × 1 bal);
* ``pending`` — struktur var, jurnala hələ tətbiq olunmayıb (mövzu yoxdur və ya
  mövcud mövzular RƏQƏM DƏYİŞMƏDƏN uyğunlaşdırıla bilər);
* ``ok`` — mövzular strukturla uyğundur;
* ``structure_mismatch`` — uyğunlaşdırmaq RƏQƏM dəyişdirərdi və ya silmə tələb
  edərdi → heç nə yazılmır, lövhə izahlı zolaq göstərir.

QAYDALAR (heç bir tələbənin balı səssizcə dəyişmir):

* mövzu HEÇ VAXT silinmir;
* qiymətli (təhvil/bal) işarəsi olan mövzunun ``max_points``-u dəyişmir (DB
  trigger-i də qoruyur, ``registrar.0081``) — köhnə çeklist mövzusu (1 bal)
  2 × 5 / 1 × 10 sillabusunda uyğunsuzluq kimi göstərilir;
* 10 × 1 strukturunda köhnə çeklist mövzuları (≤10) sıra ilə slota bağlanır —
  ``max_points`` 1 qalır, yəni rəqəm dəyişmir; çatışmayan slotlar yaradılır;
* slot → mövzu xəritəsi sabitdir (``uniq_selfwork_topic_offering_slot``); paralel
  qurulma açılış sətrinin kilidi ilə ardıcıllaşır (kilid sırası: açılış →
  qeydiyyat → işarə).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.db import transaction
from django.db.models import Q, prefetch_related_objects
from django.utils.translation import pgettext

from apps.registrar.models import AssessmentComponent, ComponentKind, SelfWorkMark, SelfWorkTopic
from apps.registrar.models.selfwork import SELFWORK_TOTAL_POINTS

STATE_NONE = "none"
STATE_PENDING = "pending"
STATE_OK = "ok"
STATE_MISMATCH = "structure_mismatch"

SOURCE_SYLLABUS = "syllabus"
SOURCE_TOPICS = "topics"

#: Uyğunsuzluq səbəbləri (UI mətni :func:`mismatch_message`-dədir).
REASON_LEGACY_GRADED = "legacy_graded"
REASON_TOO_MANY = "too_many_topics"
REASON_CHANGED = "structure_changed"
REASON_MIXED = "mixed_topics"
REASON_INCONSISTENT = "inconsistent_topics"

#: Struktur sillabusdan qurulanda mövzu adı (data — UI tərcüməsi deyil).
SLOT_TITLE = "Sərbəst iş {n}"

_CTX = "registrar.selfwork"


@dataclass(frozen=True)
class Structure:
    """N slot × P bal (cəmi ≤ 10)."""

    option: str
    count: int
    per_score: int
    source: str = SOURCE_SYLLABUS

    @property
    def label(self) -> str:
        return f"{self.count} × {self.per_score}"


@dataclass
class Plan:
    state: str
    structure: Structure | None = None
    reason: str = ""
    adopt: tuple = ()  # ((topic, slot_index, max_points), …) — mövcud mövzunun uyğunlaşdırılması
    create: tuple = ()  # yaradılacaq slot nömrələri
    detail: dict = field(default_factory=dict)
    applied: bool = False

    @property
    def is_structured(self) -> bool:
        return self.structure is not None and self.state in (STATE_OK, STATE_PENDING)

    def as_dict(self) -> dict:
        """Şablon üçün düz forma (lövhənin ``structure`` açarı)."""
        structure = self.structure
        return {
            "state": self.state,
            "reason": self.reason,
            "option": structure.option if structure else "",
            "count": structure.count if structure else 0,
            "per_score": structure.per_score if structure else 0,
            "label": structure.label if structure else "",
            "source": structure.source if structure else "",
            "is_structured": self.is_structured,
            "message": mismatch_message(self) if self.state == STATE_MISMATCH else "",
        }


# ── Sillabus → struktur ──────────────────────────────────────────────────────


def _self_section_data(version) -> dict:
    """Versiyanın ``self`` bölməsi. Bölmələr versiya obyektinə PREFETCH olunur —
    eyni sorğuda jurnalın mövzu mənbəyi (``journal_topics``) də həmin keşdən oxuyur."""
    prefetch_related_objects([version], "sections")
    for row in version.sections.all():
        if row.section_id == "self":
            return row.data or {}
    return {}


#: ``apps.syllabus`` oxu memo-su (``preload_syllabus_for_offering``) — varsa dosye sorğusuz gəlir.
_SYLLABUS_MEMO_ATTR = "_syllabus_memo"


def _offering_syllabus(offering):
    """Açılışın sillabus dosyesi — memo varsa ondan; təşkilat obyekti keşdə deyilsə id ilə
    (``offering.organization`` FK-sını ayrıca sorğu ilə oxumamaq üçün)."""
    from apps.syllabus import public as syllabus_public

    if hasattr(offering, _SYLLABUS_MEMO_ATTR) or "organization" in offering._state.fields_cache:
        return syllabus_public.syllabus_for_offering_obj(offering)
    return syllabus_public.syllabus_for_offering(
        organization=offering.organization_id,
        offering_id=offering.pk,
        subject_id=offering.subject_id,
        period_id=offering.period_id,
        instructor_id=offering.instructor_id,
    )


def syllabus_structure(offering) -> Structure | None:
    """Açılışın TƏSDİQLƏNMİŞ sillabusundakı sərbəst iş strukturu (yalnız siyasətin icazə verdiyi seçim)."""
    from apps.syllabus import public as syllabus_public

    syllabus = _offering_syllabus(offering)
    version = syllabus_public.approved_version_for(syllabus)
    if version is None:
        return None
    option = str(_self_section_data(version).get("option") or "").strip()
    config = syllabus_public.SELFWORK_OPTIONS.get(option)
    if not config:
        return None
    return Structure(option=option, count=int(config["count"]), per_score=int(config["per_score"]))


def topics_structure(topics) -> Structure | None:
    """Artıq qurulmuş (slotlu) mövzulardan struktur — sillabus oxunmadan (oxu yolları üçün)."""
    if not topics or any(topic.slot_index is None for topic in topics):
        return None
    maxima = {topic.max_points for topic in topics}
    count = max(topic.slot_index for topic in topics)
    if len(maxima) != 1 or count * next(iter(maxima)) > SELFWORK_TOTAL_POINTS:
        return None
    per_score = next(iter(maxima))
    return Structure(option=f"{count}x{per_score}", count=count, per_score=per_score, source=SOURCE_TOPICS)


# ── Plan ─────────────────────────────────────────────────────────────────────


def plan_for(topics, *, graded_topic_ids, structure) -> Plan:
    """Mövcud mövzular + struktur → :class:`Plan` (YAZI YOXDUR)."""
    topics = list(topics)
    structured = [t for t in topics if t.slot_index is not None]
    legacy = [t for t in topics if t.slot_index is None]
    if structure is None:
        if structured and legacy:
            return Plan(STATE_MISMATCH, None, REASON_MIXED)
        if structured:
            derived = topics_structure(structured)
            return Plan(STATE_OK, derived) if derived else Plan(STATE_MISMATCH, None, REASON_INCONSISTENT)
        return Plan(STATE_NONE)
    count, per_score = structure.count, structure.per_score
    if not topics:
        return Plan(STATE_PENDING, structure, create=tuple(range(1, count + 1)))
    if structured and legacy:
        return Plan(STATE_MISMATCH, structure, REASON_MIXED)

    def locked(topic):  # qiymətli mövzunun tavanı dəyişə bilməz
        return topic.id in graded_topic_ids and topic.max_points != per_score

    if structured:
        slots = {t.slot_index for t in structured}
        if max(slots) > count or any(locked(t) for t in structured):
            return Plan(STATE_MISMATCH, structure, REASON_CHANGED)
        adopt = tuple((t, t.slot_index, per_score) for t in structured if t.max_points != per_score)
        missing = tuple(sorted(set(range(1, count + 1)) - slots))
        if not adopt and not missing:
            return Plan(STATE_OK, structure)
        return Plan(STATE_PENDING, structure, adopt=adopt, create=missing)
    if len(legacy) > count:
        return Plan(STATE_MISMATCH, structure, REASON_TOO_MANY, detail={"topics": len(legacy)})
    if any(locked(t) for t in legacy):
        graded = sum(1 for t in legacy if t.id in graded_topic_ids)
        return Plan(STATE_MISMATCH, structure, REASON_LEGACY_GRADED, detail={"topics": len(legacy), "graded": graded})
    adopt = tuple((t, index, per_score) for index, t in enumerate(legacy, start=1))
    return Plan(STATE_PENDING, structure, adopt=adopt, create=tuple(range(len(legacy) + 1, count + 1)))


def offering_topics(offering) -> list:
    return list(SelfWorkTopic.objects.filter(offering=offering).order_by("order", "created_at"))


def graded_topic_ids(offering) -> set:
    """Qiymətli işarəsi (təhvil və ya bal) olan mövzular — TƏK sorğu."""
    return set(
        SelfWorkMark.objects.filter(topic__offering=offering)
        .filter(Q(done=True) | Q(points__isnull=False))
        .values_list("topic_id", flat=True)
        .distinct()
    )


def is_complete(topics) -> bool:
    """Mövzular TAM qurulmuş strukturdur: N slot (1…N) × eyni P bal, cəmi düz 10."""
    if not topics or any(topic.slot_index is None for topic in topics):
        return False
    maxima = {topic.max_points for topic in topics}
    if len(maxima) != 1:
        return False
    slots = sorted(topic.slot_index for topic in topics)
    return slots == list(range(1, len(topics) + 1)) and len(topics) * next(iter(maxima)) == SELFWORK_TOTAL_POINTS


def needs_syllabus(topics) -> bool:
    """Oxu yolunda sillabus YALNIZ struktur tam deyilsə oxunur (mövzu yoxdur, köhnə mövzu var,
    slot silinib) — tam qurulmuş jurnal əlavə sorğu etmir."""
    return not is_complete(topics)


SYLLABUS_AUTO = "auto"  # yalnız lazım olanda (mövzu yoxdur / köhnə mövzu var) — oxu yolları
SYLLABUS_ALWAYS = "always"  # yazı yolları: qurulmuş struktur da sillabusla yoxlanır
SYLLABUS_NEVER = "never"  # rəqəm səthləri: struktur yalnız mövzulardan


def load_plan(offering, *, topics=None, graded=None, structure=None, syllabus=SYLLABUS_AUTO) -> Plan:
    """Canlı plan: mövzular (+ lazım olsa sillabus və qiymətli mövzular) oxunur."""
    topics = offering_topics(offering) if topics is None else list(topics)
    if structure is None and (syllabus == SYLLABUS_ALWAYS or (syllabus == SYLLABUS_AUTO and needs_syllabus(topics))):
        structure = syllabus_structure(offering)
    if structure is not None and topics and graded is None:
        graded = graded_topic_ids(offering)
    return plan_for(topics, graded_topic_ids=graded or set(), structure=structure)


# ── Tətbiq (yazı yolu) ───────────────────────────────────────────────────────


@transaction.atomic
def ensure_selfwork_component(offering):
    """Sərbəst iş komponentini idempotent yarat (kind=SELF_WORK, max 10).

    ``entry_score_for`` sərbəst işi YALNIZ bu komponent varsa sayır — ona görə
    struktur qurulanda və hər hook yazısında çağırılır. Komponentə bal YAZILMIR
    (cəm ``selfwork_points``-dən oxunur). Tək istisna: köçürmə köhnə ``si``
    balını bu komponentə ``ComponentScore`` kimi yazır; o bal YALNIZ lövhədə
    "arxiv" sütunu kimi göstərilir və giriş balına əlavə OLUNMUR (bax ``selfwork_board``)."""
    component = AssessmentComponent.objects.filter(offering=offering, kind=ComponentKind.SELF_WORK).first()
    if component is None:
        # İki paralel yazı (hook + lövhə) ikinci SELF_WORK komponenti yaratmasın —
        # ikinci komponent ``entry_score_for``-da balı İKİ DƏFƏ sayardı.
        lock_offering(offering)
        component = AssessmentComponent.objects.filter(offering=offering, kind=ComponentKind.SELF_WORK).first()
    if component is None:
        component = AssessmentComponent.objects.create(
            organization=offering.organization,
            offering=offering,
            name="Sərbəst iş",
            kind=ComponentKind.SELF_WORK,
            max_score=SELFWORK_TOTAL_POINTS,
            order=AssessmentComponent.objects.filter(offering=offering).count() + 1,
        )
    return component


def lock_offering(offering) -> None:
    """Açılış sətrini ``FOR UPDATE`` kilidlə — struktur/mövzu yazıları ardıcıllaşır."""
    type(offering).objects.select_for_update().filter(pk=offering.pk).exists()


def _apply(offering, plan: Plan, topics) -> None:
    ensure_selfwork_component(offering)
    for topic, slot_index, max_points in plan.adopt:
        topic.slot_index = slot_index
        topic.max_points = max_points
        topic.save(update_fields=["slot_index", "max_points", "updated_at"])
    base_order = max((topic.order for topic in topics), default=0)
    for offset, slot_index in enumerate(plan.create, start=1):
        SelfWorkTopic.objects.create(
            organization=offering.organization,
            offering=offering,
            title=SLOT_TITLE.format(n=slot_index),
            order=base_order + offset,
            slot_index=slot_index,
            max_points=plan.structure.per_score,
        )


def ensure_structure(offering) -> Plan:
    """Təsdiqlənmiş sillabusun strukturunu jurnala tətbiq et (idempotent) → :class:`Plan`.

    Yalnız ``pending`` plan tətbiq olunur və yalnız jurnal AÇIQDIRSA; açılış sətri
    kilidlənib plan kilid altında YENİDƏN qurulur (paralel çağırış dublikat
    yaratmır). Qaytarılan plan ``applied=True`` daşıyırsa mövzular yaradılıb/bağlanıb."""
    from apps.registrar.gradebook import journal_is_locked

    plan = load_plan(offering, syllabus=SYLLABUS_ALWAYS)
    if plan.state != STATE_PENDING or journal_is_locked(offering):
        return plan
    structure = plan.structure
    with transaction.atomic():
        lock_offering(offering)
        topics = offering_topics(offering)
        plan = load_plan(offering, topics=topics, structure=structure)
        if plan.state != STATE_PENDING:
            return plan
        _apply(offering, plan, topics)
    return Plan(STATE_OK, structure, applied=True)


# ── «+ mövzu» qaydası ────────────────────────────────────────────────────────


def next_topic_slot(plan: Plan, topics):
    """Yeni mövzu üçün ``(slot_index, max_points)`` və ya ``None`` (yer yoxdur).

    * strukturlu jurnal: yalnız BOŞ slot doldurulur (2 × 5 / 1 × 10-da N-dən artıq mövzu yoxdur);
    * köhnə çeklist / uyğunsuzluq: ≤10 mövzu, hər biri 1 bal, Σ max ≤ 10."""
    topics = list(topics)
    if plan.is_structured and plan.state == STATE_OK:
        taken = {topic.slot_index for topic in topics}
        free = [n for n in range(1, plan.structure.count + 1) if n not in taken]
        return (free[0], plan.structure.per_score) if free else None
    total = sum(topic.max_points for topic in topics)
    if len(topics) >= SELFWORK_TOTAL_POINTS or total + 1 > SELFWORK_TOTAL_POINTS:
        return None
    return (None, 1)


# ── Mətnlər ──────────────────────────────────────────────────────────────────


def mismatch_message(plan: Plan) -> str:
    """``structure_mismatch`` izahı — lövhə zolağı və hook imtina mesajı üçün."""
    label = plan.structure.label if plan.structure else ""
    if plan.reason == REASON_LEGACY_GRADED:
        return pgettext(
            _CTX,
            "Sillabus sərbəst işi %(label)s bal kimi tələb edir, jurnalda isə %(topics)s köhnə çeklist mövzusu "
            "var və onların bəzisinə artıq bal yazılıb. Qiymət yazılmış mövzular avtomatik çevrilmir — "
            "tələbələrin balı dəyişərdi. Strukturu dəyişmək üçün RİM ilə sənədli düzəliş edin.",
        ) % {"label": label, "topics": plan.detail.get("topics", 0)}
    if plan.reason == REASON_TOO_MANY:
        return pgettext(
            _CTX,
            "Sillabus sərbəst işi %(label)s bal kimi tələb edir, jurnalda isə %(topics)s mövzu var. "
            "Mövzular silinmir — artıq (qiymətsiz) mövzuları özünüz silin, struktur sonra tətbiq olunacaq.",
        ) % {"label": label, "topics": plan.detail.get("topics", 0)}
    if plan.reason == REASON_CHANGED:
        return pgettext(
            _CTX,
            "Jurnaldakı sərbəst iş strukturu sillabusdakından (%(label)s) fərqlidir. Qiymət yazılmış slotlar "
            "avtomatik dəyişdirilmir və mövzular silinmir — artıq (qiymətsiz) mövzuları silin, struktur sonra "
            "tətbiq olunacaq.",
        ) % {"label": label}
    return pgettext(
        _CTX,
        "Jurnaldakı sərbəst iş mövzuları sillabusun strukturu ilə uyğun deyil (köhnə və strukturlu mövzular "
        "qarışıqdır). Qiymət yazılmış mövzular avtomatik dəyişdirilmir.",
    )


__all__ = [
    "Plan",
    "REASON_CHANGED",
    "REASON_INCONSISTENT",
    "REASON_LEGACY_GRADED",
    "REASON_MIXED",
    "REASON_TOO_MANY",
    "SLOT_TITLE",
    "STATE_MISMATCH",
    "STATE_NONE",
    "STATE_OK",
    "STATE_PENDING",
    "SYLLABUS_ALWAYS",
    "SYLLABUS_AUTO",
    "SYLLABUS_NEVER",
    "Structure",
    "ensure_selfwork_component",
    "ensure_structure",
    "graded_topic_ids",
    "is_complete",
    "load_plan",
    "lock_offering",
    "mismatch_message",
    "needs_syllabus",
    "next_topic_slot",
    "offering_topics",
    "plan_for",
    "syllabus_structure",
    "topics_structure",
]
