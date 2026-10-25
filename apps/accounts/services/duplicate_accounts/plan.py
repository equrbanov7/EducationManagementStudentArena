"""Dublikat hesabların PLANI — kim eyni şəxsdir, hansı hesab saxlanılır, nə edilir (YAZMIR).

Sahib (2026-10-25): «Dublikat hesabdırsa — hal-hazırda jurnalı yazdığı hesabı saxla, digərlərini dondur.»

**Eyni şəxs** (uydurma yoxdur):

* soyad + ad eyni — diakritik/registr dözümlü, sahələr tərs yazıla bilər («Ad | Soyad»); yazılış variantı
  (ə/a/e, q/g/k, f/v, qoşa hərf — «Qəmbərova»/«Qambarova», «Gülçin»/«Gülcin») YALNIZ ata adı HƏR İKİ hesabda
  yazılıb və eyni/oxşardırsa qəbul olunur;
* ata adı ziddiyyətsizdir: eyni, yazılış variantı (Əsgər/Əskər; bir hərf fərqi DEYİL — Vahid ≠ Zahid)
  və ya bir tərəfdə boş (boş ata adlı hesab yalnız
  soyad+ad DƏQİQ uyğun olanda qoşulur; iki fərqli ata adlı qrupa uyğun gəlirsə — qərar siyahısı). Ata adı
  fərqlidirsə — BAŞQA ADAMDIR, toxunulmur;
* FİN: unikal sahədir — qrupda iki FİN-li hesab varsa bunlar fərqli adamlardır (yalnız hesabat);
* adı natamam hesab («Aynur» — soyad yoxdur): eyni kafedrada adı uyğun gələn TƏK tam adlı hesabla.

**Saxlanılan hesab:** cari semestrin jurnalı olan → dərs yükü olan → son girişi olan → rolu (dekan / dekan
müavini / kafedra müdiri / inzibati) olan → üzvlüyü çox olan → köhnə hesab.

**Xüsusi hal** — saxlanılan (jurnallı) hesab HEÇ VAXT girməyib, digəri girir: rəsmi «Fənn təhvili» axını
(``registrar.handover_actions``) var — saxlanılanın dərs yükü (``TeacherAssignment``) yoxdursa və açılışların
təhvilinə bloker yoxdursa jurnallar GİRƏN hesaba təhvil verilir, girməyən hesab dondurulur (``flip``). Yük
varsa yükün köçürülməsi yük sənədinin düzəliş (amendment) axınını açıb tapşırığı yenidən təsdiqə qaytarır —
avtomatik paketdə edilmir: jurnallı hesab saxlanılır, girən hesab dondurulur və RİM-in «parol təyin et»
siyahısına düşür (``rim_password``).

**Dondurulan hesab üçün:** onun rolları (üzvlük: rol + bölmə) saxlanılanda yoxdursa saxlanılana verilir,
rəhbəri olduğu bölmələrin rəhbəri saxlanılan olur, cari açılışları təhvil verilir, aktiv üzvlükləri deaktiv
edilir, hesab «Hesabı dayandır» ilə bloklanır. Dərs yükü olan dublikat dondurulmur (qərar siyahısı).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from ..teacher_roster.matching import loose
from . import facts as facts_mod

MODE_NORMAL = "normal"
MODE_FLIP = "flip"
MODE_RIM_PASSWORD = "rim_password"

STATUS_OK = "ok"
STATUS_ALL_BLOCKED = "all_blocked"
STATUS_KEPT_BLOCKED = "kept_blocked"
STATUS_FIN_CONFLICT = "fin_conflict"
STATUS_PATRONYMIC_CONFLICT = "patronymic_conflict"

SKIP_PROTECTED = "protected"
SKIP_HAS_LOAD = "has_load"
SKIP_HANDOVER_BLOCKED = "handover_blocked"

#: Təhvili dayandıran bloker kodları (``registrar.handover.blockers``; hədəfin uyğunluğu rol köçəndən sonra yaranır).
HANDOVER_BLOCKERS = ("offering_inactive", "journal_closed", "past_period")


def patronymic_state(left: str, right: str) -> str:
    """``same`` / ``similar`` / ``missing`` (bir tərəfdə yoxdur) / ``different``."""
    if not left or not right:
        return "missing"
    if left == right or left.startswith(right) or right.startswith(left):
        return "same"
    if loose(left) == loose(right):
        return "similar"  # yalnız yazılış variantı (Əsgər/Əskər); bir hərf fərqi YOX — Vahid ≠ Zahid
    return "different"


@dataclass
class DupAction:
    person: object
    skip: str = ""
    block: bool = False
    deactivate: list = field(default_factory=list)  # dublikatın aktiv üzvlük id-ləri
    transfer: list = field(default_factory=list)  # saxlanılana veriləcək üzvlüklər (dict)
    heads: list = field(default_factory=list)  # rəhbəri saxlanılana keçən bölmə id-ləri
    handover: list = field(default_factory=list)  # saxlanılana təhvil veriləcək açılış id-ləri

    @property
    def writes(self) -> int:
        if self.skip:
            return 0
        return int(self.block) + len(self.deactivate) + len(self.transfer) + len(self.heads) + len(self.handover)


@dataclass
class Cluster:
    members: list  # [Person] — saxlanılma sırası ilə (ən güclü əvvəl)
    status: str = STATUS_OK
    mode: str = MODE_NORMAL
    kept: object = None
    journal_holder: object = None  # xüsusi halda jurnalların köhnə sahibi
    dups: list = field(default_factory=list)  # [DupAction]
    excluded: list = field(default_factory=list)  # [(Person, səbəb)] — eyni adlı, amma başqa adam
    notes: list = field(default_factory=list)

    @property
    def writes(self) -> int:
        return sum(action.writes for action in self.dups)


@dataclass
class Plan:
    organization: object
    academic_year: str
    clusters: list
    ambiguous: list  # [(Person, [Person])] — bir neçə qrupa uyğun gələn hesab (qərar siyahısı)
    people: dict
    homonyms: list = field(default_factory=list)  # [[Person]] — eyni ad, ata adı fərqli (başqa adamlar)

    @property
    def writes(self) -> int:
        return sum(cluster.writes for cluster in self.clusters if cluster.status == STATUS_OK)


# ── Qruplaşdırma ─────────────────────────────────────────────────────────────


class _Union:
    def __init__(self):
        self.parent = {}

    def find(self, item):
        self.parent.setdefault(item, item)
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def join(self, left, right):
        self.parent[self.find(left)] = self.find(right)


def _clusters(people: dict) -> tuple[list, list, dict]:
    """→ (qruplar [[Person]], qeyri-müəyyən [(Person, namizədlər)], ``{ad açarı: [Person]}``)."""
    union = _Union()
    full = [person for person in people.values() if not person.partial]
    partial = [person for person in people.values() if person.partial]
    ambiguous = []
    by_loose = defaultdict(list)
    for person in full:
        union.find(person.user_id)
        by_loose[person.loose_key].append(person)
    for bucket in by_loose.values():
        named = [person for person in bucket if person.patronymic_key]
        for index, left in enumerate(named):
            for right in named[index + 1 :]:
                if patronymic_state(left.patronymic_key, right.patronymic_key) in ("same", "similar"):
                    union.join(left.user_id, right.user_id)
        for person in [person for person in bucket if not person.patronymic_key]:
            exact = [other for other in bucket if other is not person and other.exact_key == person.exact_key]
            roots = {union.find(other.user_id) for other in exact if other.patronymic_key}
            if len(roots) > 1:
                ambiguous.append((person, exact))
                continue
            for other in exact:
                if not other.patronymic_key or union.find(other.user_id) in roots:
                    union.join(person.user_id, other.user_id)
    for person in partial:
        candidates = [
            other
            for other in full
            if other.chairs & person.chairs
            and person.single_key in (loose(other.last_key), loose(other.first_key))
            and patronymic_state(person.patronymic_key, other.patronymic_key) != "different"
        ]
        roots = {union.find(other.user_id) for other in candidates}
        if len(roots) == 1:
            union.join(person.user_id, candidates[0].user_id)
        elif len(roots) > 1:
            ambiguous.append((person, candidates))
    groups = defaultdict(list)
    for person in people.values():
        if person.user_id in union.parent:
            groups[union.find(person.user_id)].append(person)
    return [group for group in groups.values() if len(group) > 1], ambiguous, by_loose


# ── Qərar ────────────────────────────────────────────────────────────────────


def _blocked_offerings(organization, offering_ids, today) -> set:
    """Təhvili mümkün olmayan açılışlar (bağlı jurnal / bitmiş dövr / deaktiv)."""
    if not offering_ids:
        return set()
    from django.apps import apps as django_apps

    from apps.registrar.public import handover

    CourseOffering = django_apps.get_model("registrar", "CourseOffering")

    closed = handover.closed_offering_ids(list(offering_ids))
    blocked = set()
    for offering in CourseOffering.objects.filter(pk__in=list(offering_ids)).select_related("period"):
        codes = handover.blockers(offering, organization=organization, closed_ids=closed, today=today)
        if any(code in HANDOVER_BLOCKERS for code in codes):
            blocked.add(str(offering.pk))
    return blocked


def _dup_action(person, kept, planned: set, blocked_offerings: set) -> DupAction:
    action = DupAction(person=person)
    if person.protected:
        action.skip = SKIP_PROTECTED
        return action
    if person.load:
        action.skip = SKIP_HAS_LOAD
        return action
    if set(person.owned) & blocked_offerings:
        action.skip = SKIP_HANDOVER_BLOCKED
        return action
    for membership in person.memberships:
        slot = (membership["role_id"], membership["unit"])
        if slot not in planned:
            planned.add(slot)
            action.transfer.append(membership)
    action.heads = list(person.heads)
    action.handover = list(person.owned)
    action.deactivate = [membership["id"] for membership in person.memberships]
    action.block = person.is_active
    return action


def _decide(cluster: Cluster, organization, today) -> None:
    members = cluster.members
    if sum(1 for person in members if person.has_fin) > 1:
        cluster.status = STATUS_FIN_CONFLICT
        return
    for index, left in enumerate(members):
        for right in members[index + 1 :]:
            if patronymic_state(left.patronymic_key, right.patronymic_key) == "different":
                cluster.status = STATUS_PATRONYMIC_CONFLICT
                return
    if not any(person.is_active for person in members):
        cluster.status = STATUS_ALL_BLOCKED
        return
    kept = members[0]
    if not kept.is_active:
        cluster.kept = kept
        cluster.status = STATUS_KEPT_BLOCKED
        return
    if kept.last_login is None:
        logins = [p for p in members[1:] if p.is_active and p.last_login is not None and not p.protected]
        if logins:
            login = max(logins, key=lambda person: person.last_login)
            blocked = _blocked_offerings(organization, kept.owned, today)
            if kept.load == 0 and not kept.protected and not blocked:
                cluster.mode = MODE_FLIP
                cluster.journal_holder = kept
                kept = login
            else:
                cluster.mode = MODE_RIM_PASSWORD
                cluster.notes.append("kept_has_load" if kept.load else "handover_blocked")
    cluster.kept = kept
    planned = {(membership["role_id"], membership["unit"]) for membership in kept.memberships}
    others = [person for person in members if person is not kept]
    blocked = _blocked_offerings(organization, [pk for person in others for pk in person.owned], today)
    cluster.dups = [_dup_action(person, kept, planned, blocked) for person in others]


def build(organization, *, academic_year: str, period_ids=None, today=None) -> Plan:
    """Dublikat qruplarını tapır və hər qrup üçün qərar verir — YAZMIR."""
    from django.utils import timezone

    from ..staff_placement.facts import current_period_ids

    period_ids = current_period_ids(organization) if period_ids is None else period_ids
    today = today or timezone.localdate()
    people = facts_mod.load_people(organization, academic_year=academic_year, period_ids=period_ids)
    groups, ambiguous, by_loose = _clusters(people)
    clusters = []
    for group in groups:
        members = sorted(group, key=lambda person: person.sort_key(), reverse=True)
        cluster = Cluster(members=members)
        names = {person.loose_key for person in group if not person.partial}
        cluster.excluded = [
            (person, "patronymic_differs")
            for name in sorted(names)
            for person in by_loose.get(name, [])
            if person not in group
        ]
        _decide(cluster, organization, today)
        clusters.append(cluster)
    clusters.sort(key=lambda cluster: (cluster.status != STATUS_OK, cluster.members[0].display.lower()))
    group_of = {person.user_id: index for index, group in enumerate(groups) for person in group}
    homonyms = [
        sorted(bucket, key=lambda person: person.username)
        for bucket in by_loose.values()
        if len({group_of.get(person.user_id, -person.user_id) for person in bucket}) > 1
    ]
    return Plan(
        organization=organization,
        academic_year=academic_year,
        clusters=clusters,
        ambiguous=ambiguous,
        people=people,
        homonyms=sorted(homonyms, key=lambda bucket: bucket[0].display.lower()),
    )


def summary(plan: Plan) -> dict:
    """Yalnız SAYLAR (stdout / workflow loqu üçün)."""
    counts = defaultdict(int)
    for cluster in plan.clusters:
        counts[f"clusters_{cluster.status}"] += 1
        if cluster.status != STATUS_OK:
            continue
        counts[f"mode_{cluster.mode}"] += 1
        for action in cluster.dups:
            if action.skip:
                counts[f"skip_{action.skip}"] += 1
                continue
            counts["freeze"] += int(action.block)
            counts["memberships_off"] += len(action.deactivate)
            counts["roles_moved"] += len(action.transfer)
            counts["heads_moved"] += len(action.heads)
            counts["journals_moved"] += len(action.handover)
    counts["ambiguous"] = len(plan.ambiguous)
    counts["writes"] = plan.writes
    return dict(sorted(counts.items()))


__all__ = [
    "MODE_FLIP",
    "MODE_NORMAL",
    "MODE_RIM_PASSWORD",
    "STATUS_OK",
    "Cluster",
    "DupAction",
    "Plan",
    "build",
    "patronymic_state",
    "summary",
]
