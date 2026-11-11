"""Dublikat fənlər — KATALOQ addımı (``merge_duplicate_subjects_20261111 --only catalogue``), sahib 2026-11-11.

Mövcud ``merge_subjects`` mexanizmi (önizləmə izi, toqquşma varsa heç nə yazılmır, geri qaytarma) hər qrup üçün öz
savepoint-ində işləyir. Bu modul iki sahib qərarını əlavə edir:

* **«Yalnız cari və gələcək»** (``current_only``, :mod:`.subject_merge_scope`): «Köhnə illərin jurnalını ciddiyə alma,
  boşver — əsas indi və bundan sonra olandır.» Mənbənin keçmiş dövr sətirləri arxivlənən mənbə kartda qalır, keçmiş
  dövrdəki toqquşma (prod: 12 qrup, «2022/2023 Payız · 232 M rus …») bloklamır.
* **İmtahan qaydası**: «Hansı fənnə bağlı imtahan verilibsə o formada saxla … Səhv olmasın.» CARİ dövrün imtahanları
  (silinməmiş, ``start_datetime`` cari dövrün başlanğıcından sonra və ya tarixsiz) qrupun YALNIZ BİR kartındadırsa o kart
  saxlanılan olur — planın açıq ``keeper``-ini və :func:`.duplicate_subjects_2026_11_11.choose_keeper` qaydasını üstələyir.
  Cari imtahanın fənni HEÇ VAXT dəyişmir, ona görə qrup ATLANIR (hesabatda səbəblə):
  ``exams_on_both_cards`` — cari imtahanlar hər iki kartdadır; ``exam_journal_merged`` — jurnal addımı imtahan kartının
  cari jurnalını artıq digər karta birləşdirib (K4), imtahan kartı saxlanıla bilmir. Birləşən qrupda saxlanılan kartın
  cari imtahanlarının jurnal bağı əmrdə (exams tərəfi) ``exam_journal_link.refresh_links`` + ``resync_exam_journal`` ilə
  yenilənir.

Hər qrup üçün bir hesabat sətri: saxlanılan / mənbə kartların kodu və adı, köçən (cari + gələcək) və qalan (keçmiş)
açılışlar, saxlanılan və köçən imtahanlar, atlanma səbəbi.
"""

from __future__ import annotations

import re
from collections import Counter

from django.apps import apps as django_apps
from django.db import transaction
from django.db.models import Q

from . import duplicate_subjects_rules_2026_11_11 as rules
from .subject_merge_scope import EXAM_KEY, OFFERING_KEY

REASON = "Sahib 2026-11-11: dublikat fənn kartları birləşdirildi, fənn kodları vahid QKU-N standartına keçirildi"


def _current_exams(subject_ids, period):
    Exam = django_apps.get_model("exams", "Exam")
    rows = Exam._base_manager.filter(subject_id__in=list(subject_ids), is_deleted=False)
    if period is not None:
        rows = rows.filter(Q(start_datetime__isnull=True) | Q(start_datetime__date__gte=period.start_date))
    return rows


def current_exam_counts(subjects, period) -> Counter:
    """``{fənn id: cari dövr imtahanlarının sayı}`` — silinmiş imtahan sayılmır."""
    return Counter(_current_exams([subject.pk for subject in subjects], period).values_list("subject_id", flat=True))


def current_exam_ids(subject_ids, period) -> set:
    """Kartların cari dövr imtahanlarının id-ləri (silinməmiş) — jurnal bağı yenilənəcək imtahanlar."""
    return set(_current_exams(subject_ids, period).values_list("pk", flat=True))


def exam_keeper(keeper, sources, period):
    """→ ``(saxlanılan, [mənbələr], qayda, imtahan sayları)``; qayda: ``exam`` | ``exams_both`` | ``plan``."""
    cards = [keeper, *sources]
    exams = current_exam_counts(cards, period)
    holders = [card for card in cards if exams[card.pk] and card.is_active and not card.is_archived]
    if len(holders) == 1:
        chosen = holders[0]
        return chosen, [card for card in cards if card.pk != chosen.pk], "exam", exams
    return keeper, list(sources), ("exams_both" if holders else "plan"), exams


#: prod-data-ops logu yalnız ``açar=[0-9a-z_-]+`` sətirlərini buraxır — kod və ad ASCII slug kimi yazılır.
_ASCII = str.maketrans("əıöüşçğ", "eiouscg")


def _slug(value) -> str:
    text = str(value or "").lower().translate(_ASCII)
    return re.sub(r"[^0-9a-z-]+", "_", text).strip("_")[:60] or "-"


def _line(name, keeper, live, rule, exams, result=None, left=None) -> str:
    kept = exams[keeper.pk]
    moved_exams = sum(exams[source.pk] for source in live)
    parts = [
        f"group={name}",
        "detail=1",
        f"keeper={_slug(keeper.code)}",
        f"keeper_name={_slug(keeper.name)}",
        "source=" + "__".join(_slug(source.code) for source in live),
        "source_name=" + "__".join(_slug(source.name) for source in live),
        f"keeper_rule={rule}",
        f"exams_kept={kept}",
        f"exams_source={moved_exams}",
    ]
    if result is not None:
        counts = result.get("counts") or {}
        parts.append(f"offerings_moved={counts.get(OFFERING_KEY, 0)}")
        parts.append(f"offerings_left_past={(left or {}).get(OFFERING_KEY, 0)}")
        parts.append(f"exams_left_past={(left or {}).get(EXAM_KEY, 0)}")
    return " ".join(parts)


def catalogue(organization, actor, counts, groups, lines, renames, merged, *, period=None, current_only=False) -> list:
    """Kataloq birləşməsi. Hər qrup üçün sətir: ``group=<ad> catalogue=<nəticə> keeper=… source=… …``.

    Tədris planında İKİ kart da varsa (həqiqətən fərqli fənlər) qrup BİRLƏŞDİRİLMİR — ``refused_curriculum_both``."""
    from .subject_merge import MergeError, preview
    from .subject_merge_apply import apply

    audits = []
    for plan_keeper, sources, _pairs, meta in groups:
        name = re.sub(r"[^0-9a-z_-]", "_", str(meta.get("name") or "auto").lower())[:60]
        keeper, sources, rule, exams = exam_keeper(plan_keeper, sources, period)
        if rule != "plan":
            counts[f"catalogue_keeper_rule_{rule}"] += 1
        if keeper.pk != plan_keeper.pk:
            counts["catalogue_keeper_switched_by_exam"] += 1
        live = [source for source in sources if not source.is_archived]
        if not live:
            counts["catalogue_already_merged"] += 1
            lines.append(f"group={name} catalogue=already_merged")
            continue
        head = _line(name, keeper, live, rule, exams)
        if rule == "exams_both":  # imtahanın fənni dəyişməsin (sahib 2026-11-11)
            counts["catalogue_skipped_exams_on_both_cards"] += 1
            lines.extend([f"group={name} catalogue=skipped reason=exams_on_both_cards", head])
            continue
        if keeper.is_archived or not keeper.is_active:
            counts["catalogue_skipped_exam_keeper_archived"] += 1
            lines.extend([f"group={name} catalogue=skipped reason=exam_keeper_archived", head])
            continue
        if rules.shared_curricula([keeper.pk, *(source.pk for source in live)]):
            counts["catalogue_refused_curriculum_both"] += 1
            lines.extend([f"group={name} catalogue=refused_curriculum_both", head])
            continue
        try:
            with transaction.atomic():
                payload = preview(
                    organization, str(keeper.pk), [str(source.pk) for source in live], current_only=current_only
                )
                if payload["blocking_total"] and keeper.pk != plan_keeper.pk:
                    # Jurnal addımı imtahan kartının cari jurnalını artıq planın kartının jurnalına birləşdiribsə (K4:
                    # passiv datalı jurnal) imtahan kartı saxlanıla bilmir; planın kartını saxlamaq imtahanın fənnini
                    # dəyişərdi — qrup ATLANIR.
                    others = [card for card in (keeper, *live) if card.pk != plan_keeper.pk]
                    fallback = preview(
                        organization, str(plan_keeper.pk), [str(card.pk) for card in others], current_only=current_only
                    )
                    if not fallback["blocking_total"]:
                        counts["catalogue_skipped_exam_journal_merged"] += 1
                        lines.extend([f"group={name} catalogue=skipped reason=exam_journal_merged", head])
                        continue
                if payload["blocking_total"]:
                    counts["catalogue_blocked"] += 1
                    codes = sorted({item["code"] for item in payload["blocking"]})
                    for code in codes:
                        counts[f"catalogue_blocked_{code}"] += 1
                    lines.extend([f"group={name} catalogue=blocked reason={'-'.join(codes)}", head])
                    continue
                result = apply(
                    organization=organization,
                    actor=actor,
                    target_ref=str(keeper.pk),
                    source_refs=[str(source.pk) for source in live],
                    reason=REASON,
                    expected_digest=payload["digest"],
                    current_only=current_only,
                )
                if keeper.pk == plan_keeper.pk:  # planın yeni adı planın saxlanılan kartı üçündür
                    rules.rename_keeper(keeper, meta.get("keeper_name"), renames, counts)
        except MergeError as exc:
            code = re.sub(r"[^a-z_]", "_", str(exc.code).lower())
            counts["catalogue_refused"] += 1
            counts[f"catalogue_refused_{code}"] += 1
            lines.extend([f"group={name} catalogue=refused reason={code}", head])
            continue
        audits.append(result["audit_id"])
        left = payload.get("left_past") or {}
        merged.append(
            {
                "group": name,
                "keeper": str(keeper.pk),
                "keeper_ects": keeper.ects,
                "keeper_rule": rule,
                "current_only": bool(current_only),
                "sources": [{"id": str(source.pk), "code": source.code, "ects": source.ects} for source in live],
            }
        )
        counts["catalogue_groups_merged"] += 1
        counts["catalogue_cards_archived"] += len(live)
        counts["catalogue_rows_repointed"] += sum(
            value for key, value in result["counts"].items() if ":" not in key and key != "soft_json"
        )
        counts["catalogue_offerings_left_past"] += left.get(OFFERING_KEY, 0)
        counts["catalogue_exams_kept"] += exams[keeper.pk]
        counts["catalogue_exams_moved"] += result["counts"].get(EXAM_KEY, 0)
        lines.append(f"group={name} catalogue=merged archived={len(live)}")
        lines.append(_line(name, keeper, live, rule, exams, result, left))
    return audits


def catalogue_exam_subjects(entries) -> set:
    """Paketin kataloq birləşmələrinin bütün kartları (saxlanılan + mənbə) — geri qaytarmada imtahan bağı yenilənsin."""
    out = set()
    for entry in entries:
        for item in (entry.changes or {}).get("catalogue_groups") or []:
            out.add(str(item.get("keeper")))
            out.update(str(source.get("id")) for source in item.get("sources") or [])
    return out


__all__ = [
    "REASON",
    "catalogue",
    "catalogue_exam_subjects",
    "current_exam_counts",
    "current_exam_ids",
    "exam_keeper",
]
