"""İmtahan balının əl ilə sistemə daxil edilməsi — İmtahan Mərkəzi servisi.

SAHİBİN QƏRARI (2026-08, bağlayıcı): yazılı və praktiki imtahan KAĞIZ üzərində
(praktikidə kodda) keçir — sistemdən getmir. Balları sonradan İmtahan Mərkəzi
köçürür: dövr (tədris ili + semestr) → fənn → QRUP (açılış) → tələbə siyahısı →
hər tələbə üçün bal sahəsi; toplu yadda saxlama.

Qaydalar:

* **Qapı** — ``final_score.entry`` icazəsi (kateqoriya ``exams``); ``exam.*``
  daşıyan imtahan mərkəzi rolları və RİM onsuz da əhatə olunur.
* **Hədəf** — ``registrar.FinalGrade.exam_score``, ``finals.set_exam_score``
  üzərindən; audit izində mənbə «imtahan mərkəzi · əl ilə».
* **Cəhddən asılı deyil** — ENROLLMENT əsaslıdır (kağız imtahanda
  ``ExamAttempt`` yoxdur, spec E8).
* **Kilid** — jurnal kilidi bu yolu BLOKLAMIR: jurnal semestr sonunda bağlanır,
  imtahan ondan sonra keçir (bax ``finals.set_exam_score`` şərhi).
* **İdempotent** — eyni bal təkrar yazılsa nə dublikat sətir, nə audit yaranır.
* **İlk daxiletmə sərbəst, sonrakı dəyişiklik TƏQDİMATLI** — artıq yazılmış bal
  dəyişdirilirsə səbəb + qeyd + SƏNƏD üçü də məcburidir
  (``apps/registrar/corrections.py`` ilə eyni müqavilə).

Sübut sətirləri append-only ``ExamScoreEntry`` jurnalındadır.

2026-09-12 (sahibin tələbi — «qrup seçilsin, müəllim, tarix… balları sistemə
yüklənsin»): hər toplu yazı bir KÖÇÜRMƏ VƏRƏQİNƏ (``ExamScoreSheet`` partiyası:
imtahan tarixi, yoxlayan müəllim, nəzarətçi, protokol №, skan) bağlanır —
``sheet`` parametri. Partiyanın skanı düzəliş üçün SƏNƏD sayılır: sətir-səviyyə
fayl olmasa da ``sheet.evidence`` təqdimat tələbini ödəyir. Qrup-əvvəl seçim və
partiya köməkçiləri ``exam_score_sheets``-də, fayl idxalı ``exam_score_import``-da
— hər ikisi YALNIZ buradakı ``record_exam_score`` ilə yazır (tək yazı yolu).

2026-09-14 (W2 `w2paper`, sahib: «hər sualdan max 10, imtahandan max 50, yekun
100-dən çox ola bilməz; apellyasiyadan sonra DƏYİŞƏN nəticələr izlənsin»):
``record_exam_score`` sual-sual balları (``question_scores``) qəbul edir —
validasiya ``exam_score_questions``-dadır, cəm imtahan balı olur; giriş +
imtahan ≤ 100 açıq yoxlanır; dəyişiklik növü ``correction`` və ya ``appeal``
ola bilər (``kind``). Oxu köməkçiləri (siyahı, tarixçə sətri, filtrlər)
``exam_score_roster``-dədir və buradan re-eksport olunur.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils.translation import pgettext

from core.audit import log_action
from core.constants import AuditAction

from . import exam_score_changes  # noqa: F401 — public fasad (`registrar.public`) üzərindən çatım
from . import exam_score_questions  # noqa: F401 — eyni səbəb (accounts `service.exam_score_questions.*`)
from . import exam_score_questions as questions
from . import finals, gradebook
from .corrections import correction_author_name
from .exam_score_roster import (  # noqa: F401 — re-eksport (public fasad `exam_score_entry` üzərindən)
    STATUS_ALL,
    STATUS_CHANGED,
    STATUS_CHOICES,
    STATUS_EMPTY,
    STATUS_RECORDED,
    entries_for_offering,
    entry_row,
    filter_roster_rows,
    group_ids_for_instructor,
    instructors_for_period,
    offering_label,
    offerings_for_subject,
    roster_for_offering,
    status_counts,
    subjects_for_period,
)
from .models import (
    CorrectionReason,
    Enrollment,
    ExamScoreEntry,
    ExamScoreEntryKind,
    FinalGrade,
)

#: Bu səthi açan icazə açarı (kataloq: ``organizations.permissions``).
ENTRY_PERMISSION = "final_score.entry"

#: Audit izində bal sətrinin yanına yazılan mənbə qeydi (spec E4).
SOURCE_NOTE = "imtahan mərkəzi · əl ilə"

_CTX = "registrar.exam_score_entry"


# ── İcazə ────────────────────────────────────────────────────────────────────


def _permission_scope(user, organization):
    from django.apps import apps as django_apps

    org_unit_model = django_apps.get_model("organizations", "OrgUnit")
    return org_unit_model.user_permission_scope(user, organization, ENTRY_PERMISSION)


def can_enter_exam_scores(user, organization) -> bool:
    """``final_score.entry`` icazəsi struktur əhatəsi verirmi (org və ya unit)."""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if _is_superadmin(user):
        return True
    if organization is None:
        return False
    return _permission_scope(user, organization).has_structure_access


def _is_superadmin(user) -> bool:
    return bool(getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False))


def offering_in_actor_scope(user, organization, offering) -> bool:
    """Aktorun struktur alt-ağacı bu açılışı əhatə edirmi (fail-closed).

    ``exam.*`` wildcard-ı dekan/kafedra müdiri kimi UNIT-scoped rollara da
    ``final_score.entry`` verir — onlar YALNIZ öz alt-ağaclarının qruplarına bal
    yaza bilməlidir. Org-səviyyə rollar (imtahan mərkəzi, RİM) hər açılışı görür.
    """
    if _is_superadmin(user):
        return True
    if organization is None or offering is None:
        return False
    from . import journal_scope

    return journal_scope.offering_in_actor_scope(user, organization, offering, permission=ENTRY_PERMISSION)


def offerings_in_actor_scope(user, organization, offerings):
    """``offerings`` siyahısını aktorun əhatəsinə görə BİR sorğu ilə süzür.

    Əvvəl seçici hər açılış üçün ``offering_in_actor_scope`` çağırırdı — 62 açılış
    = 62 əhatə + 62 təşkilat sorğusu (QA 2026-09-05 P2-5).
    """
    offerings = list(offerings)
    if not offerings:
        return []
    if _is_superadmin(user):
        return offerings
    if organization is None:
        return []
    from . import journal_scope

    scope = journal_scope.permission_scope_for(user, organization, ENTRY_PERMISSION)
    if not scope.has_structure_access:
        return []
    if scope.is_org_wide:
        return offerings
    from django.apps import apps as django_apps

    group_ids = {getattr(o, "group_id", None) for o in offerings} - {None}
    org_unit_model = django_apps.get_model("organizations", "OrgUnit")
    allowed = set(
        org_unit_model.objects.filter(organization=organization, pk__in=group_ids)
        .filter(scope.unit_subtree_q())
        .values_list("pk", flat=True)
    )
    return [o for o in offerings if getattr(o, "group_id", None) in allowed]


def assert_offering_in_actor_scope(user, organization, offering):
    """Əhatədən kənar açılışda yazını fail-closed dayandır."""
    if not offering_in_actor_scope(user, organization, offering):
        raise PermissionDenied(pgettext(_CTX, "Bu açılış sizin struktur əhatənizdə deyil."))


# ── Yazı ─────────────────────────────────────────────────────────────────────


def _clean_score(raw, cap):
    """Bal TAM ədəddir (0..cap). Boş sətir → ``None`` (sətir buraxılır)."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        value = Decimal(text)
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError(pgettext(_CTX, "Bal rəqəm olmalıdır."))
    if not value.is_finite() or value != value.to_integral_value():
        raise ValidationError(pgettext(_CTX, "Bal tam ədəd olmalıdır."))
    value = value.to_integral_value()
    if value < 0 or value > Decimal(int(cap)):
        raise ValidationError(pgettext(_CTX, "Bal 0 ilə %(max)s arasında olmalıdır.") % {"max": int(cap)})
    return value


def _same_score(old, new) -> bool:
    if old is None or new is None:
        return old is None and new is None
    return Decimal(old) == Decimal(new)


def _require_justification(*, reason, note, evidence, sheet=None):
    """Sonrakı dəyişiklik = TƏQDİMAT: səbəb + qeyd + sənəd (üçü də məcburi).

    2026-09-12: sənəd sətrin öz faylı VƏ YA partiyanın (vərəqin) skanı ola
    bilər — toplu köçürmədə bir protokol bütün dəyişiklikləri əsaslandırır,
    hər sətir üçün eyni faylı təkrar saxlamağa ehtiyac yoxdur.
    """
    if reason not in CorrectionReason.values:
        raise ValidationError(pgettext(_CTX, "Balı dəyişmək üçün səbəb seçilməlidir."))
    if not (note or "").strip():
        raise ValidationError(pgettext(_CTX, "Balı dəyişmək üçün izahat qeydi məcburidir."))
    if not evidence and not (sheet is not None and sheet.evidence):
        raise ValidationError(pgettext(_CTX, "Balı dəyişmək üçün təsdiqedici sənəd əlavə olunmalıdır."))


def assert_sheet_matches(sheet, *, organization_id, offering_id):
    """Partiya bu tenanta VƏ açılışa aiddirmi — deyilsə fail-closed ``ValidationError``.

    2026-09-13, Codex audit P2-09 (I3): eyni qayda modeldə
    (``ExamScoreEntry.clean``) və DB-də (``0073``
    ``registrar_exam_score_entry_sheet_guard`` trigger-i) təkrarlanır; burada
    məqsəd xətanın yazıdan ƏVVƏL, oxunaqlı mesajla çıxmasıdır — toplu yazıda
    bir dəfə (``save_roster_scores``), tək yazıda kilidin ardınca.
    """
    if sheet is None:
        return
    if sheet.offering_id != offering_id or sheet.organization_id != organization_id:
        raise ValidationError(pgettext(_CTX, "Köçürmə vərəqi bu açılışa aid deyil."))


def _change_kind(kind) -> str:
    """Dəyişiklik növü — dialoqda seçilən ``correction`` / ``appeal``; naməlum → ``correction``."""
    return kind if kind in ExamScoreEntryKind.change_kinds() else ExamScoreEntryKind.CORRECTION


def _latest_question_scores(enrollment):
    """Sonuncu daxiletmənin sual balları (yoxdursa / tək bal rejimidirsə ``None``)."""
    row = (
        ExamScoreEntry.objects.filter(enrollment=enrollment)
        .order_by("-created_at")
        .values_list("question_scores", flat=True)
        .first()
    )
    return row if row else None


def _entry_score_for(enrollment, scheme, entry_score):
    """Giriş balı — toplu yazıda çağıran verir (sorğusuz); tək yazıda burada oxunur."""
    if entry_score is not None:
        return entry_score
    return gradebook.entry_score_for(enrollment, scheme.entry_score_max)


@transaction.atomic
def record_exam_score(
    *,
    enrollment,
    score,
    by_user,
    reason="",
    note="",
    evidence=None,
    request=None,
    sheet=None,
    question_scores=None,
    kind="",
    entry_score=None,
):
    """Bir tələbənin imtahan balını yaz (ilkin daxiletmə və ya sənədli düzəliş / apellyasiya).

    Nəticə: yaradılan :class:`ExamScoreEntry` (bal dəyişibsə) və ya ``None``
    (dəyişiklik yoxdur — İDEMPOTENT təkrar daxiletmə).

    ``sheet`` — sətrin aid olduğu köçürmə partiyası (``ExamScoreSheet``);
    verilərsə sətir ona bağlanır və partiyanın skanı düzəliş sübutu sayılır.

    2026-09-14 (W2 `w2paper`):

    * ``question_scores`` — sual-sual xam ballar (siyahı). Verilərsə (və hamısı
      boş deyilsə) imtahan balı ONLARIN CƏMİDİR — ``score`` nəzərə alınmır
      (server avtoritetdir, JS-in canlı cəmi yalnız UX-dür). Şəbəkə
      (sual sayı / bir sualın tavanı) ``sheet``-dən, cəmin tavanı sxemdən;
    * ``kind`` — dəyişiklik növü: ``correction`` (sənədli düzəliş) və ya
      ``appeal`` (apellyasiya nəticəsi); ilkin daxiletmədə həmişə ``initial``;
    * ``entry_score`` — giriş balı (toplu yazıda çağıran batch ilə verir);
      giriş + imtahan ≤ 100 AÇIQ yoxlanır.
    """
    # Lock the durable parent even when no FinalGrade exists yet. Concurrent
    # first writes must re-read the score and require correction evidence.
    enrollment = (
        Enrollment.objects.select_for_update(of=("self",))
        .select_related("offering", "organization")
        .get(pk=enrollment.pk, organization_id=enrollment.organization_id)
    )
    # Partiya başqa açılışa/tenanta aiddirsə sətir ona bağlana bilməz — hər
    # şeydən ƏVVƏL (boş və ya eyni bal olsa belə) fail-closed (P2-09, 2026-09-13).
    assert_sheet_matches(sheet, organization_id=enrollment.organization_id, offering_id=enrollment.offering_id)
    scheme = gradebook.ensure_assessment_scheme(offering=enrollment.offering)
    cap = finals.exam_score_max(scheme)
    cleaned_questions = None
    if not questions.is_blank_list(question_scores):
        # Şəbəkə vərəqdəndir; vərəqsiz tək yazıda (köhnə çağıranlar) defolt 5 × 10.
        grid = (
            {"question_count": sheet.question_count, "question_max": sheet.question_max}
            if sheet is not None
            else questions.question_defaults()
        )
        cleaned_questions, new_score = questions.clean_question_scores(question_scores, cap=cap, **grid)
    else:
        new_score = _clean_score(score, cap)
    if new_score is None:
        return None  # boş sahə = toxunma (kütləvi silinmə riskini aradan qaldırır)
    # Sahibin sözü: «yekun bal 100-dən çox ola bilməz» — tavanlar örtsə də açıq yoxla.
    questions.assert_total_within_hundred(_entry_score_for(enrollment, scheme, entry_score), new_score)

    current = FinalGrade.objects.filter(enrollment=enrollment).first()
    old_score = current.exam_score if current is not None else None
    if _same_score(old_score, new_score):
        # Eyni cəm, amma sual bölgüsü fərqlidirsə bu da DƏYİŞİKLİKDİR (kağız
        # qeydi dəyişir) — sətir yazılır, FinalGrade isə toxunulmur.
        if cleaned_questions is None or questions.same_question_scores(
            _latest_question_scores(enrollment), cleaned_questions
        ):
            return None  # eyni bal → nə dublikat sətir, nə audit

    is_correction = old_score is not None
    if is_correction:
        _require_justification(reason=reason, note=note, evidence=evidence, sheet=sheet)

    entry = ExamScoreEntry(
        organization=enrollment.organization,
        enrollment=enrollment,
        kind=_change_kind(kind) if is_correction else ExamScoreEntryKind.INITIAL,
        old_score=old_score,
        new_score=new_score,
        question_scores=cleaned_questions,
        reason=reason if reason in CorrectionReason.values else "",
        note=(note or "").strip(),
        evidence=evidence or "",
        entered_by=by_user,
        entered_by_name=correction_author_name(by_user, request),
        sheet=sheet,
    )
    # Fayl (şəkil/PDF) ölçü + tip validatorları BAL YAZILMAMIŞDAN ƏVVƏL işləsin.
    entry.full_clean(exclude=["entered_by", "sheet"])

    final_grade = finals.set_exam_score(
        enrollment=enrollment, score=new_score, by_user=by_user, source_note=SOURCE_NOTE
    )
    if final_grade is None:
        # Qeydiyyat artıq aktiv deyil (köçürülüb/ləğv olunub) — sətir yazılmır.
        raise ValidationError(pgettext(_CTX, "Bu qeydiyyat aktiv deyil — bal yazılmadı."))

    entry.save()
    log_action(
        action=AuditAction.UPDATE,
        user=by_user,
        organization=enrollment.organization,
        obj=entry,
        reason=f"exam score entry: {entry.kind}",
        request=request,
        resource_type="registrar.exam_score_entry",
        resource_id=str(entry.pk),
        changes=[
            {
                "field": "exam_score",
                "old": str(old_score) if old_score is not None else "—",
                "new": str(new_score),
            },
            *(
                [{"field": "question_scores", "old": "—", "new": ",".join(str(v) for v in cleaned_questions)}]
                if cleaned_questions is not None
                else []
            ),
        ],
    )
    return entry


def save_roster_scores(*, offering, rows, by_user, request=None, sheet=None):
    """Formadan gələn sətirləri toplu yaz.

    ``rows`` — ``{"enrollment_id", "score", "reason", "note", "evidence",
    "question_scores", "kind"}`` lüğətləri (son ikisi opsional, 2026-09-14).
    Hər sətir öz savepoint-ində yazılır: birinin rədd olunması
    (məs. sənədsiz dəyişiklik) digərlərinin yazılmasını dayandırmır; xətalar
    toplanıb geri qaytarılır.

    ``sheet`` — bütün sətirlərin bağlandığı köçürmə partiyası (2026-09-12);
    sayğacları çağıran tərəf ``exam_score_sheets.finalize_sheet`` ilə yazır.

    Nəticə: ``{"written", "skipped", "failed", "total", "errors": [(ad, mesaj), …],
    "failed_by_enrollment": {enrollment_id: mesaj}}`` (sonuncu — eyni adlı iki
    tələbənin xətası qarışmasın deyə, fayl idxalı üçün).
    """
    # Yad partiya = bütün toplu yazı DAYANIR (sətir-sətir N eyni xəta əvəzinə
    # bir aydın xəta; heç bir savepoint açılmır) — P2-09, 2026-09-13.
    assert_sheet_matches(sheet, organization_id=offering.organization_id, offering_id=offering.pk)
    enrollments = {
        str(enrollment.id): enrollment
        for enrollment in offering.enrollments.filter(status=Enrollment.Status.ENROLLED).select_related(
            "student", "offering"
        )
    }
    # Giriş balları BİR dəfə toplu (giriş + imtahan ≤ 100 yoxlaması üçün) —
    # sətir başına 4 sorğu əvəzinə sabit sayda (2026-09-14, W2 `w2paper`).
    from . import finals_batch

    scheme = gradebook.ensure_assessment_scheme(offering=offering)
    batch = finals_batch.build(list(enrollments.values()), with_finals=False)
    entry_scores = {
        enrollment_id: gradebook.entry_score_for(enrollment, scheme.entry_score_max, **batch.entry_kwargs(enrollment))
        for enrollment_id, enrollment in enrollments.items()
    }
    written, skipped, total, errors, failed_by_enrollment = 0, 0, 0, [], {}
    written_ids = []
    for row in rows:
        enrollment_id = str(row.get("enrollment_id") or "")
        enrollment = enrollments.get(enrollment_id)
        total += 1
        if enrollment is None:
            message = pgettext(_CTX, "Bu qeydiyyat aktiv deyil — bal yazılmadı.")
            errors.append((enrollment_id, message))
            failed_by_enrollment[enrollment_id] = message
            continue
        try:
            with transaction.atomic():
                entry = record_exam_score(
                    enrollment=enrollment,
                    score=row.get("score"),
                    by_user=by_user,
                    reason=row.get("reason") or "",
                    note=row.get("note") or "",
                    evidence=row.get("evidence"),
                    request=request,
                    sheet=sheet,
                    question_scores=row.get("question_scores"),
                    kind=row.get("kind") or "",
                    entry_score=entry_scores.get(enrollment_id),
                )
        except ValidationError as exc:
            message = " ".join(exc.messages)
            errors.append((_student_label(enrollment), message))
            failed_by_enrollment[str(enrollment.id)] = message
            continue
        if entry is None:
            skipped += 1
        else:
            written += 1
            written_ids.append(str(enrollment.id))
    return {
        "written": written,
        "skipped": skipped,
        "failed": len(errors),
        "total": total,
        "errors": errors,
        "failed_by_enrollment": failed_by_enrollment,
        "written_ids": written_ids,
    }


def _student_label(enrollment) -> str:
    student = enrollment.student
    return student.get_full_name() or student.username
