"""Plan → qrup açılışı QAYDALARI — saf funksiyalar (baza yoxdur, 2026-09-25).

Sahibin tələbi (2026-09-25): «tədris şöbəsi planı kafedralara göndərəndə fənn
avtomatik qruplara düşsün; yeni müəllim təyin olunanda o da əlavə olunsun — hələ
ondan əvvəl fənn orada olsun» (cədvəlin avtomatlaşdırılması üçün).
:mod:`.offering_sync` bu qaydaları TƏTBİQ edir; burada yalnız qərar var.

1. NƏ VAXT AÇILIŞ YARANIR (:func:`plan_reached_chair`)
   Plan kafedraya dekanlıq təsdiqi ilə çatır (``recompute_task_status`` →
   ``approved``) — o andan sənədin HƏR sətri üçün (fənn × semestr × qrup) açılış
   olmalıdır. ``distributed``/``amended`` (bölgü təsdiqlənib — hər iki yol) da
   «çatıb» sayılır. Kafedranın ÖZ köhnə qaralaması (F1-dən əvvəlki yol, heç vaxt
   göndərilməyib) istisnadır: təsdiq hadisəsi yoxdur, açılış əvvəlki kimi
   ``confirm_distribution``-da yaranır (``sync_plan_offerings --include-drafts``
   ilə əvvəlcədən də yaratmaq olar).

2. SAAT (:func:`per_group_hours`)
   ``CourseOffering.lesson_hours`` QRUP başına kontakt saatıdır (qayıb limitinin
   məxrəci): fəaliyyət üzrə ``*_plan``; plan boşdursa ``*_total ÷ çarpan``
   (mühazirə — ``union_count``, seminar/lab — ``subgroup_count``). Əvvəl
   ``Σ *_total`` yazılırdı — birləşmə/yarımqrup çarpanı ilə ŞİŞİRDİLMİŞ saat.
   Eyni açılışa bir neçə sətir (həm də BAŞQA kafedranın sənədindən) düşərsə
   fəaliyyət üzrə MAKSİMUM götürülür — mühazirə bir sətirdə, lab digərində ola
   bilər, dublikat ikiqat sayılmır və nəticə sinxron sırasından asılı olmur.

3. JURNAL SAHİBİ (:func:`journal_owner`) — spec §11.3: MÜHAZİRƏÇİ, yoxdursa ilk
   vakant-olmayan təyinat.

4. MÜƏLLİM PROVENANSI (:func:`decide_instructor`)
   Dərs yükü açılışın müəllimini YALNIZ öz yazdığı dəyərin üstünə yazır:
   * açılış müəllimsizdirsə → yük sahibi (bal yaza bilirsə — ``grade.input``,
     ``registrar_guard_active_member``) yazılır;
   * müəllim yükün ƏVVƏLKİ sahibidirsə (``assign_teacher``/``unassign`` dəyişiklikdən
     əvvəlki anı ``previous`` kimi verir) → yeni sahib yazılır; yeni sahib
     vakantdırsa və ya bal yaza bilmirsə → BOŞ qalır (+ hesabat);
   * müəllim «Fənn təhvili» ilə gəlibsə (ləğv olunmamış ``TeachingHandover``,
     ``to_instructor`` = cari) → TOXUNULMUR (``preserved_handover``);
   * başqa hər hansı müəllim (cədvəl redaktoru, admin forması) → TOXUNULMUR
     (``preserved_foreign``). Təsdiq/bölgü-təsdiqi keçidlərində ``previous``
     bilinmir (:data:`UNKNOWN`), ona görə orada fərqli müəllim HEÇ VAXT əzilmir.
   Provenans ayrıca sütunsuz saxlanılır: təhvil jurnalı + dəyişiklik anındakı
   əvvəlki yük sahibi kifayətdir; hər yazı ``workload.offering_instructor_synced``
   audit qeydi buraxır.
"""

from __future__ import annotations

from ..constants import Activity, TaskStatus

#: «Əvvəlki yük sahibi məlum deyil» — təsdiq / bölgü-təsdiqi / backfill keçidləri.
UNKNOWN = object()

#: Fəaliyyət → (plan sahəsi, cəm sahəsi, çarpan sahəsi).
HOUR_FIELDS = {
    "lecture": ("lecture_plan", "lecture_total", "union_count"),
    "seminar": ("seminar_plan", "seminar_total", "subgroup_count"),
    "lab": ("lab_plan", "lab_total", "subgroup_count"),
}

#: Müəllim qərarının nəticələri → hesabat sayğacları.
OUTCOME_COUNTERS = {
    "set": ("instructor_set",),
    "replaced": ("instructor_replaced",),
    "cleared": ("instructor_cleared",),
    "cleared_blocked": ("instructor_cleared", "instructor_blocked"),
    "blocked": ("instructor_blocked",),
    "preserved_handover": ("preserved_handover",),
    "preserved_foreign": ("preserved_foreign",),
    "keep": (),
}


def plan_reached_chair(task) -> bool:
    """Plan kafedraya çatıbmı — sətirlərin qrup açılışları YARADILA bilər (bax başlıq §1)."""
    status = task.status
    if status in (TaskStatus.APPROVED, TaskStatus.DISTRIBUTED, TaskStatus.AMENDED):
        return True
    return status == TaskStatus.DISTRIBUTING and task.submitted_at is not None


def per_group_hours(row) -> dict:
    """Bir qrupun fəaliyyət üzrə semestr saatı (bax başlıq §2)."""
    hours = {}
    for activity, (plan_field, total_field, multiplier_field) in HOUR_FIELDS.items():
        plan = int(getattr(row, plan_field, 0) or 0)
        if not plan:
            total = int(getattr(row, total_field, 0) or 0)
            plan = total // max(int(getattr(row, multiplier_field, 1) or 1), 1)
        hours[activity] = plan
    return hours


def merge_hours(rows) -> dict:
    """Eyni açılışa düşən sətirlərin saatı — fəaliyyət üzrə maksimum."""
    merged = {activity: 0 for activity in HOUR_FIELDS}
    for row in rows:
        for activity, value in per_group_hours(row).items():
            merged[activity] = max(merged[activity], value)
    return merged


def journal_owner(assignments):
    """``(müəllim, mühazirədəndirmi)`` — MÜHAZİRƏÇİ, yoxdursa ilk vakant-olmayan təyinat.

    ``assignments`` fəaliyyət + yaradılma sırası ilə gəlməlidir
    (``offering_sync.assignments_prefetch``).
    """
    assignments = [a for a in assignments if a.teacher_id]
    for assignment in assignments:
        if assignment.activity == Activity.LECTURE:
            return assignment.teacher, True
    return (assignments[0].teacher, False) if assignments else (None, False)


def owner_for_rows(rows):
    """Eyni açılışı paylaşan sətirlərdən jurnal sahibi — mühazirə təyinatı üstündür."""
    fallback = None
    for row in rows:
        teacher, from_lecture = journal_owner(row.assignments.all())
        if teacher is not None and from_lecture:
            return teacher
        fallback = fallback or teacher
    return fallback


def decide_instructor(current_id, *, desired_id, eligible: bool, previous_id=UNKNOWN, handover_owned=False):
    """``(nəticə, yeni_müəllim_id)`` — bax başlıq §4. Baza oxunmur, yazılmır."""
    target = desired_id if (desired_id is not None and eligible) else None
    if current_id is None:
        if target is not None:
            return "set", target
        return ("blocked", None) if desired_id is not None else ("keep", None)
    if current_id == desired_id:
        return "keep", current_id
    if handover_owned:
        return ("preserved_handover" if desired_id is not None else "keep"), current_id
    if previous_id is not UNKNOWN and current_id == previous_id:
        if target is not None:
            return "replaced", target
        return ("cleared_blocked", None) if desired_id is not None else ("cleared", None)
    # Yükün müəllimi yoxdursa (vakant/bölünməyib) münaqişə yoxdur — mövcud müəllim qalır.
    return ("preserved_foreign" if desired_id is not None else "keep"), current_id


__all__ = [
    "HOUR_FIELDS",
    "OUTCOME_COUNTERS",
    "UNKNOWN",
    "decide_instructor",
    "journal_owner",
    "merge_hours",
    "owner_for_rows",
    "per_group_hours",
    "plan_reached_chair",
]
