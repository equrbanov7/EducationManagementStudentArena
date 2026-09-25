"""Sərbəst iş lövhəsi (sillabus strukturu / mövzu çeklisti) + KÖÇÜRÜLMÜŞ ("arxiv") balı.

``journal_extras`` modul-ölçü büdcəsinə görə bölünüb (``gradebook`` →
``gradebook_components`` ilə eyni nizam): lövhənin qurulması buradadır,
``journal_extras.get_selfwork_board`` isə re-eksportdur — çağıranlar üçün
API dəyişməyib.

Niyə "arxiv balı" var?
----------------------
Köhnə MyEdu sistemində sərbəst iş 0-10 arası TƏK BİR BAL idi
(``journals_dates_points`` cədvəlində ``month_id='si'`` xanası). Yeni sistemdə
sərbəst iş MÖVZU-ÇEKLİSTİDİR: tələbə neçə mövzu təhvil veribsə, o qədər bal.

Köçürmə ``si`` balını QORUYUR — ``AssessmentComponent(kind=SELF_WORK)``
üzərində ``ComponentScore`` kimi yazır. Amma mənbədə HANSI mövzuların təhvil
verildiyi YOXDUR, ona görə ``SelfWorkMark`` çeklist sətirləri QƏSDƏN
yaradılmır: "si = 7" görüb 7 mövzunu "təhvil verilib" işarələmək datanı
uydurmaq olardı. Nəticədə köçürülmüş jurnallarda çeklist boş qalır və lövhə
hər tələbə üçün "0" göstərirdi — bu modul məhz həmin GÖRÜNMƏ problemini həll
edir: bal OXUNUR və lövhədə AYRICA, OXU-ONLY sütun kimi göstərilir. Heç bir
mövzu işarələnmir, çeklist normal işləməyə davam edir.

⚠️  DİQQƏT — ARXİV BALINI GİRİŞ BALINA ƏLAVƏ ETMƏYİN  ⚠️
--------------------------------------------------------
``gradebook_components.entry_score_for`` (və onun güzgüsü
``analytics._evaluate``) sərbəst iş üçün YALNIZ ``SelfWorkMark`` işarələrinin
balını (köhnə çeklistdə — təhvil sayını; qayda ``selfwork_points``) oxuyur və
bu DÜZGÜNDÜR. Köçürmənin J5b fazası (``journal_entry_scores``)
köhnə ``girish`` dəyərini

    residual = clamp(girish − Σkollokvium − çeklist, 0, entry_max)

düsturu ilə GENERIC komponent kimi yazır; köçürülmüş datada çeklist 0 olduğuna
görə ``si`` ARTIQ həmin qalığın İÇİNDƏDİR. Yəni giriş balı onsuz da ``girish``
çıxır. Arxiv balını ora üstəgəl etmək ``girish + si`` verər — İKİQAT SAYMA,
hər tələbənin balı şişər. Bu modul YALNIZ GÖRÜNMƏ üçündür; heç bir hesablama
qaydası dəyişmir. "Məntiqli görünür" deyib ``entry_score_for``-a toxunmayın.

BAL STRUKTURU (2026-09-25)
--------------------------
Lövhə sillabusun strukturunu izləyir (:mod:`apps.registrar.selfwork_structure`):
2 × 5 / 1 × 10 — N sütun, hər xanada bal seçimi (1…max, «—»); 10 × 1 və köhnə
çeklist — 10 sütun, 1/0 çipi. «Fənn qovluğu»ndan gələn bal oxu-only nişanla
göstərilir (dəyişiklik yalnız sənədli düzəlişlə). Sillabus yalnız mövzu yoxdursa
və ya köhnə (slotsuz) mövzular varsa oxunur — sorğu büdcəsi sabit qalır.
"""

from __future__ import annotations

from decimal import Decimal

from django.utils import timezone

from apps.registrar import selfwork_points as rules
from apps.registrar import selfwork_structure as structure
from apps.registrar.gradebook import MARK_EDIT_WINDOW
from apps.registrar.models import (
    ComponentKind,
    ComponentScore,
    Enrollment,
    SelfWorkMark,
    SelfWorkTopic,
)

SELF_WORK_MAX_TOPICS = 10


def _trim(value: Decimal):
    """``Decimal("7.00")`` → ``7`` (şablonda "7.00" görünməsin).

    Kəsr hissə varsa Decimal olduğu kimi qalır — dəyər YUVARLAQLAŞDIRILMIR
    (köhnə data "hər necə hesablanıbsa hesablanıb")."""
    return int(value) if value == value.to_integral_value() else value


def archive_score_map(offering) -> dict:
    """enrollment_id → köçürülmüş sərbəst iş balı (``si``); balsızlar yoxdur.

    Performans: TƏK sorğu. Lövhə 100+ tələbəli jurnallarda da işlədiyi üçün
    sətir-başına sorğu (N+1) BURAXILMIR — ``SelfWorkMark`` map-i ilə eyni
    nizam."""
    rows = ComponentScore.objects.filter(
        component__offering=offering,
        component__kind=ComponentKind.SELF_WORK,
        enrollment__offering=offering,
    ).values_list("enrollment_id", "score")
    return {enrollment_id: _trim(score) for enrollment_id, score in rows if score is not None}


def effective_total(checklist_total, archive_score):
    """Lövhədə "CƏMİ" kimi göstəriləcək dəyər.

    QƏRAR və əsaslandırması:

    * canlı işarələrdə ƏN AZI BİR təhvil/bal varsa → CANLI cəm. Müəllimin CANLI
      datası həmişə üstündür; arxiv balı yeni mövzu işarələməyi bloklamamalıdır.
    * canlı cəm tam boşdur və arxiv balı varsa → ARXİV balı. Əks halda köçürülmüş
      jurnal yalan "0" göstərir (sahibin şikayəti məhz budur).
    * ikisi CƏMLƏNMİR. Bunlar eyni şeyin iki fərqli ÖLÇÜSÜDÜR — biri təhvil
      verilmiş mövzu sayı/balı, digəri köhnə sistemin aqreqat balı; cəmləmək
      mövcud olmayan bal uydurmaq olardı.

    Qeyd: bu YALNIZ göstərilən dəyərdir. Giriş balı (``entry_score_for``)
    buradan OXUMUR və oxumamalıdır — modul başlığındakı ikiqat-sayma
    xəbərdarlığına bax."""
    if checklist_total or archive_score is None:
        return checklist_total
    return archive_score


def _user_label(user) -> str:
    if user is None:
        return ""
    return (user.get_full_name() or "").strip() or user.username


def board_slots(plan, topics) -> list:
    """Sütunlar: strukturlu jurnalda N slot (``slot_index`` üzrə), qurulmamış strukturda
    N «virtual» slot (hələ mövzu yoxdur — xana deaktiv), qalan hallarda köhnə düzüm —
    HƏMİŞƏ 10 slot, ilk 10 mövzu sıra ilə (mockup: cədvəl 10 sütunlu, cəmi max 10)."""
    shape = plan.structure
    slotted = all(topic.slot_index is not None for topic in topics)
    if shape is not None and slotted and plan.state in (structure.STATE_OK, structure.STATE_PENDING):
        # Qurulmuş (və ya hələ qurulmamış / slotu silinmiş) struktur: N sütun, boş slot «virtual».
        by_slot = {topic.slot_index: topic for topic in topics}
        return [
            {
                "index": n,
                "topic": by_slot.get(n),
                "max_points": by_slot[n].max_points if n in by_slot else shape.per_score,
                "virtual": n not in by_slot,
            }
            for n in range(1, shape.count + 1)
        ]
    return [
        {
            "index": i + 1,
            "topic": topics[i] if i < len(topics) else None,
            "max_points": topics[i].max_points if i < len(topics) else 1,
            "virtual": False,
        }
        for i in range(SELF_WORK_MAX_TOPICS)
    ]


def _cell(slot, mark, now) -> dict:
    topic = slot["topic"]
    graded = topic is not None and rules.is_graded(mark)
    value = rules.effective_points(mark, topic) if graded else None
    from_folder = graded and mark.source == rules.SOURCE_SUBJECT_FOLDER
    return {
        "index": slot["index"],
        "topic": topic,  # None → boş/virtual slot (mövzu hələ yoxdur)
        "max_points": slot["max_points"],
        "points_mode": slot["max_points"] > 1,
        "virtual": slot["virtual"],
        "done": bool(mark and mark.done),
        "points": value,  # effektiv bal və ya None («—»)
        "points_value": rules.display(value) if value is not None else "",
        # geri alma/dəyişmə kilidi: qiymətlidir və 2 saat keçib
        "locked": bool(graded and (now - mark.updated_at) > MARK_EDIT_WINDOW),
        "from_folder": from_folder,  # «Fənn qovluğu» nişanı — lövhədə oxu-only
        "graded_at": mark.graded_at if graded else None,
        "graded_by": _user_label(mark.entered_by) if graded and mark.entered_by_id else "",
        # Bal seçimi: «—» + TAM bal 1…max; cari kəsr bal (fənn qovluğu/düzəliş) seçimdə
        # saxlanılır ki, formanın təkrar göndərilməsi onu səssizcə silməsin.
        "options": _options(slot["max_points"], value),
    }


def _options(max_points, value) -> list:
    if max_points <= 1:
        return []
    options = [str(n) for n in range(1, max_points + 1)]
    current = rules.display(value) if value is not None else ""
    if current and current not in options:
        options = sorted([*options, current], key=Decimal)
    return options


def get_selfwork_board(offering, *, with_structure=True):
    """Sərbəst iş tabı: sütunlar (``board_slots``) × tələbələr, xanalar + canlı CƏMİ /10.

    ``with_structure=False`` — yalnız rəqəm/oxu səthləri üçün («Yekun» tab sütunu,
    tələbə görünüşü): sillabus OXUNMUR, struktur yalnız artıq qurulmuş mövzulardan
    çıxarılır.

    Köçürülmüş jurnallar üçün əlavə açarlar: sətirdə ``checklist_total`` (xalis
    canlı cəm — köhnə ad, indi BAL cəmidir; çeklistdə təhvil sayı), ``archive_score``
    (köhnə ``si`` balı və ya None) və ``total`` (bax :func:`effective_total`);
    lövhədə ``has_archive`` — arxiv sütununun göstərilib-göstərilməyəcəyi."""
    topics = list(SelfWorkTopic.objects.filter(offering=offering).order_by("order", "created_at"))
    enrollments = list(
        offering.enrollments.filter(status=Enrollment.Status.ENROLLED)
        .select_related("student")
        .order_by("student__last_name", "student__username")
    )
    now = timezone.now()
    mark_map = {}
    graded_topics = set()
    for mark in SelfWorkMark.objects.filter(topic__offering=offering).select_related("entered_by"):
        mark_map[(mark.enrollment_id, mark.topic_id)] = mark
        if rules.is_graded(mark):
            graded_topics.add(mark.topic_id)
    plan = structure.load_plan(
        offering,
        topics=topics,
        graded=graded_topics,
        syllabus=structure.SYLLABUS_AUTO if with_structure else structure.SYLLABUS_NEVER,
    )
    slots = board_slots(plan, topics)
    archive_map = archive_score_map(offering)
    rows = []
    for e in enrollments:
        cells = []
        points_total = Decimal("0")
        for slot in slots:
            topic = slot["topic"]
            cell = _cell(slot, mark_map.get((e.id, topic.id)) if topic else None, now)
            points_total += cell["points"] or 0
            cells.append(cell)
        points_total = rules.cap_total(points_total)
        archive_score = archive_map.get(e.id)
        rows.append(
            {
                "enrollment": e,
                "student": e.student,
                "cells": cells,
                "checklist_total": points_total,
                "archive_score": archive_score,  # oxu-only: köçürülmüş köhnə bal
                "total": effective_total(points_total, archive_score),
            }
        )
    next_slot = structure.next_topic_slot(plan, topics) if plan.state != structure.STATE_PENDING else None
    folder_topics = {t for (_e, t), m in mark_map.items() if m.source == rules.SOURCE_SUBJECT_FOLDER and rules.is_graded(m)}
    for slot in slots:
        slot["has_folder_marks"] = bool(slot["topic"] and slot["topic"].id in folder_topics)
    return {
        "topics": topics,
        "slots": slots,
        "rows": rows,
        "max_topics": SELF_WORK_MAX_TOPICS,
        "total_max": int(rules.TOTAL_MAX),
        "has_archive": any(r["archive_score"] is not None for r in rows),
        "structure": plan.as_dict(),
        "points_mode": any(slot["max_points"] > 1 for slot in slots),
        "has_folder_marks": bool(folder_topics),
        "can_add_topic": next_slot is not None,
        "next_slot_max": next_slot[1] if next_slot else None,
    }
