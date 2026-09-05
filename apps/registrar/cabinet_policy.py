"""Tələbə kabineti (ekran 10) — sillabus və qiymətləndirmə köməkçiləri.

``apps/registrar/public.py`` modul-ölçü büdcəsinə (SOFT_CAP=600) dayandığı üçün
bu iki SAF köməkçi ayrıca modula çıxarıldı. Davranış eynidir.

* :func:`approved_syllabus_offerings` — «Sillabusa bax» keçidi üçün TOPLU
  (N+1-siz) yoxlama; README §8/9: YALNIZ ``APPROVED`` versiya sayılır;
* :func:`transcript_policy` — README §10.1 (`transcriptPolicy`); default
  ``request`` → kabinetdə PDF yox, «Transkript sorğusu» müraciətinə CTA;
* :func:`assessment_weights_view` — README §8/4-ün kilidli çəkiləri
  (davamiyyət 10 · sərbəst iş 10 · cari 30 · yekun 50); dəyərlər KODDA
  hardcode DEYİL, ``apps.syllabus.policy``-dən (org səviyyəsi) oxunur.
"""

from __future__ import annotations

from django.urls import reverse

#: «Transkript sorğusu» müraciət növünün kodu (``apps.applications.constants``).
TRANSCRIPT_APPLICATION_KIND = "transkript"


def transcript_policy(*, self_service: bool) -> dict:
    """Transkript bölməsinin siyasət açarları (README §10.1).

    ``self_service`` bağlı ikən kabinetdə «PDF yüklə» GÖSTƏRİLMİR (endpoint
    onsuz da 404 verirdi — düymə görünür, klik 404 idi); əvəzinə «Transkript
    sorğusu» növü ÖNCƏDƏN SEÇİLMİŞ halda Müraciətlər panelində açılır
    (Tələbə Xidmətləri Mərkəzi, SLA 3 iş günü). Sahib ``download``-a keçmək
    istəsə YALNIZ bayraq dəyişir — yeni UI lazım deyil.
    """
    return {
        "self_service": bool(self_service),
        "request_url": "%s?section=applications&new_kind=%s"
        % (reverse("accounts:profile"), TRANSCRIPT_APPLICATION_KIND),
    }


def approved_syllabus_offerings(organization, offerings) -> set:
    """Təsdiqlənmiş sillabusu OLAN açılışların id dəsti — TƏK sorğu.

    Ekran 10 (tələbə kabineti) fənn kartlarında «Sillabusa bax» keçidi
    göstərir; sətir-sətir ``_student_syllabus_available`` çağırmaq hər fənn
    üçün 2–3 sorğu deməkdir (N+1). Burada dosye axtarışının İLK İKİ pilləsi
    (offering üzrə, sonra subject+period üzrə) toplu şəkildə həll olunur;
    üçüncü (semestrsiz legacy) pillə kabinet kartında QƏSDƏN axtarılmır — o,
    jurnalın öz banneri üçündür.

    README §8/9: yalnız ``APPROVED`` versiya sayılır.
    """
    from django.db.models import Q

    from apps.syllabus.constants import SyllabusStatus
    from apps.syllabus.models import Syllabus

    offerings = [offering for offering in offerings if offering is not None]
    if organization is None or not offerings:
        return set()
    offering_ids = {offering.id for offering in offerings}
    subject_ids = {offering.subject_id for offering in offerings}
    rows = (
        Syllabus.objects.filter(organization=organization, is_active=True)
        .filter(Q(offering_id__in=offering_ids) | Q(offering__isnull=True, subject_id__in=subject_ids))
        .values_list("offering_id", "subject_id", "period_id", "approved_version__status")
    )
    by_offering: set = set()
    by_subject_period: set = set()
    for offering_id, subject_id, period_id, status in rows:
        if status != SyllabusStatus.APPROVED.value:
            continue
        if offering_id is not None:
            by_offering.add(offering_id)
        else:
            by_subject_period.add((subject_id, period_id))
    return {
        offering.id
        for offering in offerings
        if offering.id in by_offering or (offering.subject_id, offering.period_id) in by_subject_period
    }


def other_period_subject_rows(organization, record, period, semester_number, existing_rows):
    """Digər (CARİ olmayan) dövrlərdəki SİLİNMƏMİŞ qeydiyyatların fənn sətirləri.

    QA 2026-09-05 (P3-16 / SYLLABUS-07): «Fənlərim» yalnız cari dövrü göstərir
    — tələbənin paralel bir sessiyada (məs. Yay) aktiv qeydiyyatı olan fənn
    siyahıya heç düşmürdü, deməli «Sillabusa bax» keçidi də əlçatmaz idi.
    ``existing_rows`` — çağıranın ARTIQ yığdığı (əsas dövrün) sətirləri; onların
    ``enrollment`` id-ləri təkrar qaytarılmır. Qaytarılan sətirlər
    ``services.get_student_cabinet_data``-nın "subjects" formasındadır ki,
    çağıran tərəf onları elə eyni siyahıya əlavə etsin — aşağıdakı toplu
    syllabus/journal zənginləşdirməsi onları da əhatə edir. Tam period
    seçicisi (SYLLABUS-07-in özü) ayrıca (bahalı) qərardır.
    """
    from django.apps import apps as django_apps

    from apps.registrar import services
    from apps.registrar.models import Enrollment

    other_period_ids = (
        Enrollment.objects.filter(organization=organization, student=record.student)
        .exclude(offering__period_id=period.id)
        .exclude(status=Enrollment.Status.DROPPED)
        .values_list("offering__period_id", flat=True)
        .distinct()
    )
    if not other_period_ids:
        return []
    AcademicPeriod = django_apps.get_model("organizations", "AcademicPeriod")
    seen = {row["enrollment"].id for row in existing_rows}
    rows = []
    for other_period in AcademicPeriod.objects.filter(organization=organization, id__in=list(other_period_ids)):
        extra = services.get_student_cabinet_data(record=record, period=other_period, semester_number=semester_number)
        for row in extra["subjects"]:
            if row["enrollment"].id not in seen:
                seen.add(row["enrollment"].id)
                rows.append(row)
    return rows


def assessment_weights_view(organization) -> dict:
    """Qiymətləndirmə çəkiləri (10/10/30/50) — ekran 10-un «struktur» zolağı."""
    from apps.syllabus.policy import assessment_weights

    weights = assessment_weights(organization)
    return {
        "attendance": weights["attendance"],
        "selfwork": weights["selfwork"],
        "current": weights["flex"],
        "final": weights["final"],
        "total": weights["attendance"] + weights["selfwork"] + weights["flex"] + weights["final"],
    }


__all__ = [
    "TRANSCRIPT_APPLICATION_KIND",
    "approved_syllabus_offerings",
    "assessment_weights_view",
    "other_period_subject_rows",
    "transcript_policy",
]
