"""Sərbəst iş lövhəsi (mövzu çeklisti) + KÖÇÜRÜLMÜŞ ("arxiv") sərbəst iş balı.

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
``analytics._evaluate``) sərbəst iş üçün YALNIZ ``SelfWorkMark`` çeklist
sayını oxuyur və bu DÜZGÜNDÜR. Köçürmənin J5b fazası (``journal_entry_scores``)
köhnə ``girish`` dəyərini

    residual = clamp(girish − Σkollokvium − çeklist, 0, entry_max)

düsturu ilə GENERIC komponent kimi yazır; köçürülmüş datada çeklist 0 olduğuna
görə ``si`` ARTIQ həmin qalığın İÇİNDƏDİR. Yəni giriş balı onsuz da ``girish``
çıxır. Arxiv balını ora üstəgəl etmək ``girish + si`` verər — İKİQAT SAYMA,
hər tələbənin balı şişər. Bu modul YALNIZ GÖRÜNMƏ üçündür; heç bir hesablama
qaydası dəyişmir. "Məntiqli görünür" deyib ``entry_score_for``-a toxunmayın.
"""

from __future__ import annotations

from decimal import Decimal

from django.utils import timezone

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


def effective_total(checklist_total: int, archive_score):
    """Lövhədə "CƏMİ" kimi göstəriləcək dəyər.

    QƏRAR və əsaslandırması:

    * çeklistdə ƏN AZI BİR təhvil varsa → ÇEKLİST cəmi. Müəllimin CANLI datası
      həmişə üstündür; arxiv balı yeni mövzu işarələməyi bloklamamalıdır.
    * çeklist tam boşdur və arxiv balı varsa → ARXİV balı. Əks halda köçürülmüş
      jurnal yalan "0" göstərir (sahibin şikayəti məhz budur).
    * ikisi CƏMLƏNMİR. Bunlar eyni şeyin iki fərqli ÖLÇÜSÜDÜR — biri təhvil
      verilmiş mövzu sayı, digəri köhnə sistemin aqreqat balı; cəmləmək
      mövcud olmayan bal uydurmaq olardı.

    Qeyd: bu YALNIZ göstərilən dəyərdir. Giriş balı (``entry_score_for``)
    buradan OXUMUR və oxumamalıdır — modul başlığındakı ikiqat-sayma
    xəbərdarlığına bax."""
    if checklist_total or archive_score is None:
        return checklist_total
    return archive_score


def get_selfwork_board(offering):
    """Sərbəst iş tabı: HƏMİŞƏ 10 sabit slot (mövzu sayından asılı deyil) ×
    tələbələr, 1/0 + canlı cəm. Mövzu əlavə olunmamış slot boş/deaktivdir —
    mockup kimi cədvəl həmişə 10 sütunlu görünür, cəmi maksimum 10 bal.

    Köçürülmüş jurnallar üçün əlavə açarlar: sətirdə ``checklist_total`` (xalis
    çeklist sayı), ``archive_score`` (köhnə ``si`` balı və ya None) və ``total``
    (bax :func:`effective_total`); lövhədə ``has_archive`` — arxiv sütununun
    göstərilib-göstərilməyəcəyi."""
    topics = list(SelfWorkTopic.objects.filter(offering=offering).order_by("order", "created_at"))
    # 10 slot: i-ci slotda mövzu varsa onu, yoxdursa None göstər.
    slots = [{"index": i + 1, "topic": (topics[i] if i < len(topics) else None)} for i in range(SELF_WORK_MAX_TOPICS)]
    enrollments = list(
        offering.enrollments.filter(status=Enrollment.Status.ENROLLED)
        .select_related("student")
        .order_by("student__last_name", "student__username")
    )
    now = timezone.now()
    mark_map = {}
    for m in SelfWorkMark.objects.filter(topic__offering=offering):
        mark_map[(m.enrollment_id, m.topic_id)] = m
    archive_map = archive_score_map(offering)
    rows = []
    for e in enrollments:
        cells = []
        checklist_total = 0
        for slot in slots:
            topic = slot["topic"]
            mark = mark_map.get((e.id, topic.id)) if topic else None
            done = bool(mark and mark.done)
            checklist_total += 1 if done else 0
            cells.append(
                {
                    "index": slot["index"],
                    "topic": topic,  # None → boş slot (mövzu hələ əlavə olunmayıb)
                    "done": done,
                    # geri alma kilidi: verilib və 2 saat keçib
                    "locked": bool(mark and mark.done and (now - mark.updated_at) > MARK_EDIT_WINDOW),
                }
            )
        archive_score = archive_map.get(e.id)
        rows.append(
            {
                "enrollment": e,
                "student": e.student,
                "cells": cells,
                "checklist_total": checklist_total,
                "archive_score": archive_score,  # oxu-only: köçürülmüş köhnə bal
                "total": effective_total(checklist_total, archive_score),
            }
        )
    return {
        "topics": topics,
        "slots": slots,
        "rows": rows,
        "max_topics": SELF_WORK_MAX_TOPICS,
        "has_archive": any(r["archive_score"] is not None for r in rows),
    }
