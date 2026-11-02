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
from .official_entry_sheets import target_entry

ARCHIVE_COMPONENT_NAME = "Davamiyyət və sərbəst iş (arxiv)"  # J5b ``ARCHIVE_COMPONENT_NAME`` güzgüsü
ARCHIVE_COMPONENT_KIND = "generic"
FLIPS = ("fail_to_pass", "pass_to_fail")


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
    """Paket sətirləri → ``{pk: (enrollment, hədəf, mənbə, semestr, vərəq id, rəsmi yekun)}``; imtinalar sayılır.

    Rəsmi yekun yalnız hədəf yekundan çıxarılıbsa (``source == "total"``) ötürülür — yeni yekun ona bərabər olmalıdır.
    """

    keys = {(uniqid, int(row["student_id"])) for row in rows for uniqid in row.get("journals") or ()}
    ledger = run.ledger_enrollments(keys)
    wanted: dict = {}
    clashing: set = set()
    for row in rows:
        semester = int(row.get("semestr") or 0)
        prefix = f"official_entry.sem{semester}"
        value, source = target_entry(row)
        if value is None:
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
        previous = wanted.get(pk)
        if previous is not None and previous[1] != value:
            clashing.add(pk)
        total = _official_total(row) if source == "total" else None
        wanted[pk] = (enrollment, value, source, semester, row.get("export_id"), total)
    for pk in clashing:
        run.count(f"official_entry.sem{wanted.pop(pk)[3]}.skip_target_conflict")
    return wanted


def apply_official_entry(run) -> None:
    from apps.registrar.public import align_archive_entries

    wanted = resolve_targets(run, run.bundle.get("official_entries") or [])
    rows = align_archive_entries(
        organization=run.organization,
        actor=run.actor,
        targets={pk: (value, total) for pk, (_enrollment, value, _source, _semester, _export, total) in wanted.items()},
        archive_name=ARCHIVE_COMPONENT_NAME,
        archive_kind=ARCHIVE_COMPONENT_KIND,
        reason=f"SYS-1: köhnə sistemin rəsmi bal vərəqinə görə giriş balı ({run.tag})",
    )
    for row in rows:
        _enrollment, target, source, semester, export_id, _total = wanted[row.enrollment_id]
        prefix = f"official_entry.sem{semester}"
        run.count(f"{prefix}.{row.outcome}")
        if row.outcome == "skip_total_mismatch":
            run.names(
                "official_entry_total_mismatch",
                row.student,
                f"{row.subject} · {row.period} · giriş {_n(row.entry_before)}→{_n(row.entry_after)} · yeni yekun "
                f"{_n(row.total_after)} ≠ rəsmi {_n(_total)} (imtahan/25 % fərqi) · vərəq #{export_id}",
            )
        if row.outcome != "written":
            continue
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
            f"vərəq #{export_id}",
        )


def _official_total(row):
    value = row.get("total")
    return Decimal(str(value)) if value not in (None, "") else None


def _n(value) -> str:
    return format(Decimal(value).normalize(), "f") if value is not None else "—"


__all__ = ["OfficialEntryPhaseMismatch", "apply_official_entry", "check_phases", "resolve_targets"]
