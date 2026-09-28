"""Anonim cavab buferi və nəticələrin dərci — Audit 2026-09-28 SV-2 / SV-3.

SV-3 (DB / ehtiyat nüsxə səviyyəsində qəbz ↔ cavab bağı). Əvvəl qəbz və cavab EYNİ
tranzaksiyada ardıcıl yazılırdı: ``ORDER BY ctid`` ilə qəbzləri cavablarla «zip» etmək
və ya ortaq ``xmin`` ilə hər cavabı tələbəyə bağlamaq mümkün idi. İndi:

* :func:`enqueue` qəbzlə eyni tranzaksiyada yalnız şəxssiz BUFER sətri yazır
  (``SurveyPendingResponse`` — tələbə, vaxt, qəbz bağı yoxdur).
* :func:`flush` AYRI tranzaksiyada işləyir: eyni snapshot açarı (``bucket`` — bölmə,
  açılış, müəllim, fənn, qrup, kafedra, fakültə, ixtisas, kurs — cavabı qəbzə bağlaya
  biləcək bütün sahələr) üzrə ≥ k cavab yığılanda onları təsadüfi sıra ilə
  ``SurveyResponse``-a köçürür və buferdən silir. Nəticədə fiziki sıra və ``xmin`` cavabı
  qəbzə deyil, eyni açarlı ən azı k nəfərlik partiyaya bağlayır.
* Tetiklər: göndərişdən sonra ``on_commit`` (yalnız həmin açar), kampaniyanın bağlanması,
  nəticə görünüşü açılanda (:func:`publish_due`).

SV-2 (bağla → yenidən aç → bağla tək cavabı açır). Nəticələr yalnız ``SurveyResponse``-dan
oxunur. İLK dərcdə (:func:`publish_results`: bağlanma və ya ``closes_on`` keçəndən sonra
ilk baxış) bufer TAM köçürülür — o ana qədər heç nə göstərilməyib, fərq çıxmaq olmur;
açarın k-dan az qalığı eyni açarın təsadüfi köhnə cavabları ilə bir partiyada yenidən
yazılır (sıra ilə son qəbzlərə bağlanmasın). Dərcdən SONRA gələn cavablar (yenidən açılış,
``closes_on``-un irəli çəkilməsi) yalnız eyni açarla ≥ k yığılanda birlikdə görünür; k-dan
az qalıq heç vaxt dərc olunmur (qəbz — iştirak — qalır). İki dərc arasındakı fərq beləliklə
həmişə eyni snapshotlu ≥ k cavabdır: heç bir filtr onu bölə bilmir.

QALIQ RİSK: cavab buferdə olduğu müddətdə DB-yə birbaşa çıxış / o anda alınmış dump bufer
sətrini qəbzə bağlaya bilər (bax ``models/responses.py``). Köhnə (bu dəyişiklikdən əvvəl
yazılmış) cavablar üçün ``surveys_shuffle_responses`` əmri cavabları təsadüfi sıra ilə
yenidən yazır.
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
from collections import defaultdict

from django.db import transaction
from django.utils import timezone

from core.rls import bypass_rls

from ..constants import DEFAULT_MIN_GROUP_SIZE
from ..models import SurveyAnswer, SurveyCampaign, SurveyPendingResponse, SurveyResponse

logger = logging.getLogger(__name__)

#: Cavabın qəbzə bağlana biləcək snapshot sahələri (``SurveyResponse`` sütunları).
SNAPSHOT_FIELDS = (
    "scope",
    "offering_id",
    "teacher_id",
    "subject_id",
    "group_id",
    "teacher_department_id",
    "faculty_id",
    "program_id",
    "course_year",
)

_RANDOM = random.SystemRandom()


def _plain(value):
    return None if value is None else (value if isinstance(value, int) else str(value))


def bucket_of(snapshot) -> str:
    key = json.dumps([_plain(snapshot.get(name)) for name in SNAPSHOT_FIELDS], separators=(",", ":"))
    return hashlib.sha256(key.encode()).hexdigest()


def _k(campaign) -> int:
    return max(int(campaign.min_group_size or DEFAULT_MIN_GROUP_SIZE), DEFAULT_MIN_GROUP_SIZE)


def enqueue(*, organization_id, campaign, snapshot, answers) -> None:
    """Cavabı buferə yazır (çağıranın tranzaksiyasında); commit-dən sonra açar üzrə köçürmə."""
    snapshot = {name: _plain(snapshot.get(name)) for name in SNAPSHOT_FIELDS}
    bucket = bucket_of(snapshot)
    SurveyPendingResponse.objects.create(
        organization_id=organization_id,
        campaign=campaign,
        scope=snapshot["scope"],
        bucket=bucket,
        payload={
            "snapshot": snapshot,
            "answers": [[str(question.pk), score, text] for question, score, text in answers],
        },
    )
    campaign_id = campaign.pk
    transaction.on_commit(lambda: flush_quietly(campaign_id, bucket=bucket))


def flush_quietly(campaign_id, *, bucket=None) -> None:
    """``on_commit`` tetiyi — köçürmə xətası tələbənin göndərişini pozmamalıdır."""
    try:
        flush(campaign_id, bucket=bucket)
    except Exception:  # pragma: no cover — növbəti tetik (bağlanma / baxış) yenidən cəhd edir
        logger.exception("survey pending flush failed (campaign=%s)", campaign_id)


def _snapshot_q(snapshot) -> dict:
    return {
        (f"{name}__isnull" if snapshot[name] is None else name): (True if snapshot[name] is None else snapshot[name])
        for name in SNAPSHOT_FIELDS
    }


def _existing_items(campaign_id, snapshot, limit) -> tuple[list, list]:
    """Eyni açarın təsadüfi ``limit`` köhnə cavabı — ``(item-lər, silinəcək id-lər)``."""
    rows = list(
        SurveyResponse.objects.filter(campaign_id=campaign_id, **_snapshot_q(snapshot))
        .order_by("?")
        .values("pk", "organization_id")[:limit]
    )
    ids = [row["pk"] for row in rows]
    answers: dict = defaultdict(list)
    for response_id, question_id, score, text in SurveyAnswer.objects.filter(response_id__in=ids).values_list(
        "response_id", "question_id", "score", "text"
    ):
        answers[response_id].append([question_id, score, text])
    items = [(row["organization_id"], snapshot, answers[row["pk"]]) for row in rows]
    return items, ids


def write_batch(campaign_id, items) -> int:
    """``items`` — ``(organization_id, snapshot, [[question_id, score, text], …])``; təsadüfi sıra ilə yazır."""
    items = list(items)
    _RANDOM.shuffle(items)
    responses, answers = [], []
    for organization_id, snapshot, rows in items:
        response = SurveyResponse(organization_id=organization_id, campaign_id=campaign_id, **snapshot)
        responses.append(response)
        answers.extend(
            SurveyAnswer(
                organization_id=organization_id, response=response, question_id=question_id, score=score, text=text
            )
            for question_id, score, text in rows
        )
    SurveyResponse.objects.bulk_create(responses)
    SurveyAnswer.objects.bulk_create(answers)
    return len(responses)


def flush(campaign_id, *, bucket=None, final=False) -> int:
    """Buferi köçürür (bax modul sənədi); köçürülən cavab sayını qaytarır.

    ``final=True`` — ilk dərc: nəticə hələ dərc olunmayıbsa bütün açarlar (k-dan az qalıq
    köhnə cavablarla tamamlanır) köçürülür və ``results_published_at`` qeyd olunur.
    """
    with transaction.atomic(), bypass_rls():
        # Kampaniya sətri köçürmələri seriyalaşdırır (göndərişlər onu kilidləmir).
        # İlk dərc kilidi GÖZLƏYİR: paralel baxış köçürmədən əvvəlki dəsti görməməlidir.
        campaign = SurveyCampaign.objects.select_for_update(skip_locked=not final).filter(pk=campaign_id).first()
        if campaign is None:
            return 0
        first = final and campaign.results_published_at is None
        k = _k(campaign)
        pending = SurveyPendingResponse.objects.filter(campaign_id=campaign_id)
        if bucket is not None:
            pending = pending.filter(bucket=bucket)
        groups: dict = defaultdict(list)
        for row in pending.order_by("pk"):
            groups[row.bucket].append(row)
        items, done, moved = [], [], []
        for rows in groups.values():
            if len(rows) < k and not first:
                continue
            snapshot = rows[0].payload["snapshot"]
            items.extend((row.organization_id, snapshot, row.payload["answers"]) for row in rows)
            done.extend(row.pk for row in rows)
            if len(rows) < k:
                extra, ids = _existing_items(campaign_id, snapshot, k - len(rows))
                items.extend(extra)
                moved.extend(ids)
        count = 0
        if items:
            SurveyResponse.objects.filter(pk__in=moved).delete()
            count = write_batch(campaign_id, items)
            SurveyPendingResponse.objects.filter(pk__in=done).delete()
        if first:
            campaign.results_published_at = timezone.now()
            campaign.save(update_fields=["results_published_at"])
    return count


def publish_results(campaign_id) -> int:
    """Nəticələrin ilk dərci (bağlanma / ``closes_on`` keçəndən sonra ilk baxış); təkrar çağırış
    yalnız ≥ k açarları köçürür."""
    return flush(campaign_id, final=True)


def publish_due(campaigns) -> None:
    """Nəticə görünüşündən: effektiv bağlı, hələ dərc olunmamış kampaniyaları dərc edir."""
    for row in campaigns:
        if row.get("effective_status") == "closed" and not row.get("results_published"):
            publish_results(row["id"])


def reshuffle_campaign(campaign_id) -> int:
    """Köhnə cavabları açar üzrə təsadüfi sıra ilə YENİDƏN yazır (``surveys_shuffle_responses``)."""
    with transaction.atomic(), bypass_rls():
        SurveyCampaign.objects.select_for_update().filter(pk=campaign_id).first()
        rows = list(
            SurveyResponse.objects.filter(campaign_id=campaign_id).values("pk", "organization_id", *SNAPSHOT_FIELDS)
        )
        answers: dict = defaultdict(list)
        for response_id, question_id, score, text in SurveyAnswer.objects.filter(
            response__campaign_id=campaign_id
        ).values_list("response_id", "question_id", "score", "text"):
            answers[response_id].append([question_id, score, text])
        items = [
            (row["organization_id"], {name: row[name] for name in SNAPSHOT_FIELDS}, answers[row["pk"]]) for row in rows
        ]
        SurveyResponse.objects.filter(pk__in=[row["pk"] for row in rows]).delete()
        return write_batch(campaign_id, items)


__all__ = ["bucket_of", "enqueue", "flush", "publish_due", "publish_results", "reshuffle_campaign", "write_batch"]
