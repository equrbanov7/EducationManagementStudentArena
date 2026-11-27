"""«Bölgü sehrbazı» — YAZI tərəfi: jurnal bölmələri + sətir cəmi + bölgülər BİR tranzaksiyada (sahib 2026-11-26).

:func:`apply_wizard` gövdəsi (``POST bolgu/sehrbaz/yadda-saxla/``)::

    {"task_id": "…", "row_ids": ["…"],
     "rows":   [{"row_id": "…", "joint_by_activity": {"seminar": false, "lab": true}, "fix_totals": true}],
     "groups": [{"row_id": "…", "group_id": "…", "apply_journal": true,
                 "seminar": {"count": 2, "numbers": [1, 2], "names": ["234 K1", "234 K2"], "units": ["<OrgUnit>", "…"],
                             "placement": {"<enrollment>": 1, …}},
                 "lab": {"count": 4, "numbers": [1, 2, 3, 4], "nested": true, "names": ["234 K1 · Lab-1", …],
                         "placement": {…}}}],
     "units":  [{"row_id": "…", "activity": "seminar|lab", "group_id": "…|", "sub_number": 1|null,
                 "teacher_id": "<id>|vacant|", "hours": 30, "is_hourly_paid": false, "keep": false}],
     "lecture": [{"row_id": "…", "teacher_id": "<id>|vacant"}],
     "amend_reason": "…", "amend_note": "…"}

QAYDALAR:

* ``joint_by_activity`` hər fəaliyyətin seçimini saxlayır. Köhnə ``joint`` hər iki fəaliyyətə tətbiq olunur;
* ``numbers`` — jurnal bölmələrinin REAL nömrələri (boşluqlu {2,3} də; yoxdursa 1..count) — yenidən nömrələnmir;
* vahidlər (bölmələr) serverdə konfiqurasiyadan YENİDƏN törədilir (:func:`expected_units`) və gövdədəki ``units`` ilə
  TAM üst-üstə düşməlidir — müştəri ilə server fərqli düşünürsə heç nə yazılmır (``workload.wizard_units``);
* ``teacher_id`` boş — vahidə bölgü yoxdur (mövcudu silinir), ``vacant`` — vakant bölgü, ``keep`` — vahidin mövcud
  (bir neçə müəllimli) bölgüləri toxunulmaz qalır;
* sətir cəmi yalnız ``fix_totals`` ilə: ``seminar_total = qrup planı × seminar vahidi``, ``lab_total = lab planı ×
  lab vahidi``, ``subgroup_count`` / ``lab_group_count`` — sayların özü (düzəliş axını, tarixçə — ``save_row_amended``);
* hər fəaliyyətdə Σ saat ≤ (yeni) cəm — əks halda ``workload.wizard_over_total``;
* SIRA (DB trigger-i müvəqqəti aşmanı da rədd edir): jurnal bölmələri → silmələr → azalan redaktələr → sətir cəmi →
  artan redaktələr → əlavələr → mühazirəçi; açılış sinxronu sonda sətir başına BİR dəfə.

Hər yazı mövcud servislərlə gedir (icazə, düzəliş səbəbi, audit, trigger); hər hansı xəta bütün tranzaksiyanı geri
qaytarır — jurnal bölmələri də.
"""

from __future__ import annotations

from collections import defaultdict

from django.db import transaction
from django.utils.translation import pgettext

from core.audit import log_action
from core.constants import AuditAction
from core.http_ids import parse_uuid

from .assignments import _owner_snapshot, _sync_row
from .offering_rules import plan_reached_chair
from .patok_streams import VACANT, _set_lecturer
from .row_edit import assign_amended, save_row_amended, unassign_amended
from .scoping import WorkloadDenied, ensure_can_distribute
from .split_wizard import (
    PLAN_FIELD,
    TOTAL_FIELD,
    can_fix_totals,
    deny,
    load_rows,
    parse_row_ids,
    row_groups,
    row_joint_modes,
)

_CTX = "workload.split_wizard"
SECTION_KINDS = ("seminar", "lab")
#: Registrar bölmə xətası → HTTP statusu (403 səlahiyyət, 409 bağlı jurnal, qalanı giriş xətası).
_SECTION_CODES = {403: "workload.wizard_forbidden", 409: "workload.wizard_blocked"}


def _count(raw) -> int:
    try:
        value = int(raw or 0)
    except (TypeError, ValueError):
        value = 0
    return value if 2 <= value <= 9 else 0


def _numbers(raw) -> list:
    """Bölmələrin REAL nömrələri (``numbers``; yoxdursa ``1..count``) — boşluqlu {2,3} yenidən nömrələnmir."""
    if "numbers" not in raw:
        return list(range(1, _count(raw.get("count")) + 1))
    values = raw.get("numbers") if isinstance(raw.get("numbers"), (list, tuple)) else []
    try:
        numbers = [int(value) for value in values]  # sıra adlarla (``names``) üst-üstə düşür — dəyişdirilmir
    except (TypeError, ValueError):
        numbers = []
    if len(set(numbers)) != len(values) or any(not 1 <= number <= 9 for number in numbers):
        raise deny("workload.wizard_units", pgettext(_CTX, "Bölmələr dəyişib — sehrbazı bağlayıb yenidən açın."))
    return numbers if len(numbers) >= 2 else []


def _teacher(raw):
    """``""`` → yoxdur (``False``), ``vacant`` → ``None``, id → ``int`` / UUID."""
    text = str(raw or "").strip()
    if not text:
        return False
    if text == VACANT:
        return None
    value = int(text) if text.isdigit() else parse_uuid(text)
    if value is None:
        raise deny("workload.wizard_teacher", pgettext(_CTX, "Müəllim düzgün seçilməyib."))
    return value


def _parse_config(payload, rows) -> dict:
    """``{row_pk: {"joint", "fix", "groups": {group_pk: {"seminar", "lab", "journal"}}}}``."""
    row_items = {parse_uuid((item or {}).get("row_id")): item for item in payload.get("rows") or [] if item}
    group_items = {}
    for item in payload.get("groups") or []:
        item = item or {}
        group_items[(parse_uuid(item.get("row_id")), parse_uuid(item.get("group_id")))] = item
    config = {}
    for row in rows:
        item = row_items.get(row.pk) or {}
        groups = row_groups(row)
        current = row_joint_modes(row, groups)
        modes = item.get("joint_by_activity")
        if modes is None:
            legacy = bool(item.get("joint"))
            # An open legacy tab cannot represent both modes. Its omitted assignments would be removed.
            if (
                current["seminar"] != current["lab"]
                and _active(row, "lab")
                and (_active(row, "seminar") or legacy != current["lab"])
            ):
                raise deny(
                    "workload.wizard_refresh",
                    pgettext(
                        _CTX,
                        "Bu sətirdə seminar və laboratoriyanın qrup bölgüsü fərqlidir. "
                        "Səhifəni yeniləyib hər fəaliyyətin bölgüsünü ayrıca yoxlayın.",
                    ),
                )
            modes = dict.fromkeys(SECTION_KINDS, legacy)
        if not isinstance(modes, dict) or any(not isinstance(value, bool) for value in modes.values()):
            raise deny("workload.wizard_units", pgettext(_CTX, "Bölmələr dəyişib — sehrbazı bağlayıb yenidən açın."))
        joint = {kind: len(groups) > 1 and modes.get(kind, current[kind]) for kind in SECTION_KINDS}
        per_group = {}
        for group in groups:
            entry = group_items.get((row.pk, group.pk)) or {}
            seminar = entry.get("seminar") if isinstance(entry.get("seminar"), dict) else {}
            lab = entry.get("lab") if isinstance(entry.get("lab"), dict) else {}
            per_group[group.pk] = {
                "seminar": [] if joint["seminar"] else _numbers(seminar),
                "lab": [] if joint["lab"] else _numbers(lab),
                "journal": (
                    {"seminar": seminar, "lab": lab} if entry.get("apply_journal") and not all(joint.values()) else None
                ),
            }
        config[row.pk] = {"joint": joint, "fix": bool(item.get("fix_totals")), "groups": per_group, "row": row}
    return config


def _active(row, activity) -> bool:
    return int(getattr(row, TOTAL_FIELD[activity]) or 0) > 0


def expected_units(row, cfg) -> dict:
    """``{"seminar": [(qrup pk | None, alt qrup № | None)], "lab": [...]}`` — sətrin vahidləri (bax modul başlığı)."""
    result = {}
    for activity in SECTION_KINDS:
        if not _active(row, activity):
            result[activity] = []
            continue
        if cfg["joint"][activity]:
            result[activity] = [(None, None)]
            continue
        keys = []
        for group in row_groups(row):
            numbers = cfg["groups"][group.pk][activity]
            keys += [(group.pk, number) for number in numbers] if numbers else [(group.pk, None)]
        result[activity] = keys
    return result


def _existing_key(assignment, row):
    groups = row_groups(row)
    group = assignment.group_id
    if group is None and len(groups) == 1:
        group = groups[0].pk
    return (group, assignment.sub_number)


def _parse_units(payload, config, expected) -> dict:
    """Gövdənin vahidləri → ``{(row, activity, key): {...}}``; konfiqurasiyadan törənənlə tam eyni olmalıdır."""
    wanted = {
        (row_pk, activity, key)
        for row_pk, kinds in expected.items()
        for activity, keys in kinds.items()
        for key in keys
    }
    units = {}
    for item in payload.get("units") or []:
        item = item or {}
        row_pk = parse_uuid(item.get("row_id"))
        activity = str(item.get("activity") or "")
        group_raw = item.get("group_id")
        group = parse_uuid(group_raw) if group_raw else None
        try:
            sub = int(item["sub_number"]) if item.get("sub_number") not in (None, "", 0, "0") else None
        except (TypeError, ValueError):
            sub = -1
        row = config.get(row_pk, {}).get("row")
        if row is not None and group is None and len(row_groups(row)) == 1:
            group = row_groups(row)[0].pk
        marker = (row_pk, activity, (group, sub))
        if marker not in wanted or marker in units:
            raise deny("workload.wizard_units", pgettext(_CTX, "Bölmələr dəyişib — sehrbazı bağlayıb yenidən açın."))
        teacher = _teacher(item.get("teacher_id"))
        hours = 0
        if teacher is not False:
            try:
                hours = int(item.get("hours") or 0)
            except (TypeError, ValueError):
                hours = 0
            if hours <= 0:
                raise deny("workload.wizard_hours", pgettext(_CTX, "Saat sıfırdan böyük olmalıdır."))
        units[marker] = {
            "teacher": teacher,
            "hours": hours,
            "hourly": bool(item.get("is_hourly_paid")),
            "keep": bool(item.get("keep")),
        }
    if set(units) != wanted:
        raise deny("workload.wizard_units", pgettext(_CTX, "Bölmələr dəyişib — sehrbazı bağlayıb yenidən açın."))
    return units


def _totals_data(row, cfg, keys) -> dict:
    """``fix_totals`` üçün sətir yazısı: cəmlər + saylar (dəyişməyənlər buraxılır)."""
    from .offering_rules import per_group_hours

    plans = per_group_hours(row)
    data = {}
    counts = {}
    for activity in SECTION_KINDS:
        if not _active(row, activity):
            continue
        counts[activity] = len(keys[activity])
        want = plans[activity] * counts[activity]
        if want != int(getattr(row, TOTAL_FIELD[activity]) or 0):
            data[TOTAL_FIELD[activity]] = want
            if not int(getattr(row, PLAN_FIELD[activity]) or 0):
                data[PLAN_FIELD[activity]] = plans[activity]
    sub = counts.get("seminar", row.subgroup_count)
    if sub != row.subgroup_count:
        data["subgroup_count"] = sub
    if "lab" in counts:
        lab = counts["lab"]
        follows_changed_seminar = sub != row.subgroup_count and lab == sub
        if lab != (row.lab_group_count or sub) or (row.lab_group_count and follows_changed_seminar):
            data["lab_group_count"] = 0 if lab == sub else lab
    return data


def _plan_writes(config, expected, units) -> dict:
    """Bölgü dəyişiklikləri: silmələr / redaktələr / əlavələr + fəaliyyət üzrə yekun saat."""
    removes, edits, adds = [], [], []
    final = defaultdict(int)
    for row_pk, cfg in config.items():
        row = cfg["row"]
        existing = defaultdict(list)
        for assignment in sorted(row.assignments.all(), key=lambda a: (a.created_at, str(a.pk))):
            if assignment.activity in SECTION_KINDS:
                existing[(assignment.activity, _existing_key(assignment, row))].append(assignment)
        for activity, keys in expected[row_pk].items():
            for key in keys:
                unit = units[(row_pk, activity, key)]
                found = existing.pop((activity, key), [])
                if unit["keep"] and found:
                    final[(row_pk, activity)] += sum(int(a.hours) for a in found)
                    continue
                if unit["teacher"] is False:
                    removes += found
                    continue
                final[(row_pk, activity)] += unit["hours"]
                item = {"row": row, "activity": activity, "key": key, **unit}
                if not found:
                    adds.append(item)
                    continue
                current, extra = found[0], found[1:]
                removes += extra
                if (current.teacher_id, int(current.hours), bool(current.is_hourly_paid)) != (
                    unit["teacher"],
                    unit["hours"],
                    unit["hourly"],
                ):
                    edits.append({**item, "assignment": current})
        for leftovers in existing.values():
            removes += leftovers
    return {"removes": removes, "edits": edits, "adds": adds, "final": final}


def _check_totals(config, plan, totals) -> None:
    for (row_pk, activity), hours in plan["final"].items():
        row = config[row_pk]["row"]
        total = totals.get(row_pk, {}).get(TOTAL_FIELD[activity], int(getattr(row, TOTAL_FIELD[activity]) or 0))
        if hours > total:
            raise deny(
                "workload.wizard_over_total",
                pgettext(
                    _CTX,
                    "%(groups)s: %(activity)s üçün %(hours)s saat paylanıb, sətrin cəmi isə %(total)s saatdır. "
                    "«Yoxla» addımında «Sətri düzəlt» seçin və ya saatı azaldın.",
                )
                % {
                    "groups": " · ".join(group.name for group in row_groups(row)) or "—",
                    "activity": pgettext(_CTX, "seminar") if activity == "seminar" else pgettext(_CTX, "laboratoriya"),
                    "hours": hours,
                    "total": total,
                },
            )


def _apply_sections(task, actor, config, request) -> int:
    from apps.registrar.public import SplitWizardSectionError, split_wizard_apply_sections

    from .split_wizard import journal_keys

    rows = [cfg["row"] for cfg in config.values()]
    keys = journal_keys(rows)
    changed = 0
    for cfg in config.values():
        for group_pk, entry in cfg["groups"].items():
            if entry["journal"] is None or group_pk not in keys:
                continue
            # Sətirdə saatı olmayan növə toxunulmur (``None``) — eyni jurnalın başqa sətrinin bölmələri qorunur.
            row = cfg["row"]
            seminar = lab = None
            if _active(row, "seminar") and not cfg["joint"]["seminar"]:
                seminar = dict(entry["journal"]["seminar"], count=len(entry["seminar"]), numbers=entry["seminar"])
            if _active(row, "lab") and not cfg["joint"]["lab"]:
                lab = dict(entry["journal"]["lab"], count=len(entry["lab"]), numbers=entry["lab"])
                if cfg["joint"]["seminar"]:
                    lab["nested"] = False
            if seminar is None and lab is None:
                continue
            try:
                result = split_wizard_apply_sections(
                    organization=task.organization,
                    user=getattr(actor, "user", None),
                    key=keys[group_pk],
                    seminar=seminar,
                    lab=lab,
                    request=request,
                )
            except SplitWizardSectionError as exc:
                raise WorkloadDenied(_SECTION_CODES.get(exc.status, "workload.wizard_sections"), exc.message)
            changed += int(result.get("changed") or 0)
    return changed


def _assign(task, actor, item, amend, request, *, assignment=None):
    row = item["row"]
    group = item["key"][0]
    return assign_amended(
        row=row,
        actor=actor,
        amend=amend,
        request=request,
        assignment=assignment,
        activity=item["activity"],
        teacher_id=item["teacher"],
        hours=item["hours"],
        is_hourly_paid=item["hourly"],
        note=assignment.note if assignment is not None else "",
        group_id=str(group) if group else None,
        sub_number=item["key"][1],
        sync_offerings=False,
        live_edit=True,
    )


@transaction.atomic
def apply_wizard(*, task, actor, payload, amend=None, request=None) -> dict:
    """Sehrbazın «Təsdiqlə» düyməsi (bax modul başlığı). Qaytarır: yazı xülasəsi (saylar)."""
    ensure_can_distribute(actor, task.chair_id)
    rows = load_rows(task, parse_row_ids(payload.get("row_ids")), lock=True)
    config = _parse_config(payload, rows)
    expected = {row.pk: expected_units(row, config[row.pk]) for row in rows}
    units = _parse_units(payload, config, expected)
    fix_allowed = can_fix_totals(task)
    totals = {}
    for row in rows:
        if config[row.pk]["fix"]:
            data = _totals_data(row, config[row.pk], expected[row.pk])
            if data and not fix_allowed:
                raise deny(
                    "workload.task_not_editable",
                    pgettext(_CTX, "Bu mərhələdə sətrin cəmini dəyişmək olmur — tədris şöbəsinə müraciət edin."),
                )
            if data:
                totals[row.pk] = data
    plan = _plan_writes(config, expected, units)
    _check_totals(config, plan, totals)
    lectures = []
    for item in payload.get("lecture") or []:
        row = next((r for r in rows if r.pk == parse_uuid((item or {}).get("row_id"))), None)
        if row is None or int(row.lecture_total or 0) <= 0 or row.patok_lead_id:
            raise deny("workload.wizard_units", pgettext(_CTX, "Mühazirəçini bu sətirdə seçmək olmur."))
        teacher = _teacher((item or {}).get("teacher_id"))
        lectures.append((row, VACANT if teacher in (False, None) else teacher))

    create = plan_reached_chair(task)
    before = {row.pk: _owner_snapshot(row, live_edit=True) for row in rows}
    summary = {"sections": _apply_sections(task, actor, config, request)}
    for assignment in plan["removes"]:
        assignment.row.task = task
        unassign_amended(
            assignment=assignment, actor=actor, amend=amend, request=request, sync_offerings=False, live_edit=True
        )
    shrinking = [e for e in plan["edits"] if e["hours"] <= int(e["assignment"].hours)]
    growing = [e for e in plan["edits"] if e["hours"] > int(e["assignment"].hours)]
    for item in shrinking:
        _assign(task, actor, item, amend, request, assignment=item["assignment"])
    for row in rows:
        if row.pk in totals:
            save_row_amended(
                task=task, actor=actor, data=totals[row.pk], row=row, amend=amend, request=request, sync_offerings=False
            )
    for item in growing:
        _assign(task, actor, item, amend, request, assignment=item["assignment"])
    for item in plan["adds"]:
        _assign(task, actor, item, amend, request)
    for row, teacher in lectures:
        _set_lecturer(task, actor, row, teacher, amend, request)
    touched = bool(plan["removes"] or plan["edits"] or plan["adds"] or totals or lectures)
    offerings = {}
    if touched:
        for row in rows:
            row.task = task
            offerings[str(row.pk)] = _sync_row(
                row, actor=actor, request=request, previous=before[row.pk], create=create
            )
    summary.update(
        {
            "removed": len(plan["removes"]),
            "edited": len(plan["edits"]),
            "added": len(plan["adds"]),
            "rows_fixed": len(totals),
            "lecturers": len(lectures),
        }
    )
    if touched or summary["sections"]:
        log_action(
            AuditAction.UPDATE,
            user=getattr(actor, "user", None),
            organization=task.organization,
            obj=task,
            new_values={**summary, "rows": [str(row.pk) for row in rows], "offerings": offerings},
            reason="workload.split_wizard",
            request=request,
            resource_type="workload.TeachingTask",
            resource_id=str(task.pk),
            resource_repr=rows[0].subject_label,
        )
    return summary


def ensure_journals(*, task, actor, row_ids, request=None) -> dict:
    """«Jurnalı indi yarat»: plan kafedraya çatıbsa sətirlərin qrup açılışları mövcud sinxron yolu ilə yaradılır."""
    from .offering_sync import compact, run_safely, sync_row_offerings

    ensure_can_distribute(actor, task.chair_id)
    rows = load_rows(task, parse_row_ids(row_ids))
    if not plan_reached_chair(task):
        raise deny(
            "workload.wizard_sections",
            pgettext(_CTX, "Jurnal tapşırıq dekanlıqda təsdiqlənəndən sonra yaranır — indi yalnız saatı bölmək olar."),
        )
    report = {}
    for row in rows:
        result = compact(run_safely(sync_row_offerings, row, actor=actor, request=request, create=True))
        for key, value in result.items():
            report[key] = report.get(key, 0) + value
    return report


__all__ = ["SECTION_KINDS", "apply_wizard", "ensure_journals", "expected_units"]
