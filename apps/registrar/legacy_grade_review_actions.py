"""Köçürülmüş nəticənin dəqiqləşdirilməsi — YAZI qatı (append-only).

İKİ ƏMƏL, İKİ FƏRQLİ MƏNA
-------------------------
* **Təsdiqlə** — «dəyər doğrudur, baxış bitdi». Canlı bala TOXUNMUR; yalnız
  ``LegacyGradeReview`` sətri yaranır.
* **Düzəlt** — «dəyər səhvdir». Canlı bal MÖVCUD auditli axınla dəyişdirilir
  (``exam_score_entry.record_exam_score``: ``ExamScoreEntry`` + səbəb + qeyd +
  SƏNƏD + audit + jurnal güzgüsü). Bu modul YENİ düzəliş axını YAZMIR — sadəcə
  mövcud axını çağırır və nəticəni yoxlama qərarı ilə möhürləyir.
* **Mübahisələndir** — «qərar verilə bilmir, kağız jurnal lazımdır». Sətir
  növbədə qalır, amma artıq «heç kim baxmayıb» statusunda deyil.

NİYƏ DÜZƏLİŞDƏN SONRA QƏRAR ``VERIFIED`` OLUR
---------------------------------------------
``review_required`` bayrağı (transkript və digər səthlərdəki nişan) məhz
«İmtahan Mərkəzi hələ dəqiqləşdirməyib» deməkdir. Düzəliş tətbiq olunandan
sonra sətir DƏQİQLƏŞDİRİLMİŞ sayılır, ona görə qərar ``VERIFIED``-dir; «bu
təsdiq deyil, düzəlişdir» məlumatı isə ``reason_code``-da qalır və status
süzgəci «Düzəldilib» ilə «Təsdiqlənib»i məhz oradan ayırır.

⚠️ KÖHNƏ SƏTİR HEÇ VAXT ÜZƏRİNDƏN YAZILMIR. ``LegacyGradeFact`` append-only-dir;
düzəliş CANLI ``FinalGrade``-ə gedir, sübut isə olduğu kimi qalır — sonradan
«köhnə sistemdə nə yazılmışdı» sualı həmişə cavablana bilir.
"""

from __future__ import annotations

import hashlib

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils.translation import pgettext

from core.audit import log_action
from core.constants import AuditAction

from . import exam_score_entry
from .legacy_grade_review import encode_category_codes, matched_category_codes
from .models import LegacyGradeFact, LegacyGradeReview, LegacyGradeReviewDecision

# Tərcümə konteksti hər çağırışda HƏRFİ sətirdir, dəyişən DEYİL: ``xgettext``
# ``pgettext``-in kontekst arqumentini yalnız hərfi sətir olanda oxuya bilir —
# dəyişən verilsə sətri SƏSSİZCƏ atır və mətn heç bir dilə çıxmır.

#: ``reason_code`` sabitləri — ``token_validator`` formatına uyğun (a-z0-9._-).
REASON_VERIFIED = "exam_center_verified"
REASON_CORRECTED = "exam_center_corrected"
REASON_DISPUTED = "exam_center_disputed"

#: Səth əməli → (qərar, səbəb kodu).
DECISION_BY_ACTION = {
    "verify": (LegacyGradeReviewDecision.VERIFIED, REASON_VERIFIED),
    "dispute": (LegacyGradeReviewDecision.DISPUTED, REASON_DISPUTED),
    "correct": (LegacyGradeReviewDecision.VERIFIED, REASON_CORRECTED),
}

MIN_NOTE_LENGTH = 3
MAX_NOTE_LENGTH = 1000


class LegacyReviewError(ValidationError):
    """Səthə göstərilə bilən yoxlama xətası."""


def _digest(*parts) -> str:
    """Qərarın məzmun möhürü — eyni qərar həmişə eyni digest verir.

    Möhürə faktın MƏNBƏ açarı düşür (``source_table``/``source_pk``), hədəf
    UUID-si yox: repetisiya bazası yenidən qurulanda UUID dəyişir, mənbə açarı
    isə sabit qalır — beləliklə iki qaçış arasında digest müqayisə oluna bilir.
    """
    payload = "\x1f".join(str(part or "") for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _fact_or_error(*, organization, fact_id):
    fact = LegacyGradeFact.objects.filter(organization=organization, pk=fact_id).select_related("enrollment").first()
    if fact is None:
        raise LegacyReviewError(pgettext("registrar.legacy_grade_review", "Köhnə qiymət faktı tapılmadı."))
    return fact


def _clean_note(note, *, required):
    text = (note or "").strip()
    if required and len(text) < MIN_NOTE_LENGTH:
        raise LegacyReviewError(pgettext("registrar.legacy_grade_review", "Qərarın səbəbini yazın — qeyd məcburidir."))
    return text[:MAX_NOTE_LENGTH]


def _write_review(*, organization, fact, decision, reason_code, note, actor, category_codes=""):
    """``LegacyGradeReview`` sətrini yaz; icazə yoxlaması MODELDƏDİR (fail-closed).

    Model ``clean()``-də ``final_score.entry`` icazəsini və struktur əhatəsini
    yenidən yoxlayır. Burada onu təkrarlamırıq ki, iki yerdə ayrı-ayrı sürüşən
    qapı yaranmasın; sadəcə modelin xətasını səthə anlaşılan formada ötürürük.
    """
    review = LegacyGradeReview(
        organization=organization,
        fact=fact,
        decision=decision,
        reason_code=reason_code,
        note=note,
        # Qərarın hansı suala cavab verdiyini SAXLAYIRIQ: canlı-mənbəli
        # kateqoriya düzəlişdən sonra öz-özünə pozulur, möhür isə sətri
        # «Düzəldilib» süzgəcində və irəliləyiş məxrəcində saxlayır.
        category_codes=category_codes,
        evidence_digest=_digest(fact.source_system, fact.source_table, fact.source_pk, decision, reason_code, note),
        reviewed_by=actor,
    )
    try:
        review.save()
    except ValidationError as exc:
        message_dict = getattr(exc, "message_dict", {})
        if "reviewed_by" in message_dict:
            raise PermissionDenied(
                pgettext("registrar.legacy_grade_review", "Köhnə rəsmi balı dəqiqləşdirmək üçün səlahiyyətiniz yoxdur.")
            )
        raise
    return review


@transaction.atomic
def record_decision(*, organization, fact_id, action, note, actor, request=None):
    """«Təsdiqlə» / «Mübahisələndir» — canlı bala TOXUNMADAN yoxlama qərarı."""
    if action not in ("verify", "dispute"):
        raise LegacyReviewError(pgettext("registrar.legacy_grade_review", "Naməlum əməliyyat."))
    decision, reason_code = DECISION_BY_ACTION[action]
    fact = _fact_or_error(organization=organization, fact_id=fact_id)
    # Təsdiqdə qeyd sərbəstdir (dəyər dəyişmir); mübahisədə MƏCBURİDİR —
    # «niyə mübahisəlidir» sualı cavabsız qalsa, növbədə əbədi ilişir.
    note = _clean_note(note, required=(action == "dispute"))
    review = _write_review(
        organization=organization,
        fact=fact,
        decision=decision,
        reason_code=reason_code,
        note=note,
        actor=actor,
        category_codes=encode_category_codes(matched_category_codes(organization=organization, fact_id=fact.pk)),
    )
    log_action(
        action=AuditAction.UPDATE,
        user=actor,
        organization=organization,
        obj=review,
        reason=f"legacy grade review: {reason_code}",
        request=request,
        resource_type="registrar.legacy_grade_review",
        resource_id=str(review.pk),
        changes=[{"field": "decision", "old": "—", "new": str(decision)}],
    )
    return review


@transaction.atomic
def apply_correction(*, organization, fact_id, score, reason, note, evidence, actor, request=None):
    """«Düzəlt» — MÖVCUD auditli imtahan-balı axını ilə canlı dəyəri düzəlt.

    Ardıcıllıq QƏSDƏN belədir: əvvəlcə bal yazılır, sonra yoxlama qərarı. Bal
    yazısı rədd olunsa (sənədsiz dəyişiklik, əhatədən kənar açılış, passiv
    qeydiyyat) qərar da yazılmır — «dəqiqləşdirildi» deyib heç nə dəyişməmək
    ən pis nəticə olardı. Hər ikisi eyni tranzaksiyadadır.
    """
    fact = _fact_or_error(organization=organization, fact_id=fact_id)
    enrollment = fact.enrollment
    if enrollment is None:
        raise LegacyReviewError(
            pgettext(
                "registrar.legacy_grade_review",
                "Bu fakt qeydiyyata bağlanmayıb — düzəliş üçün əvvəlcə sahibi müəyyənləşdirilməlidir.",
            )
        )
    note = _clean_note(note, required=True)
    # Kateqoriya möhürü BAL YAZILMAZDAN ƏVVƏL çıxarılır: `live_exam_mismatch`
    # şərti məhz bu düzəlişlə pozulacaq, sonra soruşsaq möhür boş qayıdardı.
    category_codes = encode_category_codes(matched_category_codes(organization=organization, fact_id=fact.pk))
    # Açılış əhatəsi: `exam.*` daşıyan unit-scoped aktor yalnız öz alt-ağacına
    # yaza bilər. Servis qatının öz fail-closed yoxlaması.
    exam_score_entry.assert_offering_in_actor_scope(actor, organization, enrollment.offering)
    entry = exam_score_entry.record_exam_score(
        enrollment=enrollment,
        score=score,
        by_user=actor,
        reason=reason,
        note=note,
        evidence=evidence,
        request=request,
    )
    if entry is None:
        raise LegacyReviewError(
            pgettext(
                "registrar.legacy_grade_review",
                "Yeni bal cari dəyərlə eynidir — düzəliş yazılmadı. Fərqli dəyər yazın və ya təsdiqləyin.",
            )
        )
    decision, reason_code = DECISION_BY_ACTION["correct"]
    review = _write_review(
        organization=organization,
        fact=fact,
        decision=decision,
        reason_code=reason_code,
        # Qeyd sətri düzəlişin dəltasını da daşıyır ki, yoxlama tarixçəsi tək
        # başına oxunanda «nə dəyişdi» sualı `ExamScoreEntry`-yə getmədən cavablansın.
        note=f"{entry.old_score if entry.old_score is not None else '—'} → {entry.new_score} · {note}"[
            :MAX_NOTE_LENGTH
        ],
        actor=actor,
        category_codes=category_codes,
    )
    return {"entry": entry, "review": review}


__all__ = [
    "DECISION_BY_ACTION",
    "MAX_NOTE_LENGTH",
    "MIN_NOTE_LENGTH",
    "REASON_CORRECTED",
    "REASON_DISPUTED",
    "REASON_VERIFIED",
    "LegacyReviewError",
    "apply_correction",
    "record_decision",
]
