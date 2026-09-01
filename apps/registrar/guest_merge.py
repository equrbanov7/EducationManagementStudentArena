"""«Alt qrup birləşməsi» — tələbəni ÖZ jurnalından azad edib hədəf jurnala köçürmək.

NİYƏ BU MODUL VAR
─────────────────
:mod:`apps.registrar.guest_roster` alt qrupdan əlavəni idarə edir, amma onun
dublikat qapısı real ssenarini dalana salırdı: mandat fənlər (`services.
enroll_mandatory_subjects`) HƏR qrup üçün avtomatik açılış yaradır, yəni «Tarix»
fənni üzrə G2 tələbəsinin ÖZ G2 jurnalı onsuz da var. G1 jurnalına əlavə etmək
istəyəndə qapı «bu fənn üzrə artıq başqa jurnalda aktivdir» deyib dayanırdı,
çıxış yolu isə yox idi (öz jurnalından çıxarmaq da qadağandır).

Bu modul həmin çıxış yolunu NƏZARƏTLİ və AUDİTLİ şəkildə verir: mənbə qeydiyyat
`dropped` + `superseded_by` → hədəf qeydiyyat.

NİYƏ YENİ SEMANTİKA İCAD OLUNMUR
────────────────────────────────
`dropped` + `superseded_by` naxışı rəsmi qrup köçürməsinin (:mod:`apps.registrar.
transfer`) EYNİSİDİR: eyni tələbə, eyni fənn, eyni dövr üzrə bir qeydiyyat
digərini əvəz edir. `Enrollment.clean()` bu zənciri onsuz da doğrulayır
(eyni org/tələbə/fənn/dövr + dövr yoxdur) və `superseded_enrollment_is_dropped`
məhdudiyyəti statusun tarixçə statusu olmasını tələb edir. Yəni birləşmə ayrıca
model, ayrıca status və ya ayrıca bayraq TƏLƏB ETMİR.

KÖHNƏ İŞİN TALEYİ (qərar və əsaslandırma)
─────────────────────────────────────────
Mənbə qeydiyyat SİLİNMİR — bütün `LessonMark`, `ComponentScore`, `SelfWorkMark`,
`CourseWork` sətirləri olduğu kimi bazada qalır və `superseded_by` ilə hədəf
qeydiyyata bağlanır. Amma `dropped` sətir bütün UI səthlərindən düşür, ona görə
görünürlük AYRICA həll olunur:

1. **Qayıb saatı KÖÇÜRÜLÜR** (`carried_absence_hours`). Qayıb limiti (25%)
   qaydası DƏRSƏ yox, FƏNNƏ + SEMESTRƏ aiddir: tələbə semestrin yarısında
   birləşsə, əvvəlki 3 həftədə yığdığı 8 saat qayıb «unudulmamalıdır» — əks
   halda birləşmə imtahana buraxılış hədini sıfırlayan boşluq olardı. Saat
   skalyar sayğacdır (dərsə bağlı deyil), ona görə köçürmək TƏHLÜKƏSİZDİR.
   Həm canlı qrid (:func:`gradebook.get_offering_journal`), həm də denormallaşmış
   `Enrollment.absence_hours` (:func:`gradebook.recompute_absence_hours`) bunu
   nəzərə alır — yəni «Fənlərim», analitika və imtahan körpüsü də düzgün rəqəmi
   görür.

2. **Bal KÖÇÜRÜLMÜR — GÖSTƏRİLİR.** `LessonMark` konkret `Lesson` sətrinə
   bağlıdır; hədəf jurnalda o dərslər YOXDUR. Balları köçürmək ya uydurma xana
   yaratmaq (tələbənin iştirak etmədiyi dərsə qiymət), ya da hədəf jurnalın
   komponent tavanlarını ikiqat saymaq demək olardı — hər ikisi qiymət
   bütövlüyünü pozur. Əvəzinə hədəf jurnalın sətri «əvvəlki jurnal» xülasəsi
   daşıyır (neçə qiymət, neçə q/b, giriş balı, hansı qrup) və müəllim/koordinator
   lazım bilsə balı mövcud AUDİTLİ komponent/düzəliş axını ilə özü yazır.

3. **Transkript.** Mənbə qeydiyyat `dropped` olduğu üçün transkriptdən düşür,
   amma fənn İTMİR: hədəf qeydiyyat aktivdir və eyni fənni, eyni dövrü daşıyır.
   Hər ikisini göstərmək semestrdə fənni İKİ DƏFƏ saymaq (ÜOMG-də kreditin
   ikiqat çəkisi) demək olardı — məhz buna görə rəsmi qrup köçürməsi də
   əvəzlənmiş sətri gizlədir. Tarixçə `superseded_by` zənciri + audit izi ilə
   həmişə sorğulana bilir.

GERİ QAYTARMA
─────────────
Hədəf sətri geri götürüləndə (:func:`restore_source`) mənbə qeydiyyat AVTOMATİK
bərpa olunur: `superseded_by` təmizlənir, status `enrolled` olur. Beləliklə
tələbə «heç yerdə» qalmır.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.utils.translation import pgettext

from core.audit import log_action
from core.constants import AuditAction

from .models import (
    AssessmentComponent,
    AssessmentScheme,
    AttendanceStatus,
    ComponentScore,
    Enrollment,
    FinalGrade,
    LessonMark,
    SelfWorkMark,
)

_CTX = "registrar.guest_roster"

#: Birləşmə səbəbi (dekanlıq sərəncamı nömrəsi kimi) MƏCBURİDİR — bu qədər simvol.
MIN_REASON_LENGTH = 5

#: Sxemi olmayan açılışda giriş balı tavanı (``AssessmentScheme.entry_score_max``
#: model defoltu ilə EYNİ). Oxu yolu sxem YARATMIR — ``ensure_assessment_scheme``
#: qrid çəkilişində yan-təsirli INSERT edərdi.
DEFAULT_ENTRY_SCORE_MAX = 50


# ── Münaqişə (eyni fənn + dövr üzrə başqa jurnal) ────────────────────────────


def conflicting_enrollments(*, offering, student, lock=False):
    """Eyni fənn+dövr üzrə BAŞQA jurnaldakı aktiv qeydiyyatlar (adətən 0 və ya 1).

    ``lock=True`` — mutasiya yolunda sətri kilidləyir. ``of=("self",)`` MƏCBURİDİR:
    `select_for_update` + nullable FK-lı `select_related` yalnız PostgreSQL-də
    çökür (outer join FOR UPDATE-də ola bilməz).
    """
    queryset = Enrollment.objects.filter(
        organization=offering.organization,
        student=student,
        offering__subject_id=offering.subject_id,
        offering__period_id=offering.period_id,
        status=Enrollment.Status.ENROLLED,
    ).exclude(offering_id=offering.pk)
    if lock:
        queryset = queryset.select_for_update(of=("self",))
    return list(queryset.select_related("offering", "offering__group", "offering__subject").order_by("created_at"))


# ── Mənbə jurnaldakı işin xülasəsi ───────────────────────────────────────────


def work_summary(enrollment) -> dict:
    """Bir qeydiyyatın jurnal izi: neçə qiymət, neçə q/b, giriş balı, yekun var/yox.

    Təsdiq önbaxışı və audit üçün — istifadəçi «nə itə bilər» sualının cavabını
    təsdiqdən ƏVVƏL görməlidir.
    """
    from apps.registrar import gradebook

    marks = list(LessonMark.objects.filter(enrollment=enrollment).select_related("lesson"))
    absent = [mark for mark in marks if mark.status == AttendanceStatus.ABSENT]
    scheme = gradebook.ensure_assessment_scheme(offering=enrollment.offering)
    return {
        "marks": len(marks),
        "scored": sum(1 for mark in marks if mark.score is not None),
        "absence_count": len(absent),
        "absence_hours": sum(mark.lesson.hours for mark in absent),
        "components": ComponentScore.objects.filter(enrollment=enrollment).count(),
        "selfwork": SelfWorkMark.objects.filter(enrollment=enrollment).count(),
        "entry_score": int(gradebook.entry_score_for(enrollment, scheme.entry_score_max)),
        "entry_score_max": int(scheme.entry_score_max),
        "has_final_grade": FinalGrade.objects.filter(enrollment=enrollment).exists(),
    }


def release_block_reason(enrollment) -> str:
    """Mənbə qeydiyyat azad edilə bilməzsə səbəb mətni, ola bilirsə boş sətir."""
    from apps.registrar import gradebook

    if FinalGrade.objects.filter(enrollment=enrollment).exists():
        return pgettext(
            _CTX,
            "Mənbə jurnalda bu tələbənin yekun qiyməti var — birləşmə əvəzinə rəsmi qrup köçürməsi tələb olunur.",
        )
    if gradebook.journal_is_locked(enrollment.offering):
        return pgettext(
            _CTX,
            "Mənbə jurnal bağlanıb — tələbəni ondan azad etmək üçün əvvəlcə RİM jurnalı açmalıdır.",
        )
    return ""


def assert_releasable(enrollment):
    reason = release_block_reason(enrollment)
    if reason:
        raise ValidationError(reason)


def validate_reason(reason) -> str:
    """Birləşmə səbəbi məcburidir (audit izi «boş» qala bilməz)."""
    cleaned = str(reason or "").strip()
    if len(cleaned) < MIN_REASON_LENGTH:
        raise ValidationError(
            pgettext(
                _CTX,
                "Birləşmə üçün səbəb yazılmalıdır (məs.: dekanlıq sərəncamı nömrəsi).",
            )
        )
    return cleaned


def merge_preview(*, offering, student) -> dict:
    """Təsdiqdən ƏVVƏL göstərilən nəticə: hansı jurnaldan, nə qədər iş, aqibəti.

    İstifadəçi «bəli» deməzdən əvvəl rəqəmləri görməlidir — birləşmə tələbənin
    qeydiyyatını dəyişən əməldir.
    """
    conflicts = conflicting_enrollments(offering=offering, student=student)
    if not conflicts:
        return {"conflict": False, "release_required": False, "sources": [], "blocked": ""}
    if len(conflicts) > 1:
        return {
            "conflict": True,
            "release_required": True,
            "sources": [],
            "blocked": pgettext(
                _CTX,
                "Tələbənin bu fənn üzrə birdən çox aktiv jurnalı var — birləşmə avtomatik aparıla bilməz.",
            ),
        }
    source = conflicts[0]
    blocked = release_block_reason(source)
    summary = work_summary(source)
    return {
        "conflict": True,
        "release_required": True,
        "blocked": blocked,
        "sources": [
            {
                "enrollment_id": str(source.pk),
                "group": getattr(source.offering.group, "name", "") or "",
                "subject": source.offering.subject.name,
                **summary,
            }
        ],
    }


# ── Azad etmə / bərpa ────────────────────────────────────────────────────────


def release_source(*, source, target, by_user, reason):
    """Mənbə qeydiyyatı tarixçəyə keçir və hədəf qeydiyyata bağla.

    `dropped` + `superseded_by` — rəsmi qrup köçürməsinin naxışı. Heç nə
    silinmir: bütün bal/davamiyyət sətirləri mənbə qeydiyyatda qalır.
    """
    assert_releasable(source)
    summary = work_summary(source)
    source.status = Enrollment.Status.DROPPED
    source.superseded_by = target
    source.full_clean(validate_unique=False, validate_constraints=False)
    source.save(update_fields=["status", "superseded_by", "updated_at"])
    _audit_merge(
        source=source,
        target=target,
        by_user=by_user,
        reason=reason,
        verb="release",
        summary=summary,
    )
    return summary


def restore_source(*, target, by_user, reason=""):
    """Hədəf sətir geri götürüləndə mənbə qeydiyyatı bərpa et (idempotent).

    Qaytarır: bərpa olunmuş qeydiyyatların sayı.
    """
    restored = 0
    predecessors = list(
        Enrollment.objects.select_for_update(of=("self",))
        .filter(superseded_by=target, status=Enrollment.Status.DROPPED)
        .select_related("offering")
    )
    for source in predecessors:
        source.superseded_by = None
        source.status = Enrollment.Status.ENROLLED
        source.save(update_fields=["status", "superseded_by", "updated_at"])
        _audit_merge(
            source=source,
            target=target,
            by_user=by_user,
            reason=reason,
            verb="restore",
            summary=work_summary(source),
        )
        restored += 1
    return restored


# ── Köçürülən iş (hədəf jurnalda görünür) ────────────────────────────────────


def carry_over_map(target_ids, *, with_entry_score: bool = True) -> dict:
    """``{hədəf_enrollment_id: xülasə}`` — birləşmədən gələn əvvəlki jurnal işi.

    SORĞU BÜDCƏSİ (ölçülmüş, 2026-08-31)
    ────────────────────────────────────
    Sabit hissə: 1 sorğu əvəzlənmiş qeydiyyatlar, 1 sorğu onların işarələri;
    ``with_entry_score=True`` olanda üstəgəl 2 toplu sorğu (mənbə açılışların
    komponent tərifləri + sxem tavanları) → cəmi 4, hədəf sayından ASILI DEYİL.
    ⚠️ Tam-sabit DEYİL: mənbə açılışda komponent TƏRİFİ varsa
    ``gradebook.entry_score_for`` hər mənbə sətri üçün öz ``ComponentScore`` /
    ``SelfWorkMark`` sorğularını edir (növ başına ≤3). Bu, YALNIZ birləşdirilmiş
    qonaq sətirlərinə düşür (qridin adi sətirləri xəritəyə heç girmir), yəni
    xərc qrup ölçüsü ilə deyil, birləşmə sayı ilə (adətən 0–2) böyüyür.
    İSTİ yol bu xərci ÜMUMİYYƏTLƏ ödəmir — bax ``with_entry_score=False``.

    ASİMMETRİYA DÜZƏLİŞİ (2026-08-31 auditi)
    ────────────────────────────────────────
    Əvvəl bu xəritə YALNIZ ziyanı daşıyırdı: qayıb saatı/sayı avtomatik
    köçürülürdü (hədd sayğacına ƏLAVƏ olunurdu), tələbənin əvvəlki jurnalda
    QAZANDIĞI giriş balı isə nə köçürülür, nə də göstərilirdi — o rəqəm yalnız
    təsdiq önbaxışında bir dəfə görünür, sonra audit izinə düşüb yox olurdu.
    Müəllim hədəf jurnalda «bu tələbə əvvəlki jurnalda 18 bal yığmışdı»
    məlumatını heç yerdən ala bilmirdi.

    Balın KÖÇÜRÜLMƏMƏSİ (uydurma xana yaratmamaq üçün) doğru qərardır və
    dəyişmir — dəyişən budur ki, rəqəm indi GÖRÜNÜR: ``entry_score`` +
    ``entry_score_max`` xülasəyə daxildir və qrid sətrində/tooltip-də çıxır.

    ``with_entry_score=False`` — yalnız saat lazım olan İSTİ yol
    (:func:`carried_absence_hours`, hər işarə yazılışında çağırılır): bal
    hesablaması üçün lazım olan komponent/sxem sorğuları edilmir və nəticə
    sözlüyündə ``entry_score``/``entry_score_max`` açarları OLMUR.
    """
    target_ids = [value for value in target_ids if value]
    if not target_ids:
        return {}
    predecessors = list(
        Enrollment.objects.filter(superseded_by_id__in=target_ids, status=Enrollment.Status.DROPPED).select_related(
            "offering", "offering__group"
        )
    )
    if not predecessors:
        return {}
    marks_by_enrollment: dict = {}
    per_enrollment: dict = {}
    marks = LessonMark.objects.filter(enrollment_id__in=[row.pk for row in predecessors]).select_related("lesson")
    for mark in marks:
        marks_by_enrollment.setdefault(mark.enrollment_id, []).append(mark)
        bucket = per_enrollment.setdefault(mark.enrollment_id, {"marks": 0, "scored": 0, "count": 0, "hours": 0})
        bucket["marks"] += 1
        if mark.score is not None:
            bucket["scored"] += 1
        if mark.status == AttendanceStatus.ABSENT:
            bucket["count"] += 1
            bucket["hours"] += mark.lesson.hours

    entry_scores, caps = _source_entry_scores(predecessors, marks_by_enrollment) if with_entry_score else ({}, {})

    result: dict = {}
    for source in predecessors:
        bucket = per_enrollment.get(source.pk, {"marks": 0, "scored": 0, "count": 0, "hours": 0})
        blank = {"absence_hours": 0, "absence_count": 0, "marks": 0, "scored": 0, "groups": [], "enrollment_ids": []}
        if with_entry_score:
            blank.update({"entry_score": 0, "entry_score_max": 0})
        entry = result.setdefault(source.superseded_by_id, blank)
        entry["absence_hours"] += bucket["hours"]
        entry["absence_count"] += bucket["count"]
        entry["marks"] += bucket["marks"]
        entry["scored"] += bucket["scored"]
        if with_entry_score:
            entry["entry_score"] += int(entry_scores.get(source.pk, 0))
            entry["entry_score_max"] += int(caps.get(source.offering_id, DEFAULT_ENTRY_SCORE_MAX))
        group_name = getattr(source.offering.group, "name", "") or ""
        if group_name and group_name not in entry["groups"]:
            entry["groups"].append(group_name)
        entry["enrollment_ids"].append(str(source.pk))
    return result


def _source_entry_scores(predecessors, marks_by_enrollment):
    """``({mənbə_enrollment_id: giriş_balı}, {offering_id: tavan})`` — TOPLU oxu.

    Bal MƏNBƏ jurnalın öz qaydası ilə hesablanır (``gradebook.entry_score_for``
    kanonikdir — burada ikinci düstur yazılmır). Komponent tərifləri və sxem
    tavanları mənbə açılışlar üzrə İKİ sorğu ilə oxunur; işarələr onsuz da
    yaddaşdadır. Sxem YARADILMIR (bu, oxu yoludur) — yoxdursa model defoltu.
    """
    from apps.registrar import gradebook

    offering_ids = {source.offering_id for source in predecessors}
    components: dict = {}
    for component in AssessmentComponent.objects.filter(offering_id__in=offering_ids):
        components.setdefault(component.offering_id, []).append(component)
    caps = dict(
        AssessmentScheme.objects.filter(offering_id__in=offering_ids).values_list("offering_id", "entry_score_max")
    )
    scores = {
        source.pk: gradebook.entry_score_for(
            source,
            caps.get(source.offering_id, DEFAULT_ENTRY_SCORE_MAX),
            marks=marks_by_enrollment.get(source.pk, []),
            components=components.get(source.offering_id, []),
        )
        for source in predecessors
    }
    return scores, caps


def carried_absence_hours(enrollment) -> int:
    """Bu qeydiyyata birləşmə ilə köçürülmüş qayıb saatı (yoxdursa 0).

    Yalnız «alt qrupdan əlavə» sətirləri üçün sorğu edilir — adi sətirlərdə
    əlavə sorğu OLMUR. Bal hesablanmır (``with_entry_score=False``): bu funksiya
    HƏR işarə yazılışında (``recompute_absence_hours``) çağırılır, bal isə
    yalnız görünüş üçündür.
    """
    if getattr(enrollment, "source_group_id", None) is None:
        return 0
    summary = carry_over_map([enrollment.pk], with_entry_score=False).get(enrollment.pk)
    return int(summary["absence_hours"]) if summary else 0


# ── Audit ────────────────────────────────────────────────────────────────────


def _audit_merge(*, source, target, by_user, reason, verb, summary):
    """Birləşmə/bərpa izi — hansı jurnaldan, hansına, hansı iş qalır."""
    student = target.student
    source_group = getattr(source.offering, "group", None)
    log_action(
        action=AuditAction.UPDATE,
        user=by_user,
        organization=target.organization,
        obj=source,
        resource_type="registrar.journal_guest_merge",
        resource_id=str(source.pk),
        resource_repr=f"{(student.get_full_name() or student.username)} · {target.offering.subject.code}",
        old_values={"status": Enrollment.Status.ENROLLED if verb == "release" else Enrollment.Status.DROPPED},
        new_values={"status": source.status},
        changes={
            "verb": verb,
            "student_id": str(student.pk),
            "source_offering_id": str(source.offering_id),
            "source_group": getattr(source_group, "name", "") or "",
            "target_offering_id": str(target.offering_id),
            "target_group": getattr(target.offering.group, "name", "") or "",
            "preserved": {key: str(value) for key, value in summary.items()},
        },
        reason=str(reason or "") or pgettext(_CTX, "Alt qrup birləşməsi — mənbə jurnal qeydiyyatı bərpa olundu."),
    )
