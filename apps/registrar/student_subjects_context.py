"""«Fənlərim» (tələbə kabineti, ekran 10) — bölmə kontekstinin qurulması.

2026-09-12 (tələbə kabineti redizaynı, audit bəndi 7/1). Əvvəl bu məntiq
``apps/registrar/public.py``-də idi və o fayl modul-ölçü büdcəsinə (SOFT_CAP
600) dayanmışdı. İki səbəbdən buraya çıxarıldı:

1. **N+1.** Köhnə döngü hər fənn üçün ``finals.compute_final_result`` (batch-siz
   → ``FinalGrade``/``ResitRecord``/komponent/sərbəst iş/donma/istisna oxumaları),
   ``gradebook.get_component_breakdown`` (2 sorğu) və
   ``exam_attempt_history.attempt_rows_for_enrollment`` (1 sorğu) çağırırdı —
   ölçmə: 1 fənn = 110, 4 fənn = 149 sorğu (səhifə başına), yəni fənn başına
   ~13 sorğu.  İndi hamısı toplu dəstlə (:mod:`apps.registrar.finals_batch`,
   :func:`apps.registrar.exam_attempt_history.attempt_rows_by_subject`,
   ``AssessmentScheme`` tək sorğu) hesablanır — sorğu sayı fənn sayından asılı
   deyil (``test_student_sections_redesign.py`` kilidləyir).

2. **Görünüş məntiqi şablondan çıxır.** Buraxılış vəziyyəti (``ui.status``),
   KPI sırası və legend burada bir dəfə hesablanır; şablon yalnız oxuyur —
   sahib: «tələbə üçün aydın olsun», handoff §7: «status yalnız rənglə deyil,
   mətnlə də verilir».

Riyaziyyat BURADA TƏKRAR YAZILMIR: giriş balı, yekun nəticə, buraxılış qərarı
əvvəlki funksiyalardan (``gradebook`` / ``finals`` / ``exam_eligibility``)
gəlir; yalnız çağırış toplu olub.
"""

from __future__ import annotations

from decimal import Decimal

from django.urls import reverse
from django.utils.translation import pgettext_lazy

from apps.registrar import (
    exam_attempt_history,
    finals,
    finals_batch,
    gradebook,
    interim_assessment,
    selfwork_points,
    services,
)
from apps.registrar.cabinet_policy import (
    approved_syllabus_offerings,
    assessment_weights_view,
    other_period_subject_rows,
)
from apps.registrar.models import AssessmentScheme, ComponentKind

#: «Limitə yaxın» həddi — icazəli qayıbın 75%-i.  Jurnalın xəbərdarlıq siyahısı
#: (:func:`apps.registrar.student_journal_context.warnings_for`) ilə EYNİ hədd:
#: iki səth bir tələbəyə fərqli rəng göstərməsin.
NEAR_LIMIT_RATIO = Decimal("0.75")

_CTX = "profile.subjects"


def _dec(value) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except (ArithmeticError, TypeError, ValueError):
        return Decimal("0")


def eligibility_status(eligibility) -> str:
    """``exam_eligibility.resolve`` nəticəsi → ``exam_eligibility`` status ailəsinin açarı.

    Sıra vacibdir: donmuş semestr həmişə «frozen» (orada ``barred`` onsuz da
    susdurulub); sonra qadağa; sonra 75% yaxınlıq; məxrəc yoxdursa «unknown» —
    əvvəl bu hal da «buraxılır» kimi görünürdü, halbuki hədd hesablana bilmir
    (``UNKNOWN_HOURS_NOTICE``).
    """
    if not eligibility:
        return "unknown"
    if eligibility.get("frozen"):
        return "frozen"
    if eligibility.get("barred"):
        return "barred"
    if not eligibility.get("hours_known", True):
        return "unknown"
    allowed = _dec(eligibility.get("allowed_hours"))
    if allowed > 0 and _dec(eligibility.get("absence_hours")) >= allowed * NEAR_LIMIT_RATIO:
        return "near"
    return "ok"


def _scheme_map(offerings) -> dict:
    """``offering_id`` → ``AssessmentScheme`` — TƏK sorğu; olmayanlar yaradılır.

    ``other_period_subject_rows`` sətirləri ``assessment_scheme``-i select_related
    etmir → ``compute_final_result`` hər açılış üçün əks-O2O sorğusu edərdi.
    Sxem yoxdursa ``ensure_assessment_scheme`` (get_or_create) — nadir hal,
    davranış əvvəlki ilə eynidir.
    """
    ids = [o.id for o in offerings if o is not None]
    found = {s.offering_id: s for s in AssessmentScheme.objects.filter(offering_id__in=ids)} if ids else {}
    for offering in offerings:
        if offering is not None and offering.id not in found:
            found[offering.id] = gradebook.ensure_assessment_scheme(offering=offering)
    return found


def _component_breakdown(batch, enrollment, *, midterm=False, selfwork_slots=None) -> list:
    """``gradebook.get_component_breakdown``-un toplu güzgüsü (eyni forma, sorğusuz).

    ``midterm`` (2026/2027-dən): köhnə kodun bu dövrdə yaratdığı BALSIZ «Kollokvium N»
    qalıqları çip kimi göstərilmir — tələbə yalnız «Midterm …/20» görür.

    SƏRBƏST İŞ çipi (2026-09-25): giriş balına DÜŞƏN bal (``selfwork_points`` cəmi,
    komponent tavanı ilə — ``entry_score_for`` güzgüsü); canlı bal yoxdursa köçürülmüş
    «arxiv» balı (``selfwork_board.effective_total`` qaydası). ``slots`` — slot-slot
    bal («Sərbəst iş 1: 4/5»), ``selfwork_slots`` batch-in eyni sorğusundan gəlir."""
    components = sorted(batch.components_by_offering.get(enrollment.offering_id, []), key=lambda c: (c.order, c.name))
    if not components:
        return []
    score_by = {cs.component_id: cs.score for cs in batch.scores_by_enrollment.get(enrollment.id, [])}
    if midterm:
        keep = interim_assessment.MIDTERM_COMPONENT_NAME.lower()
        components = [
            c
            for c in components
            if c.kind != ComponentKind.KOLLOKVIUM or c.name.strip().lower() == keep or score_by.get(c.id) is not None
        ]
    chips = []
    for c in components:
        chip = {"name": c.name, "score": score_by.get(c.id), "max": c.max_score}
        if c.kind == ComponentKind.SELF_WORK:
            live = min(
                Decimal(batch.selfwork_points.get((enrollment.id, enrollment.offering_id), 0)), Decimal(c.max_score)
            )
            chip["score"] = live if live else score_by.get(c.id)
            chip["slots"] = (selfwork_slots or {}).get(enrollment.id, [])
        chips.append(chip)
    return chips


def _is_midterm_row(enrollment, period, organization) -> bool:
    """Sətrin dövrü midterm rejimindədirmi — əlavə sorğusuz (dövr ya keşdədir, ya bölmənin dövrüdür;
    təşkilat çağırandan gəlir — ``offering.organization`` FK-sı sətir başına sorğu edərdi)."""
    offering = enrollment.offering
    cached = offering._state.fields_cache.get("period")
    if cached is None and period is not None and offering.period_id == period.id:
        cached = period
    if cached is None:
        return False  # bilinməyən dövr üçün sorğu etmirik — köhnə forma (bütün komponentlər) qalır
    return interim_assessment.mode_for_period(cached, organization=organization) == interim_assessment.MODE_MIDTERM


def enrich_subject_rows(*, organization, record, rows, journal_by_enrollment, period=None) -> None:
    """Hər fənn sətrinə jurnal xülasəsi, yekun nəticə, komponentlər, cəhdlər,
    sillabus keçidləri və görünüş açarlarını (``ui``) əlavə edir — yerində."""
    enrollments = [row["enrollment"] for row in rows]
    offerings = [row["enrollment"].offering for row in rows]
    schemes = _scheme_map(offerings)
    # Sərbəst iş cəmi + slot-slot bal TƏK sorğuda (batch-in öz aqreqatını ƏVƏZ edir — sorğu sayı dəyişmir).
    selfwork_slots: dict = {}

    def _selfwork_loader(enrollment_ids, offering_ids):
        slots, totals = selfwork_points.selfwork_slots(enrollments, offering_ids)
        selfwork_slots.update(slots)
        return totals

    batch = finals_batch.build(enrollments, selfwork_loader=_selfwork_loader, organization=organization, period=period)
    approved_ids = approved_syllabus_offerings(organization, offerings)
    attempts_by_subject = exam_attempt_history.attempt_rows_by_subject(
        student=record.student,
        subject_ids={o.subject_id for o in offerings},
        organization=organization,
    )
    for row in rows:
        enrollment = row["enrollment"]
        offering = enrollment.offering
        row["syllabus_available"] = offering.id in approved_ids
        row["syllabus_url"] = (
            reverse("registrar:offering_syllabus_json", args=[offering.id]) if offering.id in approved_ids else ""
        )
        row["syllabus_pdf_url"] = (
            reverse("registrar:offering_syllabus_pdf", args=[offering.id]) if offering.id in approved_ids else ""
        )
        row["journal"] = journal_by_enrollment.get(enrollment.id)
        row["final"] = finals.compute_final_result(
            enrollment=enrollment, scheme=schemes.get(offering.id), organization=organization, batch=batch
        )
        row["components"] = _component_breakdown(
            batch,
            enrollment,
            midterm=_is_midterm_row(enrollment, period, organization),
            selfwork_slots=selfwork_slots,
        )
        row["attempts"] = attempts_by_subject.get(offering.subject_id, [])
        row["ui"] = {"status": eligibility_status(row.get("eligibility"))}


def kpi_summary(rows) -> dict:
    """KPI sırası — prototip (ekran 10 «Cari semestr»): toplanmış bal (orta),
    semestr krediti, buraxılmayan fənn, yekunlaşan fənn."""
    subject_count = len(rows)
    ects_total = sum(int(row.get("ects") or 0) for row in rows)
    entries = [row["journal"] for row in rows if row.get("journal")]
    entry_avg = None
    entry_cap = None
    if entries:
        entry_avg = (sum(_dec(j["entry_score"]) for j in entries) / len(entries)).quantize(Decimal("0.1"))
        caps = {int(j["entry_score_max"] or 0) for j in entries}
        entry_cap = caps.pop() if len(caps) == 1 else None
    statuses = [row.get("ui", {}).get("status", "unknown") for row in rows]
    finals_rows = [row.get("final") or {} for row in rows]
    graded = [f for f in finals_rows if f.get("graded")]
    return {
        "subject_count": subject_count,
        "ects_total": ects_total,
        "entry_avg": entry_avg,
        "entry_cap": entry_cap,
        "barred_count": statuses.count("barred"),
        "near_count": statuses.count("near"),
        "frozen_count": statuses.count("frozen"),
        "graded_count": len(graded),
        "passed_count": sum(1 for f in graded if f.get("passed")),
        "failed_count": sum(1 for f in finals_rows if f.get("failed")),
    }


def fmt_score(value) -> str:
    """Decimal balı tələbə üçün qısa yazır: 38.50 → «38.5», 40.00 → «40»."""
    if value is None:
        return "—"
    text = f"{_dec(value):.2f}".rstrip("0").rstrip(".")
    return text or "0"


def kpi_tiles(kpis: dict) -> list:
    """`partials/ems_ui/_kpi_row.html` üçün kart siyahısı (prototip ekran 10).

    Ton MƏNA daşıyır: buraxılmayan fənn varsa qırmızı, limitə yaxın varsa sarı,
    hamısı qaydasındadırsa yaşıl — və hər halda mətn də eyni şeyi deyir.
    """
    n = kpis["subject_count"]
    entry_note = (
        pgettext_lazy(_CTX, "yekun imtahanın balı hələ əlavə olunmayıb")
        if not kpis["graded_count"]
        else pgettext_lazy(_CTX, "imtahana qədər toplanan bal (orta)")
    )
    if kpis["barred_count"]:
        elig_tone, elig_note = "danger", pgettext_lazy(_CTX, "qayıb həddi keçilib — dekanlığa müraciət edin")
    elif kpis["near_count"]:
        elig_tone = "warning"
        elig_note = pgettext_lazy(_CTX, "%(count)s fənn limitə yaxındır — davamiyyətə diqqət") % {
            "count": kpis["near_count"]
        }
    else:
        elig_tone, elig_note = "success", pgettext_lazy(_CTX, "bütün fənlərdə imtahana buraxılırsınız")
    if kpis["graded_count"]:
        final_note = pgettext_lazy(_CTX, "keçdi %(passed)s · kəsildi %(failed)s") % {
            "passed": kpis["passed_count"],
            "failed": kpis["failed_count"],
        }
    else:
        final_note = pgettext_lazy(_CTX, "hələ yekun imtahan nəticəsi yoxdur")
    return [
        {
            "label": pgettext_lazy(_CTX, "Toplanmış bal (orta)"),
            "value": fmt_score(kpis["entry_avg"]),
            "unit": f"/ {kpis['entry_cap']}" if kpis["entry_avg"] is not None and kpis["entry_cap"] else "",
            "note": entry_note,
            "tone": "primary",
        },
        {
            "label": pgettext_lazy(_CTX, "Semestr krediti"),
            "value": kpis["ects_total"],
            "unit": "ECTS",
            "note": pgettext_lazy(_CTX, "%(count)s fənn") % {"count": n},
        },
        {
            "label": pgettext_lazy(_CTX, "İmtahana buraxılmayan"),
            "value": kpis["barred_count"],
            "unit": f"/ {n}",
            "note": elig_note,
            "tone": f"accent-{elig_tone}",
        },
        {
            "label": pgettext_lazy(_CTX, "Yekun nəticə"),
            "value": kpis["graded_count"],
            "unit": f"/ {n}",
            "note": final_note,
        },
    ]


#: Legend — rəng semantikası MƏTNlə (handoff §7). Açar `exam_eligibility` ailəsi
#: ilə eynidir; şablon badge-i `{% ems_status_badge %}` ilə, izahı buradan verir.
LEGEND = (
    {"status": "ok", "hint": pgettext_lazy(_CTX, "qayıb icazəli həddin altındadır")},
    {"status": "near", "hint": pgettext_lazy(_CTX, "icazəli qayıbın 75%-i keçilib — diqqət")},
    {"status": "barred", "hint": pgettext_lazy(_CTX, "qayıb həddi keçilib, yekun imtahana giriş yoxdur")},
    {
        "status": "frozen",
        "hint": pgettext_lazy(
            _CTX, "köhnə sistemdən köçürülmüş, bağlı semestr — status yenidən hesablanmır, faktiki nəticə göstərilir"
        ),
    },
)


def build_section(*, request, organization, record, period, semester_number) -> dict:
    """Akademik qeydi və dövrü artıq həll olunmuş tələbə üçün bölmənin qalan hissəsi.

    ``public.build_student_subjects_context`` boş hal / qeyd yoxdur / dövr yoxdur
    budaqlarını özü verir və yalnız DOLU halda buranı çağırır.  Qaytarılan dict
    bölmə lüğətinə (``student_subjects_section``) ``update`` olunur — açarlar
    əvvəlki ilə eynidir (mövcud testlər + şablon), yeniləri: ``kpis``, ``legend``,
    hər sətirdə ``ui``.
    """
    data = services.get_student_cabinet_data(record=record, period=period, semester_number=semester_number)
    data["subjects"] += other_period_subject_rows(organization, record, period, semester_number, data["subjects"])

    # Hər fənnin elektron jurnal xülasəsi (giriş balı + davamiyyət) — «Fənlərim»
    # eyni zamanda tələbənin «Qiymətlərim» görünüşüdür.
    journal_summary = gradebook.get_student_journal_summary(
        record=record, period=period, semester_number=semester_number
    )
    journal_by_enrollment = {row["enrollment"].id: row["journal"] for row in journal_summary["subjects"]}
    enrich_subject_rows(
        organization=organization,
        record=record,
        rows=data["subjects"],
        journal_by_enrollment=journal_by_enrollment,
        period=period,
    )

    group_decisions = data["group_decisions"]
    elective_blocks = [
        {
            "name": name,
            "required_choices": block["required_choices"],
            "options": block["options"],
            "chosen": group_decisions.get(name),
        }
        for name, block in data["elective_blocks"].items()
    ]
    kpis = kpi_summary(data["subjects"])
    return {
        "period": period,
        "semester_number": semester_number,
        "subjects": data["subjects"],
        "elective_blocks": elective_blocks,
        "group_decisions": group_decisions,
        "credit_summary": data["credit_summary"],
        # Qiymətləndirmə çəkiləri — universitet SİYASƏTİ ilə kilidli (README §8/4:
        # davamiyyət 10 · sərbəst iş 10 · cari 30 · yekun 50). Kodda hardcode YOX.
        "assessment_weights": assessment_weights_view(organization),
        "kpis": kpis,
        "kpi_tiles": kpi_tiles(kpis) if data["subjects"] else [],
        "legend": LEGEND,
    }
