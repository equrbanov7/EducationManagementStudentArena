"""«Bölgü sehrbazı» — fənn kartının seminar / laboratoriya bölgüsü addım-addım (sahib 2026-11-26). OXU tərəfi.

Sahib: «Yük bölgüsü-ndə bölmə axını aydın deyil — mən özüm də bilmirəm necə edim. Seminar 2-yə bölünür, lab-da hər
seminar alt qrupu yenə 2-yə … hansı tələbə haraya düşür bilinmir. İmtahan yaratma forması kimi addımlı modal olsun.»

Sehrbaz bir KARTIN (eyni fənn + semestr + kredit — :func:`.subject_cards.family_key`) sətirləri üzərində işləyir.
Seçim vahidi SƏTİRDİR: çox qruplu sətrin («536 İ / 536 ML») qrupları birlikdə seçilir — onların seminar/lab-ı ya
«birlikdə» keçir (``subgroup_count ≤ 1``), ya da qrup-qrup bölünür.

:func:`wizard_state` ekranın bütün datasını BİR cavabda verir:

* sətirlər — qrup başına saat (``per_group_hours``), cəmlər, çarpanlar, mövcud bölgülər (qrup bağı + alt qrup №),
  patok tərəfdaşının aparıcısı (mühazirə burada yalnız göstərilir/müəllimi seçilir — axınlar «Axınları dəyiş»-dədir);
* qruplar — jurnalın aktiv siyahısı və bölmələri (registrar fasadı), reyestr alt qrupları («234 K1», «234 K2»);
* tapşırıq — düzəliş tələbi, plan kafedraya çatıbmı (jurnalı indi yaratmaq olarmı), sətir cəmini dəyişmək olarmı.

Yazı tərəfi — :mod:`.split_wizard_apply`.
"""

from __future__ import annotations

from django.utils.translation import pgettext

from core.http_ids import parse_uuid
from core.person_names import person_label

from ..constants import AMENDMENT_SCOPED_STATUSES, EDITABLE_STATUSES, RowKind, TaskStatus
from ..models import TeachingTaskRow
from .group_aliases import verified_aliases
from .offering_rules import per_group_hours, plan_reached_chair
from .patok import is_partner, partner_lectures
from .row_edit import amendment_needed
from .scoping import WorkloadDenied, ensure_can_distribute
from .subject_cards import family_key

_CTX = "workload.split_wizard"
ACTIVITIES = ("lecture", "seminar", "lab")
TOTAL_FIELD = {"lecture": "lecture_total", "seminar": "seminar_total", "lab": "lab_total"}
PLAN_FIELD = {"lecture": "lecture_plan", "seminar": "seminar_plan", "lab": "lab_plan"}

#: Giriş xətaları (HTTP 400) — mətnlər ``pgettext`` ilə verilir.
WIZARD_INPUT_CODES = frozenset(
    {
        "workload.wizard_rows",
        "workload.wizard_rows_mismatch",
        "workload.wizard_units",
        "workload.wizard_hours",
        "workload.wizard_over_total",
        "workload.wizard_teacher",
        "workload.wizard_sections",
    }
)


def deny(code: str, message: str) -> WorkloadDenied:
    return WorkloadDenied(code, str(message))


def parse_row_ids(raw) -> list:
    """``"a,b"`` / ``["a", "b"]`` → UUID siyahısı (təkrarsız, sıra saxlanır); pozuq id — xəta."""
    items = raw.split(",") if isinstance(raw, str) else list(raw or [])
    ids = []
    for item in items:
        if not str(item or "").strip():
            continue
        pk = parse_uuid(str(item).strip())
        if pk is None:
            raise deny("workload.wizard_rows", pgettext(_CTX, "Sətir tapılmadı."))
        if pk not in ids:
            ids.append(pk)
    if not ids:
        raise deny("workload.wizard_rows", pgettext(_CTX, "Sətir seçilməyib."))
    return ids


def load_rows(task, row_ids, *, lock: bool = False) -> list:
    """Kartın sətirləri (tədris sətri, eyni ailə); ``lock`` — ``select_for_update`` (yazı tranzaksiyası)."""
    queryset = TeachingTaskRow.objects.filter(task=task, pk__in=row_ids)
    if lock:
        locked = [row.pk for row in queryset.select_for_update(of=("self",)).only("pk")]
        queryset = TeachingTaskRow.objects.filter(pk__in=locked)
    rows = list(
        queryset.select_related("subject", "period", "patok_lead").prefetch_related(
            "groups", "assignments__teacher__profile", "assignments__group"
        )
    )
    by_pk = {row.pk: row for row in rows}
    if len(by_pk) != len(row_ids) or any(row.row_kind != RowKind.TEACHING for row in rows):
        raise deny("workload.wizard_rows", pgettext(_CTX, "Sətir bu tapşırığın tədris sətri deyil."))
    if len({family_key(row) for row in rows}) != 1:
        raise deny("workload.wizard_rows_mismatch", pgettext(_CTX, "Sətirlər eyni fənn və semestrdə olmalıdır."))
    ordered = [by_pk[pk] for pk in row_ids]
    for row in ordered:
        row.task = task
    return ordered


def can_fix_totals(task) -> bool:
    """Sətrin cəmini (seminar/lab cəmi, alt qrup sayı) dəyişmək bu statusda mümkündürmü (düzəliş axını daxil)."""
    if task.status in (TaskStatus.DISTRIBUTED, TaskStatus.AMENDED):
        return True
    return task.status in EDITABLE_STATUSES and task.status not in AMENDMENT_SCOPED_STATUSES


def row_groups(row) -> list:
    """Sətrin qrupları — ad sırası ilə (fiziki ``OrgUnit``-lər; bölgünün qrup bağı bunlardan biri olmalıdır)."""
    return sorted(row.groups.all(), key=lambda unit: (unit.name or "", str(unit.pk)))


def assignment_payload(assignment) -> dict:
    teacher = assignment.teacher
    return {
        "id": str(assignment.pk),
        "activity": assignment.activity,
        "teacher_id": str(assignment.teacher_id) if assignment.teacher_id else "",
        "teacher_name": person_label(teacher) if teacher is not None else pgettext(_CTX, "Vakant"),
        "hours": int(assignment.hours),
        "group_id": str(assignment.group_id) if assignment.group_id else "",
        "sub_number": assignment.sub_number,
        "is_vacant": assignment.teacher_id is None,
        "is_hourly_paid": bool(assignment.is_hourly_paid),
    }


def _row_payload(task, row, partners) -> dict:
    groups = row_groups(row)
    plans = per_group_hours(row)
    partner = partners.get(row.pk) if is_partner(row) else None
    lectures = [a for a in row.assignments.all() if a.activity == "lecture"]
    return {
        "id": str(row.pk),
        "groups": [str(group.pk) for group in groups],
        "label": " · ".join(group.name for group in groups) or row.groups_text or "—",
        "joint": len(groups) > 1 and int(row.subgroup_count or 1) <= 1,
        "plans": {activity: int(plans[activity]) for activity in ACTIVITIES},
        "plan_fields": {activity: int(getattr(row, PLAN_FIELD[activity]) or 0) for activity in ACTIVITIES},
        "totals": {activity: int(getattr(row, TOTAL_FIELD[activity]) or 0) for activity in ACTIVITIES},
        "union_count": int(row.union_count or 1),
        "subgroup_count": int(row.subgroup_count or 0),
        "lab_group_count": int(row.lab_group_count or 0),
        "student_count": int(row.student_count or 0),
        "needs_amendment": amendment_needed(task, row),
        "partner": (
            {"lead_groups": partner.get("groups") or "", "teacher_name": partner.get("teacher_name") or ""}
            if partner
            else None
        ),
        # Mühazirəçini burada yalnız sadə halda seçmək olar: axının aparıcısı, ən çox bir mühazirə bölgüsü.
        "lecture_editable": not partner and int(row.lecture_total or 0) > 0 and len(lectures) <= 1,
        "assignments": [assignment_payload(a) for a in row.assignments.all()],
    }


def journal_keys(rows) -> dict:
    """``{fiziki qrup pk: jurnal açarı (fənn, dövr, alias qrup)}`` — kartdakı alt bölmə seçicisi ilə eyni açar."""
    aliases = verified_aliases(group for row in rows for group in row.groups.all())
    keys = {}
    for row in rows:
        if not (row.subject_id and row.period_id):
            continue
        for group in row.groups.all():
            keys[group.pk] = (row.subject_id, row.period_id, aliases.get(group.pk, group).pk)
    return keys


def wizard_state(*, task, actor, row_ids) -> dict:
    """Sehrbazın açılış datası (bax modul başlığı). İcazə: ``workload.distribute`` (kafedra əhatəsi)."""
    from apps.registrar.public import split_wizard_journal_state, split_wizard_registry_subgroups

    ensure_can_distribute(actor, task.chair_id)
    rows = load_rows(task, parse_row_ids(row_ids))
    partners = partner_lectures(rows)
    keys = journal_keys(rows)
    journals = split_wizard_journal_state(
        organization=task.organization, user=getattr(actor, "user", None), keys=set(keys.values())
    )
    registry = split_wizard_registry_subgroups(organization=task.organization, group_ids={k[2] for k in keys.values()})
    groups = []
    for row in rows:
        for group in row_groups(row):
            key = keys.get(group.pk)
            journal = journals.get(key) if key else None
            groups.append(
                {
                    "id": str(group.pk),
                    "name": group.name,
                    "row_id": str(row.pk),
                    "student_count": len(journal["students"]) if journal else 0,
                    "journal": journal,
                    "registry_subgroups": registry.get(key[2], []) if key else [],
                }
            )
    first = rows[0]
    return {
        "task": {
            "id": str(task.pk),
            "status": task.status,
            "needs_amendment": any(amendment_needed(task, row) for row in rows),
            "plan_reached": plan_reached_chair(task),
            "can_fix_totals": can_fix_totals(task),
        },
        "subject": first.subject_label,
        "period_label": f"{first.period.name} · {first.period.academic_year}" if first.period_id else "",
        "rows": [_row_payload(task, row, partners) for row in rows],
        "groups": groups,
    }


__all__ = [
    "ACTIVITIES",
    "PLAN_FIELD",
    "TOTAL_FIELD",
    "WIZARD_INPUT_CODES",
    "assignment_payload",
    "can_fix_totals",
    "deny",
    "journal_keys",
    "load_rows",
    "parse_row_ids",
    "row_groups",
    "wizard_state",
]
