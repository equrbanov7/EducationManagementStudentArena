"""Tələbə səthi üçün köhnə qiymət faktlarının tenant-scoped read modeli.

Bu qat kanonik balı hesablamır və xam dəyəri dəyişmir. Bir qeydiyyata aid bütün
``LegacyGradeFact`` sətirlərini (ziddiyyətli/dublikat mənbələr daxil) saxlayır,
son append-only İmtahan Mərkəzi qərarını isə yalnız təqdimat statusuna çevirir.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.db.models import Prefetch
from django.utils.translation import pgettext_lazy

from apps.registrar.models import (
    LegacyGradeEvidenceKind,
    LegacyGradeFact,
    LegacyGradeReview,
    LegacyGradeReviewDecision,
)

_KIND_LABELS = {
    LegacyGradeEvidenceKind.SUMMARY: pgettext_lazy("registrar.legacy_grade", "Köhnə yekun cədvəli"),
    LegacyGradeEvidenceKind.EXAM: pgettext_lazy("registrar.legacy_grade", "Köhnə imtahan xanası"),
    LegacyGradeEvidenceKind.RESIT: pgettext_lazy("registrar.legacy_grade", "Köhnə təkrar imtahan xanası"),
    LegacyGradeEvidenceKind.EXAM_ENTRY_EXIT: pgettext_lazy("registrar.legacy_grade", "Köhnə imtahan giriş/çıxış cəhdi"),
    LegacyGradeEvidenceKind.OTHER: pgettext_lazy("registrar.legacy_grade", "Köhnə sistemin xüsusi bal kodu"),
}

_REVIEW_LABELS = {
    LegacyGradeReviewDecision.VERIFIED: pgettext_lazy(
        "registrar.legacy_grade", "İmtahan Mərkəzi tərəfindən təsdiqlənib"
    ),
    LegacyGradeReviewDecision.DISPUTED: pgettext_lazy(
        "registrar.legacy_grade", "İmtahan Mərkəzi tərəfindən mübahisələndirilib"
    ),
    LegacyGradeReviewDecision.CORRECTION_REQUIRED: pgettext_lazy("registrar.legacy_grade", "Düzəliş tələb olunur"),
}

_MAPPING_LABELS = {
    "linked": pgettext_lazy("registrar.legacy_grade", "Qeydiyyatla uyğunlaşdırılıb"),
    "group_mismatch": pgettext_lazy("registrar.legacy_grade", "Tarixi qrup uyğunsuzluğu var"),
    "discarded_source": pgettext_lazy("registrar.legacy_grade", "Köhnə sistemdə silinmiş jurnal mənbəyidir"),
    "unresolved": pgettext_lazy("registrar.legacy_grade", "Qeydiyyatla avtomatik uyğunlaşdırılmayıb"),
    "conflict": pgettext_lazy("registrar.legacy_grade", "Mənbə sətirləri arasında ziddiyyət var"),
}

_MAPPING_LABEL_FALLBACK = pgettext_lazy("registrar.legacy_grade", "Uyğunlaşdırma yoxlanmalıdır")
_REVIEW_LABEL_FALLBACK = pgettext_lazy("registrar.legacy_grade", "İmtahan Mərkəzinin yoxlaması gözlənilir")

# Bu, review workflow statusundan ayrı, daimi legacy-bal bildirişidir. Sahibin
# tələbinə görə köhnə sistemdən köçürülmüş balın yanında qırmızı görünür
# və VERIFIED qərarından sonra da itməz. VERIFIED ayrıca İmtahan Mərkəzinin
# həmin fakt üzrə verdiyi statusdur; dəyərin legacy mənşəyini dəyişmir.
LEGACY_EXAM_CENTER_WARNING = pgettext_lazy(
    "registrar.legacy_grade",
    "İmtahan Mərkəzi ilə dəqiqləşdirilsin",
)


def _decimal_text(value: Decimal | None) -> str:
    """Mətn snapshot-u yoxdursa Decimal-i elmi notasiyasız göstər."""

    if value is None:
        return ""
    return format(value, "f")


def _score_text(fact, text_field: str, decimal_field: str) -> str:
    # Mənbənin orijinal mətn proyeksiyası birinci seçimdir: burada round/clamp
    # qadağandır. Decimal yalnız köhnə materializasiyada mətn boş qalıbsa fallback-dir.
    return getattr(fact, text_field) or _decimal_text(getattr(fact, decimal_field))


def _latest_review(fact):
    history = getattr(fact, "_student_review_history", ())
    return history[-1] if history else None


def _fact_dict(fact) -> dict:
    latest = _latest_review(fact)
    decision = latest.decision if latest else "pending"
    review_required = latest is None or latest.decision != LegacyGradeReviewDecision.VERIFIED
    return {
        "source_system": fact.source_system,
        "source_table": fact.source_table,
        "source_pk": fact.source_pk,
        "source_reference": f"{fact.source_table} #{fact.source_pk}",
        "kind": fact.evidence_kind,
        "kind_label": _KIND_LABELS.get(fact.evidence_kind, _KIND_LABELS[LegacyGradeEvidenceKind.OTHER]),
        "score_code": fact.score_code,
        "is_archive": fact.is_archive,
        "entry_score": _score_text(fact, "entry_score_text", "entry_score"),
        "exam_score": _score_text(fact, "exam_score_text", "exam_score"),
        "resit_score": _score_text(fact, "resit_score_text", "resit_score"),
        "final_score": _score_text(fact, "final_score_text", "final_score"),
        "raw_score": fact.raw_score_text,
        "legacy_attempt_type": fact.legacy_attempt_type,
        "legacy_recorded_at": fact.legacy_recorded_at_text,
        "mapping_status": fact.mapping_status,
        "mapping_label": _MAPPING_LABELS.get(fact.mapping_status, _MAPPING_LABEL_FALLBACK),
        "review_status": decision,
        "review_label": _REVIEW_LABELS.get(decision, _REVIEW_LABEL_FALLBACK),
        "review_required": review_required,
        "warning": LEGACY_EXAM_CENTER_WARNING,
    }


def legacy_grade_facts_for_enrollments(*, organization, enrollment_ids) -> dict[object, list[dict]]:
    """``enrollment_id -> bütün xam faktlar`` xəritəsi, iki sabit sorğu ilə.

    Həm ``organization``, həm enrollment ID tətbiq olunur. Bu ikiqat scope RLS-i
    əvəz etmir; tətbiq qatında səhv kontekst ötürüləndə də başqa tenant faktını
    qaytarmayan fail-closed müdafiədir.
    """

    # Enrollment UUID-dir; tipini integer/string-ə çevirmək natural-key-i
    # korlayar. Django trusted UUID/string dəyərlərini özü təhlükəsiz normallaşdırır.
    ids = {value for value in enrollment_ids if value is not None}
    if organization is None or not ids:
        return {}

    reviews = LegacyGradeReview.objects.filter(organization=organization).order_by("created_at", "id")
    facts = (
        LegacyGradeFact.objects.filter(organization=organization, enrollment_id__in=ids)
        .prefetch_related(Prefetch("reviews", queryset=reviews, to_attr="_student_review_history"))
        .order_by("enrollment_id", "source_table", "source_pk")
    )
    grouped: dict[object, list[dict]] = defaultdict(list)
    for fact in facts:
        grouped[fact.enrollment_id].append(_fact_dict(fact))
    return dict(grouped)


# ── Köçürülmüş qiymətin GÖRÜNƏN nişanı ───────────────────────────────────────
#
# Niyə AYRI bayraq sahəsi AÇILMIR
# --------------------------------
# «Bu bal köhnə sistemdəndir?» sualı sübut qatından TAM dəqiqliklə çıxır:
# qiymətin qeydiyyatına bağlı ``LegacyGradeFact`` sətri varsa — bəli.
# Sübut bazasında ölçülüb (``emsarena_j12_verify``, 2026-08-31):
#
#   * köçürülmüş açılışdakı yekun qiymət          114,021
#   * bunlardan ``LegacyGradeFact``-i olan        114,021  → **100.0 %**
#   * faktı olmayan, amma yekun qiyməti olan               0
#
# Yəni denormalizə olunmuş ``is_legacy`` sütunu HEÇ BİR yeni məlumat verməzdi —
# yalnız sinxrondan düşə bilən ikinci həqiqət mənbəyi yaradardı (borc).
# ``Lesson.is_legacy_synthesised`` bu sual üçün YARARSIZDIR: o, dərs sətrinin
# bərpa olunduğunu bildirir (304,677 dərsin 11,607-si = 3.8 %), balın mənşəyini
# yox.  ``LegacyEntityMap`` isə AÇILIŞ səviyyəsindədir — semestr nişanı üçün
# doğrudur (bax ``exam_eligibility.frozen_offering_ids``), amma tələbənin
# konkret balı üçün çox kobuddur: köçürülmüş açılışdakı 148,020 yazılışın
# 27,263-ünə (18.4 %) köhnə sistem ÜMUMİYYƏTLƏ nəticə yazmayıb.
#
# Ona görə nişan **hesablanır**, saxlanmır.

#: Nişanın öz mətni — ``exam_eligibility.FROZEN_BADGE`` ilə QƏSDƏN eynidir:
#: istifadəçi semestr nişanı ilə sətir nişanını eyni sözlə tanısın.
LEGACY_BADGE_LABEL = pgettext_lazy("registrar.legacy_grade", "Köhnə sistemdən")

LEGACY_BADGE_NOTICE = pgettext_lazy(
    "registrar.legacy_grade",
    "Bu qiymət köhnə sistemdən köçürülüb. Dəyər mənbədən olduğu kimi gətirilib — " "yenidən hesablanmayıb.",
)

LEGACY_REVIEW_PENDING_NOTICE = pgettext_lazy(
    "registrar.legacy_grade",
    "İmtahan Mərkəzi bu qiyməti hələ dəqiqləşdirməyib.",
)

#: Tələbənin OXUYACAĞI mətn (tooltip DEYİL, ekranda daimi).  Üç şeyi bir cümlədə
#: deməlidir: mənşə (köhnə sistem), qeyri-müəyyənlik (dəqiq olmaya bilər), addım
#: (İmtahan Mərkəzi).  Texniki söz («fakt», «mapping», «materializasiya») YOXDUR —
#: bunu 18 yaşlı birinci kurs tələbəsi oxuyur, registrar deyil.
#:
#: TƏK NƏTİCƏ görünən səthdə işlənir («Nəticələrim» kartı).  Cədvəl səthində
#: eyni cümlə sətir-sətir təkrarlanmır — bax :data:`LEGACY_SEMESTER_CHECK_NOTICE`.
LEGACY_RESULT_CHECK_NOTICE = pgettext_lazy(
    "registrar.legacy_grade",
    "Bu nəticə köhnə sistemdən köçürülüb və dəqiq olmaya bilər — " "dəqiqləşdirmək üçün İmtahan Mərkəzinə müraciət et.",
)

#: KOR NÖQTƏNİN mətni.  Ekranda nəticə YOXDUR («Köhnə sistemdə nəticə
#: yazılmayıb»), amma sübutda bal VAR — köhnə sistemin balı yeni sistemə nəticə
#: kimi keçməyib.  Əvvəl bu sətirlərdə qeyd SUSURDU və rəqəm yalnız qlif
#: tooltip-ində görünürdü — yəni «İmtahan Mərkəzinə müraciət et» deməyin ƏN ÇOX
#: lazım olduğu halda ekran susurdu.
#:
#: Miqyas SEÇMƏ ilə deyil, BÜTÜN populyasiya üzrə ölçülüb (dev bazası,
#: 2026-09-01: legacy faktı olan 6,821 tələbə/təşkilat cütünün hamısı real
#: ``build_student_transcript`` yolu ilə qurulub, 145,217 sətir):
#:
#:   köçürülmüş sətir                                    120,516
#:     ├─ qəti nəticəsi var (əvvəl də qeyd alırdı)       114,460
#:     ├─ nəticə yox, SÜBUTDA bal var  → KOR NÖQTƏ         5,333   (1,944 tələbə)
#:     │    bunlardan sübutdakı bal YEKUN baldır             236   (230 tələbə)
#:     └─ nə nəticə, nə mənbə balı → qeyd SUSUR              723
#:
#: yəni qeyd alan sətir 114,460 → 119,793 olur.  Qalan 723 sətir QƏSDƏN
#: susur: orada dəqiqləşdiriləsi heç nə yoxdur (bax :func:`_has_source_result`).
#:
#: ⚠️ Ayrıca yoxlanılıb ki, bu cümlə canlı semestrdə ÇIXMIR: 150 tələbəlik
#: seçmədə 143 source-only sətrin 143-ü DONMUŞ (bağlanmış) açılışdadır, canlıda
#: 0-dır — yəni «nəticə kimi keçməyib» hələ nəticə gözlənilən semestrdə tələbəni
#: yanlış həyəcanlandırmır.
#:
#: Ayrı cümlədir, çünki :data:`LEGACY_RESULT_CHECK_NOTICE` («bu nəticə …
#: köçürülüb») burada YALAN olardı: nəticə məhz köçürülməyib.
LEGACY_SOURCE_ONLY_NOTICE = pgettext_lazy(
    "registrar.legacy_grade",
    "Köhnə sistemdə bu fənnin balı var, amma yeni sistemə nəticə kimi keçməyib — "
    "dəqiqləşdirmək üçün İmtahan Mərkəzinə müraciət et.",
)

#: Yuxarıdakı halın STATUS xanası üçün etiket.  ``exam_eligibility``-nin
#: «Köhnə sistemdə nəticə yazılmayıb» etiketi bu sətirlərdə tooltip-i TƏKZİB
#: edirdi (tooltip «Mənbədəki yekun bal: 85» deyirdi), ona görə sətir öz
#: statusunda da dürüst adlandırılır.
LEGACY_SOURCE_ONLY_STATUS = pgettext_lazy(
    "registrar.legacy_grade",
    "Köhnə sistemdə bal var, nəticə keçməyib",
)

#: SEMESTR miqyaslı qeyd — cədvəl səthi üçün.  Niyə sətir səviyyəsində DEYİL:
#: brauzerdə A/B ölçülüb (1280 px, AZ, real köçürülmüş tələbə myedu.student.3373 — 49 sətir,
#: 8 semestr, 46-sı nişanlı).  HƏR İKİ variant EYNİ kod bazasından render
#: olunub (şablon müvəqqəti dəyişdirilib və sha256 ilə geri qaytarılıb):
#:
#:   A — semestr qeydi + sətir qlifi (cari):  nişanlı sətir median  96.7 px
#:       cədvəl 4,768 px · səhifə 6,452 px · cümlə  8 dəfə
#:   B — sətir-səviyyəli qeyd (rədd edilən):  nişanlı sətir median 152.2 px
#:       cədvəl 7,376 px · səhifə 8,716 px · cümlə 44 dəfə
#:
#: yəni B tipik sətri +57 %, cədvəli +55 %, səhifəni +35 % şişirdir və eyni
#: cümləni 44 dəfə təkrarlayır (banner korluğu).  Səbəb: 1280 px-də fənn
#: sütunu cəmi 205 px-dir, qeyd orada 91 px hündürlüyündə bloka qırılır.
#: Semestr blokuna BİR qeyd + sətirdəki qlif eyni məlumatı verir, tələbə isə
#: mətni yenə EKRANDA oxuyur (tooltip-də yox — sahibin tələbi).
LEGACY_SEMESTER_CHECK_NOTICE = pgettext_lazy(
    "registrar.legacy_grade",
    "Bu semestrin nişanlı nəticələri köhnə sistemdən köçürülüb və dəqiq olmaya bilər — "
    "dəqiqləşdirmək üçün İmtahan Mərkəzinə müraciət et.",
)

#: :data:`LEGACY_SOURCE_ONLY_NOTICE`-in semestr miqyaslı qarşılığı.  AYRI
#: cümlədir və yalnız həmin hal semestrdə VARSA çıxır — iki cümləni birləşdirsək
#: kor nöqtəsi olmayan semestrdə yalan məlumat verilərdi.
LEGACY_SEMESTER_MISSING_NOTICE = pgettext_lazy(
    "registrar.legacy_grade",
    "Bu semestrin bəzi fənlərində köhnə sistemin balı var, amma yeni sistemə nəticə kimi keçməyib — "
    "dəqiqləşdirmək üçün İmtahan Mərkəzinə müraciət et.",
)


def _first_nonempty(facts, key):
    for fact in facts:
        value = fact.get(key)
        if value:
            return value
    return ""


def _mark_from_facts(facts) -> dict:
    """Bir qeydiyyatın faktlarını BİR sətirlik nişana yığır (sorğu AÇMIR)."""

    # Yoxlama tələb edən BİR fakt bütün sətri «dəqiqləşdirilməli» edir:
    # nişan ən pis haldan xəbər verməlidir, ortalamadan yox.
    review_required = any(fact["review_required"] for fact in facts)
    return {
        "is_legacy": True,
        "label": LEGACY_BADGE_LABEL,
        "notice": LEGACY_BADGE_NOTICE,
        "review_required": review_required,
        "review_notice": LEGACY_REVIEW_PENDING_NOTICE if review_required else "",
        # Legacy-bal bildirişi workflow statusundan asılı deyil: mərkəzin
        # qərarı ``review_required``/``review_notice`` ilə ayrı göstərilir.
        "warning": LEGACY_EXAM_CENTER_WARNING,
        # ``result_notice`` BURADA təyin OLUNMUR: hansı cümlənin doğru olduğu
        # sətrin nəticəsindən asılıdır (bax ``attach_legacy_provenance``).
        "fact_count": len(facts),
        # Mənbə sistemi bütün faktlarda eynidir (bir köçürmə mənbəyi);
        # ilk qeyri-boş dəyər kifayətdir.
        "source_system": _first_nonempty(facts, "source_system"),
        "source_reference": _first_nonempty(facts, "source_reference"),
        "recorded_at": _first_nonempty(facts, "legacy_recorded_at"),
        # Xam mənbə dəyərləri — tooltip/detal üçün, clamp və round OLMADAN.
        "raw_entry": _first_nonempty(facts, "entry_score"),
        "raw_exam": _first_nonempty(facts, "exam_score"),
        "raw_resit": _first_nonempty(facts, "resit_score"),
        "raw_final": _first_nonempty(facts, "final_score"),
    }


def legacy_provenance_for_enrollments(*, organization, enrollment_ids) -> dict:
    """``enrollment_id -> yığcam nişan təsviri`` — GÖRÜNƏN işarə üçün.

    :func:`legacy_grade_facts_for_enrollments`-in üstündə qurulur (ikinci sorğu
    dəsti AÇILMIR), sadəcə tam fakt siyahısını bir sətirlik nişana yığır: səthlər
    üçün lazım olan «bu bal köçürülüb + mənbəsi + tarixi + xam dəyəri» dördlüyü.

    ⚠️ Sətir siyahısı olan çağıran bunu BİRBAŞA işlətməməlidir —
    :func:`attach_legacy_provenance` həm nişanı, həm tam fakt siyahısını EYNİ
    sorğu dəstindən qoşur (bax oradakı şərh).
    """

    facts_by_enrollment = legacy_grade_facts_for_enrollments(organization=organization, enrollment_ids=enrollment_ids)
    return {enrollment_id: _mark_from_facts(facts) for enrollment_id, facts in facts_by_enrollment.items() if facts}


def _has_definite_result(row) -> bool:
    """Bu sətirdə EKRANDA GÖRÜNƏN qəti nəticə varmı?

    Nəticə yalnız ``passed``/``failed`` olanda qətidir — «Davam edir» sətrində
    yekun bal göstərilmir (bax şablonlardakı eyni şərt).

    ⚠️ Bu, tək başına «qeyd lazımdırmı?» sualının cavabı DEYİL: sətirdə nəticə
    görünməsə də sübutda bal ola bilər (bax :func:`_has_source_result` və
    :data:`LEGACY_SOURCE_ONLY_NOTICE`).
    """

    result = row.get("result") or {}
    return bool(result.get("passed") or result.get("failed"))


def _has_source_result(mark) -> bool:
    """Sübutda tələbəyə deyiləsi bir NƏTİCƏ balı varmı?

    Yekun / imtahan / təkrar imtahan balı — üçü də köhnə sistemin nəticə
    ölçüsüdür və qlif tooltip-i onları onsuz da göstərir.  Giriş balı
    (``raw_entry``) QƏSDƏN sayılmır: o, davamiyyət/kollokvium toplusudur,
    «nəticə» deyil.
    """

    return bool(mark["raw_final"] or mark["raw_exam"] or mark["raw_resit"])


def attach_legacy_provenance(
    rows,
    *,
    organization,
    id_key="enrollment_id",
    target_key="legacy",
    with_facts=True,
):
    """Hazır sətir siyahısına nişanı **yerində** qoşur (tək toplu sorğu).

    Sətirlər müxtəlif qurucudan gəlir (transkript, «Ümumi tədris məlumatı»,
    akademik qeydlər), amma hamısı eyni sabit ``enrollment_id`` daşıyır — nişan
    hər səthdə eyni yerdən çıxsın deyə qoşma məntiqi burada TƏKDİR.

    Nişanı olmayan sətirdə açar ``None`` qalır (şablon ``{% if row.legacy %}``
    yazsın), yəni «köhnə deyil» ilə «hələ yüklənməyib» qarışmır.

    ``show_result_notice`` BURADA hesablanır (``_mark_from_facts`` yox), çünki
    qərar sətrin NƏTİCƏSİNDƏN asılıdır, qeydiyyatın faktlarından yox: eyni
    qeydiyyatın nişanı hansı cümləni deməli olduğu sətirdən çıxır.  Bir yerdə
    hesablanır ki, «Nəticələrim» ilə «Ümumi tədris məlumatı» eyni sətri fərqli
    göstərməsin.

    ``with_facts`` — TAM fakt siyahısı da EYNİ sorğu dəstindən sətrə qoşulur
    (``legacy_grade_facts`` + ``legacy_grade_review_required``).  Bu, pulsuzdur:
    faktlar nişanı qurmaq üçün onsuz da oxunub dict-ə çevrilir, əvvəl sadəcə
    atılırdı və «Nəticələrim» səthi onları İKİNCİ dəfə sorğulayırdı
    (``registrar.public.student_academic_record_rows``).  ``False`` versən
    qoşulmur.
    """
    rows = list(rows)
    if not rows:
        return rows
    facts_by_enrollment = legacy_grade_facts_for_enrollments(
        organization=organization,
        enrollment_ids=(row.get(id_key) for row in rows),
    )
    for row in rows:
        facts = facts_by_enrollment.get(row.get(id_key)) or []
        # Sətir başına NÜSXƏ: eyni qeydiyyat iki sətirdə görünsə, birinin
        # sətir-səviyyəli bayrağı digərinə sızmasın.
        mark = _mark_from_facts(facts) if facts else None
        if mark is not None:
            definite = _has_definite_result(row)
            # KOR NÖQTƏ: sətirdə nəticə görünmür, amma sübutda bal var.  Qeyd
            # məhz BURADA ən çox lazımdır — əvvəl susurdu.
            source_only = not definite and _has_source_result(mark)
            mark["source_only"] = source_only
            mark["show_result_notice"] = bool(mark["review_required"] and (definite or source_only))
            mark["result_notice"] = LEGACY_SOURCE_ONLY_NOTICE if source_only else LEGACY_RESULT_CHECK_NOTICE
            mark["status_label"] = LEGACY_SOURCE_ONLY_STATUS if source_only else ""
        row[target_key] = mark
        if with_facts:
            row["legacy_grade_facts"] = facts
            row["legacy_grade_review_required"] = bool(mark and mark["review_required"])
    return rows


def semester_notice_flags(rows) -> dict:
    """Bir semestr blokunun (cədvəl səthi) qeyd MƏTNLƏRİ — TƏK tərif.

    Cümlə sətir-sətir təkrarlanmır; blok başına BİR dəfə çıxır və hansı cümlənin
    doğru olduğunu bu funksiya deyir.  Dəyər ya mətndir, ya boş sətir — şablon
    ``{% if sem.legacy_check_notice %}`` yazır və mətni İKİNCİ yerdə (şablon
    ``{% trans %}``-ında) təkrar tərif etmir; belə olsa iki mətn sürüşərdi.
    İkisi də boş ola bilər (bloku keçmiş, amma artıq yoxlanmış sətirlər).
    """

    check = missing = False
    for row in rows:
        mark = row.get("legacy")
        if not mark or not mark.get("show_result_notice"):
            continue
        if mark.get("source_only"):
            missing = True
        else:
            check = True
    return {
        "legacy_check_notice": LEGACY_SEMESTER_CHECK_NOTICE if check else "",
        "legacy_missing_notice": LEGACY_SEMESTER_MISSING_NOTICE if missing else "",
    }


__all__ = [
    "LEGACY_BADGE_LABEL",
    "LEGACY_BADGE_NOTICE",
    "LEGACY_EXAM_CENTER_WARNING",
    "LEGACY_RESULT_CHECK_NOTICE",
    "LEGACY_REVIEW_PENDING_NOTICE",
    "LEGACY_SEMESTER_CHECK_NOTICE",
    "LEGACY_SEMESTER_MISSING_NOTICE",
    "LEGACY_SOURCE_ONLY_NOTICE",
    "LEGACY_SOURCE_ONLY_STATUS",
    "attach_legacy_provenance",
    "legacy_grade_facts_for_enrollments",
    "legacy_provenance_for_enrollments",
    "semester_notice_flags",
]
