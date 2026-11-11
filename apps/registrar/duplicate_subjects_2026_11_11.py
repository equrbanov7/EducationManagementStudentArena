"""Dublikat fənlərin KÖKLÜ həlli — jurnal + kataloq + kod, bir paket (sahib 2026-11-11) — ``merge_duplicate_subjects_20261111``.

Sahib: «Kompüterlərin diaqnostikası iki fənn kartında … tələbədə iki kart. Təkcə bu fənn yox, bütün dublikatları həll
et. Fənn kodu səhv düşənləri də. Standart olsun bir.» Üç əməliyyat (sıra ilə; hər biri ayrıca da işləyir):

1. ``journals`` — eyni dövr + qrupda iki fənn kartının iki AKTİV jurnalı: mənbə kartın jurnalı saxlanılan kartın
   jurnalına birləşir (:mod:`.duplicate_journal_merge_2026_11_11` — heç bir xana / bal itmir, fərqli dəyərlər
   manifestdə). Cütlər: :data:`PLAN`-dakı açıq cütlər + qrupun (saxlanılan, mənbə) kartları üzrə BÜTÜN dövrlərdə
   aşkarlanan qutular (``auto_pairs``).
2. ``catalogue`` — mənbə kart saxlanılan karta birləşir (mövcud ``merge_subjects`` mexanizmi: önizləmə izi, toqquşma
   varsa heç nə yazılmır, geri qaytarma). Birləşdirilmiş passiv jurnal arxiv kartda tarixçə kimi qalır (K4).
   :data:`PLAN` qrupları + (``auto_catalogue``) normallaşdırılmış adı EYNİ, krediti və növü EYNİ olan digər aktiv kartlar.
   Krediti / növü fərqli eyni adlı kartlar və adı yalnız OXŞAR kartlar birləşdirilmir — sahibin baxışı üçün sayılır.
3. ``codes`` — standart ``QKU-N`` olmayan kodlar növbəti boş ``QKU-N``-ə (:mod:`.subject_recode`, ``scope="all"``):
   kartın id-si dəyişmir, ``köhnə → yeni`` audit-də, QKU dublikatı olan kart əvvəl birləşdirilməlidir.

**Saxlanılan kartın seçimi** (``keeper`` planda açıq verilməyibsə): (1) tədris planı sətirlərinin sayı, (2) cari dövrdə
aktiv jurnalların sayı, (3) dərs yükü sətirlərinin sayı, (4) sillabus sayı, (5) standart ``QKU-N`` kodu, (6) ən kiçik
nömrə — yuxarıdan aşağı ilk fərq qalib gəlir.

Hər qaçışın paket id-si var (``dupsubj-YYYYMMDD-HHMMSS-xxxx``); ``undo`` tərs sıra ilə geri qaytarır (kodlar →
kataloq → jurnallar). Hesabat (:func:`report`) həm də QORUYUCUDUR: tələbənin eyni adlı iki fənn kartı, eyni adlı
kataloq kartları və qeyri-standart kodlar sayılır — yeni dublikat görünən kimi sıfırdan fərqli olur.
"""

from __future__ import annotations

import json
import re
import secrets
from collections import Counter, defaultdict
from pathlib import Path

from django.apps import apps as django_apps
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from . import duplicate_subjects_catalogue_2026_11_11 as catalogue_step
from . import duplicate_subjects_rules_2026_11_11 as rules
from . import subject_recode
from .duplicate_journal_merge_2026_11_11 import JournalMerge
from .duplicate_journal_merge_undo_2026_11_11 import undo as undo_journals
from .subject_codes import QKU_CODE_RE, code_shape, is_standard_code
from .subject_duplicates import normalized_subject_key

FORMAT = "duplicate-subjects/1"
OPS = ("journals", "doubles", "catalogue", "codes")
RESOURCE = "registrar.duplicate_subjects"
KIND = "duplicate_subjects"
REASON = catalogue_step.REASON
BATCH_RE = re.compile(r"^dupsubj-\d{8}-\d{6}-[0-9a-f]{4}$")
#: ``{"format", "auto_catalogue", "groups": [{"name", "keeper", "sources", "pairs": [{"source", "target"}]}]}`` —
#: YALNIZ id-lər (prod inventarı 2026-11-10 23:34 UTC; şəxsi məlumat yoxdur).
PLAN = json.loads(Path(__file__).with_suffix(".json").read_text(encoding="utf-8"))


class Stop(Exception):
    """Bütün qaçış dayanır (``CommandError`` kodu) — heç nə yazılmır."""


def _model(name, app="registrar"):
    return django_apps.get_model(app, name)


def new_batch_id() -> str:
    return f"dupsubj-{timezone.now():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def current_period(organization):
    from .exam_bridge import _current_period

    return _current_period(organization)


# ── saxlanılan kart ───────────────────────────────────────────────────────


def choose_keeper(organization, subjects, period):
    """Saxlanılan kart — modulun sənədindəki sıra ilə (deterministik)."""

    def tally(model, app="registrar", **extra):
        rows = _model(model, app)._base_manager.filter(subject__in=subjects, **extra)
        return Counter(rows.values_list("subject_id", flat=True))

    plans = tally("CurriculumSubject")
    journals = tally("CourseOffering", period=period, is_active=True) if period is not None else Counter()
    loads, syllabi = tally("TeachingTaskRow", "workload"), tally("Syllabus", "syllabus")

    def rank(subject):
        match = QKU_CODE_RE.match(subject.code or "")
        return (
            -plans[subject.pk],
            -journals[subject.pk],
            -loads[subject.pk],
            -syllabi[subject.pk],
            not is_standard_code(subject.code),
            int(match.group(1)) if match else 10**9,
            str(subject.pk),
        )

    return min(subjects, key=rank)


def same_name_groups(organization) -> list:
    """Aktiv, arxivdə olmayan, normallaşdırılmış adı EYNİ kartlar — ``[[Subject, …], …]`` (≥ 2 kart)."""
    buckets = defaultdict(list)
    rows = _model("Subject")._base_manager.filter(organization=organization, is_active=True, is_archived=False)
    for subject in rows.order_by("code"):
        key = normalized_subject_key(subject.name)
        if key:
            buckets[key].append(subject)
    return [items for _key, items in sorted(buckets.items()) if len(items) > 1]


def _plan_groups(organization, plan, counts) -> list:
    """``[(keeper, [sources], [pairs])]`` — planın qrupları (kartlar tenant daxilində yoxlanılır)."""
    Subject = _model("Subject")
    out = []
    for group in plan.get("groups") or []:
        ids = [group.get("keeper"), *(group.get("sources") or [])]
        rows = {str(row.pk): row for row in Subject._base_manager.filter(organization=organization, pk__in=ids)}
        if len(rows) != len(ids) or len(set(ids)) != len(ids):
            counts["group_subject_missing"] += 1
            continue
        meta = {key: group.get(key) for key in ("name", "reviewed", "keeper_name")}
        out.append((rows[ids[0]], [rows[pk] for pk in ids[1:]], list(group.get("pairs") or []), meta))
    return out


def _auto_groups(organization, taken, period, counts) -> list:
    out = []
    for subjects in same_name_groups(organization):
        if any(subject.pk in taken for subject in subjects):
            continue
        if len({(subject.ects, subject.kind) for subject in subjects}) > 1:
            counts["same_name_review_credit_or_kind_differs"] += 1
            continue
        if len({subject.chair_unit_id for subject in subjects}) > 1:
            # Fərqli kafedraların eyni adlı kartları ayrı fənlər ola bilər (kataloq əhatəsi kafedraya görədir) —
            # avtomatik birləşdirilmir, sahibin baxışı üçün sayılır.
            counts["same_name_review_chair_differs"] += 1
            continue
        keeper = choose_keeper(organization, subjects, period)
        out.append((keeper, [subject for subject in subjects if subject.pk != keeper.pk], [], {"name": "auto"}))
    return out


def _auto_pairs(organization, keeper, sources, explicit, period, reviewed=False) -> list:
    """Qrupun kartları üzrə İKİ aktiv jurnalı olan qrup qutuları — planda olmayanlar.

    * CARİ dövr — hər qutu (jurnal birləşməsinin bütün qoruyucuları ilə);
    * KEÇMİŞ dövr — YALNIZ qutunun bir tərəfi boş qabıqdırsa (:func:`.duplicate_subjects_rules_2026_11_11.past_shell`):
      qabıq passiv olur, datalı jurnala TOXUNULMUR (bitmiş semestrin nəticələri dəyişmir). Hər iki tərəfi datalı keçmiş
      qutu kataloq addımında toqquşma kimi görünür və sahibin qərarına qalır."""
    if period is None:
        return []
    CourseOffering = _model("CourseOffering")
    known = {str(pair.get("source")) for pair in explicit} | {str(pair.get("target")) for pair in explicit}
    boxes = defaultdict(list)
    rows = CourseOffering._base_manager.filter(
        organization=organization, subject__in=[keeper, *sources], is_active=True, group__isnull=False
    ).select_related("period")
    for offering in rows.order_by("pk"):
        if str(offering.pk) not in known:
            boxes[(offering.period_id, offering.group_id)].append(offering)
    out = []
    for (period_id, _group), items in sorted(boxes.items(), key=lambda kv: str(kv[0])):
        mine = [row for row in items if row.subject_id == keeper.pk]
        others = [row for row in items if row.subject_id != keeper.pk]
        if len(mine) != 1 or len(others) != 1:
            continue
        target, source = mine[0], others[0]
        if period_id != period.pk:
            if rules.past_shell(target, period) and not rules.past_shell(source, period):
                target, source = source, target  # boş qabıq passiv olur, datalı jurnal kataloqda keçir
            elif not rules.past_shell(source, period):
                continue
        out.append({"source": str(source.pk), "target": str(target.pk), "auto": True, "reviewed": bool(reviewed)})
    return out


# ── əməliyyatlar ──────────────────────────────────────────────────────────


def _check_pairs(keeper, sources, pairs, counts, reviewed=False) -> list:
    """Açıq cütün HƏR İKİ jurnalı qrupun (fərqli) kartlarına aid olmalıdır. Data saxlanılan kartın boş jurnalının
    əksinə mənbə kartdadırsa cüt «boş → datalı» istiqamətindədir (kataloq addımı datalı jurnalı saxlanılan karta keçirir).
    """
    CourseOffering = _model("CourseOffering")
    allowed = {keeper.pk, *(source.pk for source in sources)}
    good = []
    for pair in pairs:
        rows = dict(
            CourseOffering._base_manager.filter(pk__in=[pair.get("source"), pair.get("target")]).values_list(
                "pk", "subject_id"
            )
        )
        rows = {str(pk): subject for pk, subject in rows.items()}
        source, target = rows.get(str(pair.get("source"))), rows.get(str(pair.get("target")))
        if source not in allowed or target not in allowed or source == target:
            counts["pair_not_in_group"] += 1
            continue
        good.append({**pair, "reviewed": bool(pair.get("reviewed") or reviewed)})
    return good


def _journals(organization, actor, counts, batch, groups, lines, period) -> None:
    merger = JournalMerge(organization=organization, actor=actor, counts=counts, batch=batch)
    for keeper, sources, pairs, meta in groups:
        reviewed = bool(meta.get("reviewed"))
        explicit = _check_pairs(keeper, sources, pairs, counts, reviewed)
        merger.run(explicit + _auto_pairs(organization, keeper, sources, explicit, period, reviewed))
    for index, delta in merger.report:
        if delta:
            lines.append(f"pair={index} " + " ".join(f"{key}={value}" for key, value in sorted(delta.items())))


def _codes(organization, counts, batch) -> bool:
    result = subject_recode.plan(organization, scope="all")
    counts["codes_nonstandard_seen"] += result["counts"]["site_cards"]
    counts["codes_archived_skipped"] += result["counts"]["archived_skipped"]
    counts["codes_wait_for_merge"] += result["counts"]["has_qku_duplicate"]
    counts["codes_recoded"] += len(result["items"])
    if not result["items"]:
        return False
    try:
        subject_recode.apply_recode(organization, result["items"], batch=batch)
    except subject_recode.RecodeError as exc:
        raise Stop(f"duplicate_subjects_recode_{exc}") from None
    return True


def run(
    *,
    organization,
    actor,
    counts,
    ops=OPS,
    batch="",
    plan=None,
    lines=None,
    auto_catalogue=False,
    current_only=False,
    merged=None,
) -> str:
    """``current_only`` — kataloq addımında keçmiş dövr sətirləri mənbə kartda qalır (:mod:`.subject_merge_scope`);
    ``merged`` — (çağıranın siyahısı) birləşdirilmiş qruplar: saxlanılan kart + mənbələr (imtahan bağı yenilənsin)."""
    plan = PLAN if plan is None else plan
    if plan.get("format") != FORMAT:
        raise Stop("duplicate_subjects_plan_format_unknown")
    batch = batch or new_batch_id()
    lines = [] if lines is None else lines
    period = current_period(organization)
    groups = _plan_groups(organization, plan, counts)
    if "journals" in ops:
        _journals(organization, actor, counts, batch, groups, lines, period)
    if "doubles" in ops:
        from .duplicate_student_doubles_2026_11_11 import Doubles

        Doubles(organization=organization, actor=actor, counts=counts, batch=batch, period=period).run(
            plan.get("doubles") or [], groups, lines
        )
    audits, recoded, renames = [], False, []
    merged = [] if merged is None else merged
    if "catalogue" in ops:
        # Jurnal addımı kartları dəyişmir, amma kataloq birləşməsi arxiv bayrağını oxuyur — kartlar təzədən oxunur.
        groups = _plan_groups(organization, plan, Counter())
        if auto_catalogue or plan.get("auto_catalogue"):
            taken = {subject.pk for keeper, sources, _pairs, _meta in groups for subject in (keeper, *sources)}
            groups = groups + _auto_groups(organization, taken, period, counts)
        audits = catalogue_step.catalogue(
            organization, actor, counts, groups, lines, renames, merged, period=period, current_only=current_only
        )
    if "codes" in ops:
        recoded = _codes(organization, counts, batch)
    report(organization=organization, counts=counts)
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        new_values={"ops": list(ops), "catalogue_merges": len(audits), "recoded": recoded},
        changes={
            "kind": KIND,
            "batch": batch,
            "ops": list(ops),
            "catalogue_audits": audits,
            "catalogue_groups": merged,  # saxlanılan kart + mənbələrin köhnə ECTS-i (sahib 2026-11-11)
            "current_only": bool(current_only),
            "renames": renames,
            "recoded": recoded,
        },
        reason=REASON,
        resource_type=RESOURCE,
        resource_id=batch,
    )
    return batch


def has_batch(organization, batch) -> bool:
    rows = _model("AuditLog", "audit").objects.filter(organization=organization, resource_type=RESOURCE)
    return rows.filter(resource_id=batch, changes__kind=KIND).exists()


def undo(*, organization, actor, counts, batch) -> list:
    """Paketi TAM geri qaytarır və ya HEÇ NƏ yazmır (:class:`Stop` — çağıranın tranzaksiyası geri qaytarılır).

    Qaytarır: jurnal bağı geri qayıdan imtahanların id-ləri (çağıran onları yenidən sinxronlaşdırır) — jurnal
    birləşməsinin imtahanları + kataloq birləşməsinin kartlarının cari dövr imtahanları."""
    from .subject_merge_undo import undo as undo_catalogue

    AuditLog = _model("AuditLog", "audit")
    rows = AuditLog.objects.filter(organization=organization, resource_type=RESOURCE, resource_id=batch)
    entries = list(rows.filter(changes__kind=KIND).order_by("-created_at", "-pk"))
    if not entries:
        raise Stop("duplicate_subjects_batch_unknown")
    if rows.filter(changes__kind=f"{KIND}_undo").exists():
        raise Stop("duplicate_subjects_batch_already_undone")
    if any((entry.changes or {}).get("recoded") for entry in entries):
        try:
            counts["undo_codes"] += len(subject_recode.undo_recode(organization, batch))
        except subject_recode.RecodeError as exc:
            raise Stop(f"duplicate_subjects_undo_recode_{exc}") from None
    for entry in entries:
        rules.restore_names((entry.changes or {}).get("renames"), counts)
        for audit_id in reversed((entry.changes or {}).get("catalogue_audits") or []):
            outcome = undo_catalogue(audit_id=audit_id, actor=actor, apply=True, reason=f"Geri qaytarma — {REASON}")
            if not outcome.get("applied"):
                raise Stop("duplicate_subjects_undo_catalogue_changed_after_merge")
            counts["undo_catalogue_groups"] += 1
    from .duplicate_student_doubles_2026_11_11 import undo as undo_doubles

    undo_doubles(organization=organization, actor=actor, counts=counts, batch=batch)
    exams = set(undo_journals(organization=organization, actor=actor, counts=counts, batch=batch))
    subjects = catalogue_step.catalogue_exam_subjects(entries)
    if subjects:
        exams |= catalogue_step.current_exam_ids(subjects, current_period(organization))
    # Qismən geri qaytarma paketi «geri qaytarılıb» kimi işarələməsin: bir cüt belə dayanıbsa HEÇ NƏ yazılmır.
    for key in (
        "undo_blocked_post_merge_data",
        "undo_blocked_source_card_archived",
        "undo_empty_twin_not_restored",
        "undo_doubles_blocked_post_merge_data",
    ):
        if counts[key]:
            raise Stop(f"duplicate_subjects_{key}")
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        changes={"kind": f"{KIND}_undo", "batch": batch},
        reason=f"Geri qaytarma — {REASON}",
        resource_type=RESOURCE,
        resource_id=batch,
    )
    return sorted(exams, key=str)


# ── hesabat / qoruyucu ────────────────────────────────────────────────────


def duplicate_cards(organization, period=None) -> dict:
    """Tələbənin «Elektron jurnal»ında EYNİ adlı iki kart → ``{"twin": {(a, b): n}, "same": {(a, b): n}}``.

    ``twin`` — fərqli fənn kartları (bu modulun işi); ``same`` — eyni kartın iki jurnalı (alt qrup / qonaq qalığı).
    Açar — açılış id cütü, dəyər — hər iki jurnalda ``dropped`` OLMAYAN qeydiyyatı olan tələbə sayı."""
    period = period or current_period(organization)
    twin, same = Counter(), Counter()
    if period is None:
        return {"twin": twin, "same": same}
    rows = (
        _model("Enrollment")
        .objects.filter(organization=organization, offering__period=period)
        .exclude(status="dropped")
        .values_list("student_id", "offering_id", "offering__subject_id", "offering__subject__name")
    )
    by_student = defaultdict(lambda: defaultdict(list))
    for student_id, offering_id, subject_id, name in rows:
        by_student[student_id][normalized_subject_key(name)].append((str(offering_id), subject_id))
    for cards in by_student.values():
        for items in cards.values():
            items = sorted(set(items))
            for index, (left, left_subject) in enumerate(items):
                for right, right_subject in items[index + 1 :]:
                    (same if left_subject == right_subject else twin)[(left, right)] += 1
    return {"twin": twin, "same": same}


def report(*, organization, counts) -> dict:
    """Qoruyucu saylar (yazı yoxdur): tələbənin ikiqat kartı, eyni adlı kataloq kartları, qeyri-standart kodlar."""
    found = duplicate_cards(organization)
    counts["guard_twin_card_pairs"] += len(found["twin"])
    counts["guard_twin_card_students"] += sum(found["twin"].values())
    counts["guard_same_subject_pairs"] += len(found["same"])
    counts["guard_same_subject_students"] += sum(found["same"].values())
    counts["guard_same_name_card_groups"] += len(same_name_groups(organization))
    shapes = Counter(
        code_shape(code)
        for code in _model("Subject")._base_manager.filter(organization=organization).values_list("code", flat=True)
    )
    for shape, total in shapes.items():
        if shape != "standard":
            counts[f"guard_codes_{shape}"] += total
    counts["guard_codes_nonstandard"] += sum(total for shape, total in shapes.items() if shape != "standard")
    return found


__all__ = [
    "BATCH_RE",
    "FORMAT",
    "KIND",
    "OPS",
    "PLAN",
    "REASON",
    "RESOURCE",
    "Stop",
    "choose_keeper",
    "current_period",
    "duplicate_cards",
    "has_batch",
    "new_batch_id",
    "report",
    "run",
    "same_name_groups",
    "undo",
]
