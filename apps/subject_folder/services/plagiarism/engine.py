"""Plagiat yoxlamasının mühərriki: barmaq izi → namizədlər → uyğunluqlar → bayraqlar.

Hər YENİ göndərişdən sonra (Celery və ya sinxron ehtiyat yolu):

1. **Barmaq izi** — mətn cavabı + faylların çıxarılmış mətni normallaşdırılır,
   söz 5-qram shingle-ləri qurulur, TAPŞIRIĞIN ÖZ MƏTNİ (başlıq + təlimat)
   çıxılır (hamının köçürdüyü şərt «oxşarlıq» sayılmasın), MinHash imzası saxlanılır.
2. **Namizədlər** — eyni tapşırıq (bütün qruplar), eyni nəsil açarlı tapşırıqlar
   (keçmiş semestrlər), sərbəst işdə eyni fənnin eyni slotu. Eyni tələbənin öz
   cəhdləri və qaralamalar HEÇ VAXT müqayisə olunmur; təşkilat sərhədi keçilmir.
3. **Uyğunluq**:
   * eyni fayl (SHA-256) — müəllimin qoşma/material faylları istisna — «exact», 1.0;
   * eyni normallaşdırılmış mətn (≥ ``MIN_EXACT_TEXT_CHARS``) — «exact», 1.0;
   * MinHash təxmini (Jaccard və «olma» payı) ≥ ``CANDIDATE_THRESHOLD`` olan
     namizədlər DƏQİQ shingle müqayisəsi ilə yoxlanılır; bal = max(Jaccard, olma payı).
4. ≥ 0.5 saxlanılır, ≥ 0.8 bayraqlanır (hər iki göndəriş). Müəllimin «plagiat
   deyil» qərarı (``dismiss_match``) bayrağı götürür, uyğunluq sətri qalır.

Cüt SİMMETRİKDİR: A yoxlananda B-nin barmaq izi hələ yoxdursa, B yoxlananda A ilə
müqayisə olunur — hər cüt ən gec gələnin yoxlamasında tutulur.
"""

from __future__ import annotations

import hashlib
import logging
from decimal import ROUND_HALF_UP, Decimal

from django.db import IntegrityError, transaction
from django.db.models import Count, Max, Q
from django.utils import timezone

from ...constants import (
    SIMILARITY_FLAG_THRESHOLD,
    SIMILARITY_STORE_THRESHOLD,
    EventKind,
    MatchMethod,
    PlagiarismStatus,
    SubmissionStatus,
    TaskKind,
)
from ...models import FolderMaterial, SimilarityMatch, Submission, SubmissionFingerprint, TaskAttachment
from ..events import record_event
from ..uploads import extension_of
from . import extract, minhash
from .normalize import normalize_text, words_of

logger = logging.getLogger(__name__)

#: Yaxın-dublikat üçün hər iki tərəfdə minimum shingle (~16 söz) — qısa cavablar yalnız DƏQİQ müqayisə olunur.
MIN_SHINGLES = 12
#: Dəqiq mətn uyğunluğu üçün minimum normallaşdırılmış uzunluq («ok», «bəli» kimi cavablar sayılmır).
MIN_EXACT_TEXT_CHARS = 60
#: MinHash təxmini bu həddən aşağıdırsa dəqiq yoxlamaya getmir.
CANDIDATE_THRESHOLD = 0.3
MAX_CANDIDATES = 2_000
#: Bir yoxlamada dəqiq (bahalı) müqayisənin yuxarı həddi.
MAX_VERIFY = 60
SAMPLE_PHRASES = 3
#: Boş faylın SHA-256-sı — «eyni fayl» sayılmır.
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


def _quantize(value: float) -> Decimal:
    return Decimal(str(max(0.0, min(1.0, value)))).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def task_boilerplate(task) -> set:
    """Tapşırığın öz mətninin shingle-ləri — hamının təkrarladığı şərt çıxılır."""
    return minhash.shingles(words_of(normalize_text(f"{task.title}\n{task.instructions}")))


def teacher_file_hashes(task) -> set:
    """Müəllimin paylaşdığı faylların heşləri (şablonu hamı qoşa bilər — «eyni fayl» sayılmır)."""
    hashes = set(TaskAttachment.objects.filter(task__lineage_key=task.lineage_key).values_list("sha256", flat=True))
    hashes |= set(FolderMaterial.objects.filter(folder_id=task.folder_id).values_list("sha256", flat=True))
    return {value for value in hashes if value}


def build_fingerprint(submission, *, boilerplate=None) -> SubmissionFingerprint:
    """Göndərişin barmaq izini (yenidən) hesablayıb saxlayır."""
    parts, file_hashes, skipped = [submission.text_answer or ""], [], []
    for row in submission.files.all().order_by("created_at"):
        file_hashes.append(row.sha256)
        text, reason = extract.extract_text(row.file, extension=extension_of(row.original_name), size=row.size)
        if reason:
            skipped.append({"file": row.original_name, "reason": reason})
        if text:
            parts.append(text)
    normalized = normalize_text("\n".join(parts))[: extract.MAX_TEXT_CHARS]
    boilerplate = task_boilerplate(submission.task) if boilerplate is None else boilerplate
    effective = minhash.shingles(words_of(normalized)) - boilerplate
    fingerprint, _created = SubmissionFingerprint.objects.update_or_create(
        submission=submission,
        defaults={
            "organization_id": submission.organization_id,
            "status": PlagiarismStatus.DONE if (normalized or file_hashes) else PlagiarismStatus.SKIPPED,
            "text": normalized,
            "text_sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest() if normalized else "",
            "shingle_count": len(effective),
            "minhash": minhash.signature(effective),
            "file_hashes": sorted(file_hashes),
            "extracted_chars": len(normalized),
            "skipped_files": skipped,
            "error": "",
            "checked_at": timezone.now(),
        },
    )
    return fingerprint


def candidate_queryset(submission):
    """Müqayisə namizədləri (modul docstring-i, 2-ci bənd)."""
    task = submission.task
    scope = Q(task_id=task.pk) | Q(task__lineage_key=task.lineage_key)
    if task.kind == TaskKind.SELFWORK and task.slot_index:
        scope |= Q(
            task__kind=TaskKind.SELFWORK,
            task__slot_index=task.slot_index,
            task__folder__subject_id=task.folder.subject_id,
        )
    return (
        Submission.objects.filter(organization_id=submission.organization_id)
        .filter(scope)
        .exclude(student_id=submission.student_id)
        .exclude(status=SubmissionStatus.DRAFT)
        .exclude(pk=submission.pk)
        .order_by("-submitted_at")
    )


def _fingerprint_of(row):
    try:
        return row.fingerprint
    except SubmissionFingerprint.DoesNotExist:
        return None


def _compare(fp, other_fp, *, own_files, own_map, boilerplate, budget) -> tuple:
    """``(score, method, detail, used_budget)`` və ya ``None``."""
    shared_files = own_files & set(other_fp.file_hashes or [])
    if shared_files:
        return 1.0, MatchMethod.EXACT, {"kind": "file", "files": len(shared_files)}, 0
    if fp.text_sha256 and fp.text_sha256 == other_fp.text_sha256 and fp.extracted_chars >= MIN_EXACT_TEXT_CHARS:
        return 1.0, MatchMethod.EXACT, {"kind": "text", "chars": fp.extracted_chars}, 0
    if fp.shingle_count < MIN_SHINGLES or other_fp.shingle_count < MIN_SHINGLES or budget <= 0:
        return None
    jaccard = minhash.estimate_jaccard(fp.minhash, other_fp.minhash)
    containment = minhash.estimate_containment(jaccard, fp.shingle_count, other_fp.shingle_count)
    if max(jaccard, containment) < CANDIDATE_THRESHOLD:
        return None
    other_set = minhash.shingles(words_of(other_fp.text)) - boilerplate
    scores = minhash.exact_scores(set(own_map), other_set)
    score = max(scores["jaccard"], scores["containment"])
    if score < SIMILARITY_STORE_THRESHOLD:
        return None
    samples = [phrase for key, phrase in own_map.items() if key in other_set][:SAMPLE_PHRASES]
    detail = {
        "kind": "shingle",
        "jaccard": round(scores["jaccard"], 3),
        "containment": round(scores["containment"], 3),
        "shared": scores["shared"],
        "sizes": [fp.shingle_count, other_fp.shingle_count],
        "samples": samples,
    }
    return score, MatchMethod.SHINGLE, detail, 1


def _store_match(submission, other, score, method, detail) -> SimilarityMatch:
    first, second = (submission, other) if submission.pk < other.pk else (other, submission)
    defaults = {
        "organization_id": submission.organization_id,
        "score": _quantize(score),
        "method": method,
        "detail": detail,
        "is_flagged": score >= SIMILARITY_FLAG_THRESHOLD,
    }
    for _attempt in range(2):
        try:
            with transaction.atomic():
                match, _created = SimilarityMatch.objects.update_or_create(
                    submission_a=first, submission_b=second, defaults=defaults
                )
                return match
        except IntegrityError:  # paralel yoxlama eyni cütü eyni anda yazdı — yenidən (artıq UPDATE olacaq)
            continue
    return SimilarityMatch.objects.get(submission_a=first, submission_b=second)


def refresh_flags(submission_ids) -> dict:
    """Göndərişlərin ``similarity_max`` / ``plagiarism_flagged`` keşini uyğunluqlardan yenidən qurur.

    Nəticə: ``{submission_id: (yeni_bayraq, əvvəlki_bayraq)}``.
    """
    changes = {}
    for submission_id in dict.fromkeys(submission_ids):
        stats = SimilarityMatch.objects.filter(
            Q(submission_a_id=submission_id) | Q(submission_b_id=submission_id)
        ).aggregate(
            top=Max("score", filter=Q(dismissed_at__isnull=True)),
            flags=Count("pk", filter=Q(is_flagged=True, dismissed_at__isnull=True)),
        )
        before = Submission.objects.filter(pk=submission_id).values_list("plagiarism_flagged", flat=True).first()
        flagged = bool(stats["flags"])
        Submission.objects.filter(pk=submission_id).update(similarity_max=stats["top"], plagiarism_flagged=flagged)
        changes[submission_id] = (flagged, bool(before))
    return changes


def run_similarity_check(submission_id) -> dict:
    """Bir göndərişin tam yoxlaması → ``{"status", "matches", "flagged", "max"}``."""
    submission = (
        Submission.objects.filter(pk=submission_id).select_related("task", "task__folder", "organization").first()
    )
    if submission is None or submission.status == SubmissionStatus.DRAFT:
        return {"status": PlagiarismStatus.SKIPPED.value, "matches": 0, "flagged": False, "max": None}
    try:
        boilerplate = task_boilerplate(submission.task)
        fingerprint = build_fingerprint(submission, boilerplate=boilerplate)
        own_files = set(fingerprint.file_hashes) - teacher_file_hashes(submission.task) - {EMPTY_SHA256}
        own_map = {
            key: phrase
            for key, phrase in minhash.shingle_map(words_of(fingerprint.text)).items()
            if key not in boilerplate
        }
        found, budget = [], MAX_VERIFY
        candidates = candidate_queryset(submission).select_related("fingerprint")[:MAX_CANDIDATES]
        for other in candidates:
            other_fp = _fingerprint_of(other)
            if other_fp is None or other_fp.status != PlagiarismStatus.DONE:
                continue
            outcome = _compare(
                fingerprint, other_fp, own_files=own_files, own_map=own_map, boilerplate=boilerplate, budget=budget
            )
            if outcome is None:
                continue
            score, method, detail, used = outcome
            budget -= used
            found.append((other, score, method, detail))
    except Exception as exc:  # yoxlama xətası göndərişi pozmur — status «failed»
        logger.exception("subject_folder: oxşarlıq yoxlaması alınmadı (%s)", submission_id)
        Submission.objects.filter(pk=submission_id).update(plagiarism_status=PlagiarismStatus.FAILED)
        SubmissionFingerprint.objects.filter(submission_id=submission_id).update(
            status=PlagiarismStatus.FAILED, error=exc.__class__.__name__[:500]
        )
        return {"status": PlagiarismStatus.FAILED.value, "matches": 0, "flagged": False, "max": None}
    with transaction.atomic():
        for other, score, method, detail in found:
            _store_match(submission, other, score, method, detail)
        changes = refresh_flags([submission.pk, *[other.pk for other, *_rest in found]])
        Submission.objects.filter(pk=submission.pk).update(plagiarism_status=fingerprint.status)
        for changed_id, (flagged, before) in changes.items():
            if flagged and not before:
                target = submission if changed_id == submission.pk else next(o for o, *_ in found if o.pk == changed_id)
                record_event(
                    target,
                    EventKind.PLAGIARISM_FLAGGED,
                    payload={"with": [str(o.pk) for o, *_ in found] if target is submission else [str(submission.pk)]},
                    audit=False,
                )
    top = max((score for _other, score, *_rest in found), default=None)
    return {
        "status": fingerprint.status,
        "matches": len(found),
        "flagged": bool(changes.get(submission.pk, (False, False))[0]),
        "max": top,
    }


__all__ = [
    "CANDIDATE_THRESHOLD",
    "MIN_EXACT_TEXT_CHARS",
    "MIN_SHINGLES",
    "build_fingerprint",
    "candidate_queryset",
    "refresh_flags",
    "run_similarity_check",
    "task_boilerplate",
    "teacher_file_hashes",
]
