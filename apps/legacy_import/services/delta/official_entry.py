"""Faza ``official_entry`` (SYS-1, 2026-11-03) — tarixi giriş balını köhnə sistemin RƏSMİ bal vərəqinə bərabərləşdirir.

Paket: ``legacy_delta_extract --official-entry 7-13`` (``official_entry_extract.py``); hədəf qaydası
``official_entry_sheets.target_entry``-dədir (orada əsaslandırma var).

Nə yazır
--------
YALNIZ J5b-nin öz arxiv komponentinin xanasını (``Davamiyyət və sərbəst iş (arxiv)``, ``generic``) — köçürmənin
düsturla BƏRPA etdiyi dəyəri. Registrar tərəfi (kanonik giriş, yaddaşda yoxlama, yazı, audit)
``registrar.public.align_archive_entries``-dədir (``apps/registrar/legacy_entry_alignment.py``); bu faza yalnız
paketi yazılışlara açır və sayları/adları toplayır.

Nəyə toxunmur
-------------
* müəllimin / düzəliş alətinin yazdığı xanaya (``entered_by`` doludur) — «edited_kept»;
* kollokvium, sərbəst iş, gündəlik xanalar, imtahan / təkrar imtahan balları — heç vaxt;
* dil səviyyə kursları və Midterm rejimli (2026/2027+) açılışlar, arxiv komponenti olmayan açılışlar;
* bir tələbəyə iki fərqli rəsmi dəyər düşürsə və ya vərəq ailəsi iki fərqli yazılışa açılırsa — heç biri.

Hər dəyişiklik açılış başına bir ``grade_audit`` sətrinə (``registrar.grade.component``, köhnə → yeni) düşür —
jurnalın «dəyişiklik tarixçəsi»ndə görünür və geri qaytarma üçün kifayətdir. İkinci qaçış 0 yazı verir.
Hesabat: ``official_entry.*`` sayları (semestr üzrə də) və keçid/kəsr dəyişən tələbələrin sayı; adlar yalnız
``--names-out`` faylına.
"""

from __future__ import annotations

from decimal import Decimal

from .history import HistoryPhaseMismatch
from .official_entry_extract import PHASE
from .official_entry_sheets import official_finals, target_entry

ARCHIVE_COMPONENT_NAME = "Davamiyyət və sərbəst iş (arxiv)"  # J5b ``ARCHIVE_COMPONENT_NAME`` güzgüsü
ARCHIVE_COMPONENT_KIND = "generic"
FLIPS = ("fail_to_pass", "pass_to_fail", "open_to_pass", "open_to_fail")


class OfficialEntryPhaseMismatch(HistoryPhaseMismatch):
    """Rəsmi giriş paketi yalnız ``official_entry`` fazası ilə işlədilir."""


def check_phases(bundle: dict, phases) -> None:
    if (bundle.get("snapshot") or {}).get("official_entry") is not None and set(phases) - {PHASE}:
        raise OfficialEntryPhaseMismatch("legacy_delta_official_entry_bundle_phase_mismatch")


def _outcome(result) -> str:
    if result["passed"]:
        return "pass"
    if result["failed"]:
        return "fail"
    return "open"


def resolve_targets(run, rows) -> dict:
    """Paket sətirləri → ``{pk: (enrollment, hədəf, mənbə, semestr, vərəq id, rəsmi yekun, sətir)}``; imtinalar sayılır.

    Rəsmi yekun yalnız hədəf yekundan çıxarılıbsa (``source == "total"``) ötürülür — yeni yekun ona bərabər olmalıdır.
    Bir yazılışa iki vərəq düşürsə (məs. bölünmüş jurnalın mühazirə hissəsinin imtahandan əvvəlki vərəqi + yekunlu
    vərəq) Yekun-u olan qalib gəlir; ikisi də yekunludursa və fərqlidirsə — ziddiyyət, heç biri yazılmır.
    """

    keys = {(uniqid, int(row["student_id"])) for row in rows for uniqid in row.get("journals") or ()}
    ledger = run.ledger_enrollments(keys)
    wanted: dict = {}
    clashing: set = set()
    for row in rows:
        semester = int(row.get("semestr") or 0)
        prefix = f"official_entry.sem{semester}"
        value, source = target_entry(row)
        if value is None and not _qb_fail(row):
            run.count(f"{prefix}.skip_{source}")
            continue
        found = {}
        for uniqid in row.get("journals") or ():
            enrollment = ledger.get((uniqid, int(row["student_id"])))
            if enrollment is not None:
                found[enrollment.pk] = enrollment
        if len(found) != 1:
            run.count(f"{prefix}.skip_enrollment_{'unresolved' if not found else 'ambiguous'}")
            continue
        ((pk, enrollment),) = found.items()
        total = _official_total(row) if source == "total" else None
        previous = wanted.get(pk)
        if previous is not None and previous[1] != value:
            if previous[5] is not None and total is None:
                continue  # yekunlu vərəq artıq seçilib
            if not (previous[5] is None and total is not None):
                clashing.add(pk)
        wanted[pk] = (enrollment, value, source, semester, row.get("export_id"), total, row)
    for pk in clashing:
        run.count(f"official_entry.sem{wanted.pop(pk)[3]}.skip_target_conflict")
    return wanted


def copied_attempts(organization, wanted) -> set:
    """Başqa cəhdin nəticəsi çap olunmuş vərəqlər → toxunulmayacaq yazılışların pk-ları.

    Köhnə sistem fənni təkrar keçən tələbənin yeni jurnal vərəqində ƏVVƏLKİ cəhdin nəticəsini çap edirdi
    (34 / 2 / 17 / 51 hər iki semestrdə). Yeni sistemdə həmin tələbənin eyni fənnə (eyni kart və ya eyni ad) BAŞQA
    yazılışında vərəqdəki imtahan (və 25 % balı) artıq varsa, bu yazılışın özündə isə imtahan YOXDURSA — vərəq o
    cəhdindir: bu yazılışa nə imtahan doldurulur, nə giriş balı dəyişir.
    """

    from django.apps import apps as django_apps

    from .resolve import subject_key

    Enrollment = django_apps.get_model("registrar", "Enrollment")
    FinalGrade = django_apps.get_model("registrar", "FinalGrade")
    ResitRecord = django_apps.get_model("registrar", "ResitRecord")
    sheet = {}
    for pk, (_enrollment, _value, source, _semester, _export, _total, row) in wanted.items():
        exam, resit = official_finals(row) if source == "total" else (None, None)
        if exam is not None or resit is not None:
            sheet[pk] = (exam, resit)
    if not sheet:
        return set()
    targets = {
        e.pk: e
        for e in Enrollment.objects.filter(organization=organization, pk__in=list(sheet)).select_related(
            "offering__subject"
        )
    }
    students = {e.student_id for e in targets.values()}
    others = list(
        Enrollment.objects.filter(organization=organization, student_id__in=students)
        .exclude(status="dropped")
        .select_related("offering__subject")
        .only("pk", "student_id", "offering__period_id", "offering__subject_id", "offering__subject__name")
    )
    ids = [e.pk for e in others]
    exams = dict(
        FinalGrade.objects.filter(enrollment_id__in=ids, exam_score__isnull=False).values_list(
            "enrollment_id", "exam_score"
        )
    )
    resits = dict(
        ResitRecord.objects.filter(enrollment_id__in=ids, resit_score__isnull=False).values_list(
            "enrollment_id", "resit_score"
        )
    )
    attempts: dict = {}
    for e in others:
        for key in (("id", e.offering.subject_id), ("name", subject_key(e.offering.subject.name))):
            attempts.setdefault((e.student_id, key), []).append(e)
    skipped = set()
    for pk, (exam, resit) in sheet.items():
        target = targets.get(pk)
        if target is None:
            continue
        if exams.get(target.pk) is not None:
            continue  # öz imtahanı var — yekun yoxlaması (``skip_total_mismatch``) onsuz da qoruyur
        keys = (("id", target.offering.subject_id), ("name", subject_key(target.offering.subject.name)))
        for key in keys:
            for other in attempts.get((target.student_id, key), ()):
                if other.pk == target.pk or other.offering.period_id == target.offering.period_id:
                    continue
                if (exam is None or exams.get(other.pk) == exam) and (resit is None or resits.get(other.pk) == resit):
                    skipped.add(pk)
    return skipped


def apply_official_entry(run) -> None:
    from apps.registrar.public import EntryTarget, align_archive_entries

    wanted = resolve_targets(run, run.bundle.get("official_entries") or [])
    for pk in copied_attempts(run.organization, wanted):
        run.count(f"official_entry.sem{wanted.pop(pk)[3]}.skip_copied_attempt")
    targets = {}
    for pk, (_enrollment, value, source, _semester, _export, total, row) in wanted.items():
        exam, resit = official_finals(row) if source == "total" else (None, None)
        targets[pk] = EntryTarget(entry=value, total=total, exam=exam, resit=resit, qb_fail=_qb_fail(row))
    force_total = bool(getattr(run, "force_official_total", False))
    rows = align_archive_entries(
        organization=run.organization,
        actor=run.actor,
        targets=targets,
        archive_name=ARCHIVE_COMPONENT_NAME,
        archive_kind=ARCHIVE_COMPONENT_KIND,
        reason=f"SYS-1: köhnə sistemin rəsmi bal vərəqinə görə giriş balı ({run.tag})"
        + (" · yekun rəsmi vərəqə məcburi bərabərləşdirildi (sahib 2026-11-09)" if force_total else ""),
        force_total=force_total,
    )
    for row in rows:
        _enrollment, target, source, semester, export_id, _total, _row = wanted[row.enrollment_id]
        prefix = f"official_entry.sem{semester}"
        run.count(f"{prefix}.{row.outcome}")
        for kind in row.filled:
            run.count(f"{prefix}.filled_{kind}")
        if row.total_fix:
            run.count(f"{prefix}.total_fix_{row.total_fix}")
            run.count(f"official_entry.total_fix_{row.total_fix}")
            if row.total_fix != "kept_higher":
                run.names(
                    "official_entry_total_forced",
                    row.student,
                    f"{row.subject} · {row.period} · yekun {_n(row.total_before)}→{_n(row.total_after)} "
                    f"({row.result_before}→{row.result_after}) · {row.total_fix} · vərəq #{export_id}",
                )
        if row.outcome == "skip_total_mismatch":
            run.names(
                "official_entry_total_mismatch",
                row.student,
                f"{row.subject} · {row.period} · giriş {_n(row.entry_before)}→{_n(row.entry_after)} · yeni yekun "
                f"{_n(row.total_after)} ≠ rəsmi {_n(_total)} (imtahan/25 % fərqi) · vərəq #{export_id}",
            )
        if row.outcome in ("same", "no_entry") and (row.filled or row.total_fix in ("exam", "resit")):
            pass  # giriş dəyişmir, yalnız imtahan / 25 % / köhnə q/b doldurulub və ya yekun məcburi — nəticə dəyişə bilər
        elif row.outcome != "written":
            continue
        else:
            run.count(f"{prefix}.written_from_{source}")
            run.count(f"{prefix}.{'raised' if target > row.entry_before else 'lowered'}")
        flip = f"{row.result_before}_to_{row.result_after}"
        if flip in FLIPS:
            run.count(f"{prefix}.{flip}")
            run.count(f"official_entry.{flip}")
        run.names(
            f"official_entry_{flip}" if flip in FLIPS else "official_entry_changed",
            row.student,
            f"{row.subject} · {row.period} · giriş {_n(row.entry_before)}→{_n(row.entry_after)} · "
            f"yekun {_n(row.total_before)}→{_n(row.total_after)} ({row.result_before}→{row.result_after}) · "
            f"{'doldurulub: ' + '+'.join(row.filled) + ' · ' if row.filled else ''}"
            f"vərəq #{export_id}",
        )


def _qb_fail(row) -> bool:
    """Rəsmi vərəqdə davamiyyətdən kəsilib (``(Kəsr)``) və imtahan yoxdur — köhnə q/b qərarı."""

    return bool(row.get("attendance_fail")) and row.get("exam") in (None, "") and row.get("resit") in (None, "", "0")


def _official_total(row):
    value = row.get("total")
    return Decimal(str(value)) if value not in (None, "") else None


def _n(value) -> str:
    return format(Decimal(value).normalize(), "f") if value is not None else "—"


__all__ = ["OfficialEntryPhaseMismatch", "apply_official_entry", "check_phases", "resolve_targets"]
