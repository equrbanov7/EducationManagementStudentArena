"""«Bölgü sehrbazı» — jurnalın seminar alt qrupları və lab qruplarını BİR addımda qurmaq (sahib 2026-11-26).

Sahib: «seminar 2-yə bölünür, lab-da hər seminar alt qrupu yenə 2-yə … 1 qrup seçirsən, 2 seminar qrupu deyir, amma
hansı tələbə haraya düşür bilinmir». Dərs yükü sehrbazı (``apps.workload.services.split_wizard*``) bu modulu YALNIZ
``apps.registrar.public`` üzərindən çağırır:

* :func:`journal_state` — (fənn, dövr, qrup) açarları üçün jurnalın aktiv siyahısı (tələbə → seminar alt qrupu, lab
  qrupu, reyestr qrupu), mövcud bölmələr (ad, mənbə alt qrup, bağlı dərs sayı), kilid səbəbi və aktorun səlahiyyəti;
* :func:`registry_subgroups` — reyestrin alt qrupları («234 K» → «234 K1», «234 K2»; ``subgroup_rollup.subgroup_map``);
* :func:`apply_sections` — bir jurnalın bölmələrini istənən vəziyyətə gətirir (yarat / adlandır / artıq olanı sil /
  tələbələri yerləşdir). İdempotentdir: dəyişiklik yoxdursa heç nə yazılmır (audit də yox).

QAYDALAR (mövcud modullarla eyni — :mod:`.lab_groups`, :mod:`.seminar_groups`, :mod:`.lab_groups_manage`):

* bölmələr 1..N nömrələnir; ``say ≤ 1`` = «bölünmür» (bütün tələbələrin bölməsi boşalır, sətirlər silinir);
* dərs bağlı nömrə silinə bilməz (``has_lessons``) — əvvəl dərsin bölməsi dəyişdirilməlidir;
* ``say ≥ 2`` olanda HƏR aktiv tələbə bir bölməyə yerləşdirilməlidir (tələbə başına bir seminar + bir lab);
* iç-içə rejimdə (``lab.nested``) bir lab qrupu iki seminar alt qrupunu QARIŞDIRMIR (``lab_mixed``);
* ad ≤ 40 simvol, eyni növdə iki eyni ad olmur; lab adı «Lab-N»-dirsə boş saxlanır (jurnal «234 K · Lab-N» yazır);
* tərkib qapısı «Lab qrupları» ekranı ilə EYNİDİR: bağlı jurnal / keçmiş dövr (``roster_block_reason``) və
  səlahiyyət (``lab_groups_manage.can_manage`` — jurnalın müəllimi, kafedra müdiri ``workload.distribute`` ilə, RİM).
"""

from __future__ import annotations

import re
import uuid
from collections import defaultdict

from django.apps import apps as django_apps
from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from django.utils.translation import pgettext

from core.audit import log_action
from core.constants import AuditAction
from core.person_names import person_label

from . import lab_groups, lab_groups_manage, seminar_groups
from .models import LAB_GROUP_NAME_MAX_LENGTH, CourseOffering, Enrollment, LabGroup, Lesson, SeminarGroup
from .subgroup_rollup import subgroup_map

_CTX = "registrar.split_wizard"
RESOURCE = "registrar.split_wizard"
MAX_SECTIONS = 9


class SectionSetupError(ValueError):
    """İstifadəçiyə göstərilən xəta (kod + mətn); ``status`` — HTTP qatı üçün ipucu."""

    def __init__(self, code, message, status=400):
        super().__init__(code, message, status)
        self.code = code
        self.message = str(message)
        self.status = status


def _uuid(value):
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


# ── Oxu ──────────────────────────────────────────────────────────────────────


def _offerings(organization, keys) -> dict:
    keys = {tuple(key) for key in keys if key and all(key)}
    if not keys:
        return {}
    rows = CourseOffering.objects.filter(
        organization=organization,
        is_active=True,
        subject_id__in={key[0] for key in keys},
        period_id__in={key[1] for key in keys},
        group_id__in={key[2] for key in keys},
    ).select_related("organization", "period", "group")
    return {
        (row.subject_id, row.period_id, row.group_id): row
        for row in rows
        if (row.subject_id, row.period_id, row.group_id) in keys
    }


def _record_groups(organization, student_ids) -> dict:
    Record = django_apps.get_model("registrar", "StudentAcademicRecord")
    return dict(
        Record.objects.filter(organization=organization, student_id__in=list(student_ids), is_active=True)
        .exclude(group__isnull=True)
        .values_list("student_id", "group_id")
    )


def _lesson_counts(offering_ids, field) -> dict:
    counts: dict = defaultdict(dict)
    rows = (
        Lesson.objects.filter(offering_id__in=offering_ids, **{f"{field}__isnull": False})
        .order_by()
        .values("offering_id", field)
        .annotate(total=Count("id"))
        .values_list("offering_id", field, "total")
    )
    for offering_id, number, total in rows:
        counts[offering_id][number] = total
    return counts


def journal_state(*, organization, user, keys) -> dict:
    """``{(fənn, dövr, qrup): {...}}`` — yalnız jurnalı olan açarlar (bax modul başlığı). Sorğu sayı açar sayından
    asılı deyil (açılışlar, siyahı, reyestr qrupları, bölmələr, dərs sayları — toplu)."""
    offerings = _offerings(organization, keys)
    if not offerings:
        return {}
    ids = [offering.pk for offering in offerings.values()]
    roster = list(
        Enrollment.objects.filter(organization=organization, offering_id__in=ids, status=Enrollment.Status.ENROLLED)
        .select_related("student", "student__profile")
        .order_by("student__last_name", "student__first_name", "student__username")
    )
    record_groups = _record_groups(organization, {row.student_id for row in roster})
    seminar_rows: dict = defaultdict(list)
    for row in SeminarGroup.objects.filter(offering_id__in=ids).order_by("number"):
        seminar_rows[row.offering_id].append(row)
    lab_rows: dict = defaultdict(list)
    for row in LabGroup.objects.filter(offering_id__in=ids).order_by("number"):
        lab_rows[row.offering_id].append(row)
    seminar_lessons = _lesson_counts(ids, "seminar_group")
    lab_lessons = _lesson_counts(ids, "lab_group")
    by_offering: dict = defaultdict(list)
    for row in roster:
        by_offering[row.offering_id].append(row)
    result = {}
    for key, offering in offerings.items():
        students = by_offering.get(offering.pk, [])
        result[key] = {
            "offering_id": str(offering.pk),
            "block_reason": str(lab_groups_manage.block_reason(offering) or ""),
            "can_manage": bool(lab_groups_manage.can_manage(user, offering)),
            "students": [
                {
                    "id": str(row.pk),
                    "name": person_label(row.student),
                    "seminar": row.seminar_group,
                    "lab": row.lab_group,
                    "unit_id": str(record_groups.get(row.student_id) or ""),
                }
                for row in students
            ],
            "seminar": _sections(
                seminar_rows.get(offering.pk, []),
                {row.seminar_group for row in students if row.seminar_group},
                seminar_lessons.get(offering.pk, {}),
                lambda number, name: name or seminar_groups.default_label(number),
            ),
            "lab": _sections(
                lab_rows.get(offering.pk, []),
                {row.lab_group for row in students if row.lab_group},
                lab_lessons.get(offering.pk, {}),
                lambda number, name, offering=offering: name
                or pgettext("registrar.lab_groups", "%(group)s · Lab-%(n)s")
                % {"group": offering.group.name, "n": number},
            ),
        }
    return result


def _sections(rows, roster_numbers, lessons, label) -> list:
    """Bölmələr: sətirlər ∪ siyahıdakı nömrələr ∪ dərsə bağlı nömrələr (sətirsiz köhnə Lab-1 də bölmədir)."""
    by_number = {row.number: row for row in rows}
    numbers = sorted(set(by_number) | set(roster_numbers) | set(lessons))
    return [
        {
            "number": number,
            "name": getattr(by_number.get(number), "name", "") or "",
            "label": label(number, getattr(by_number.get(number), "name", "") or ""),
            "unit_id": str(getattr(by_number.get(number), "unit_id", "") or ""),
            "lessons": int(lessons.get(number, 0)),
        }
        for number in numbers
    ]


def registry_subgroups(*, organization, group_ids) -> dict:
    """``{qrup_pk: [{"id", "name"}]}`` — reyestrin alt qrupları (ad sırası ilə); alt qrupu olmayan qrup yoxdur."""
    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    parents = list(
        OrgUnit.objects.filter(organization=organization, pk__in=list(group_ids)).only(
            "id", "name", "parent_id", "settings"
        )
    )
    return {
        parent_id: [{"id": str(unit.pk), "name": unit.name} for unit in units]
        for parent_id, units in subgroup_map(organization, parents).items()
    }


# ── Giriş datası ─────────────────────────────────────────────────────────────


def _clean_name(raw) -> str:
    return " ".join(str(raw or "").split())[:LAB_GROUP_NAME_MAX_LENGTH]


def _name_key(text) -> str:
    return re.sub(r"[\s\-]+", "", str(text or "").casefold())


def _count(raw) -> int:
    try:
        value = int(raw or 0)
    except (TypeError, ValueError):
        raise SectionSetupError("invalid_count", pgettext(_CTX, "Bölmə sayı düzgün deyil."))
    if not 0 <= value <= MAX_SECTIONS:
        raise SectionSetupError(
            "invalid_count", pgettext(_CTX, "Bölmə sayı 1–%(max)s arası olmalıdır.") % {"max": MAX_SECTIONS}
        )
    return value if value >= 2 else 0


def _placement(raw, count, enrolled, kind_label) -> dict:
    """``{enrollment_pk: nömrə | None}`` — say ≥ 2 olanda HƏR aktiv tələbə yerləşməlidir."""
    if not count:
        return {row.pk: None for row in enrolled}
    raw = raw if isinstance(raw, dict) else {}
    wanted = {}
    for key, value in raw.items():
        pk = _uuid(key)
        if pk is None:
            continue
        try:
            number = int(value)
        except (TypeError, ValueError):
            number = 0
        wanted[pk] = number if 1 <= number <= count else None
    missing = [row for row in enrolled if wanted.get(row.pk) is None]
    if missing:
        raise SectionSetupError(
            "unplaced",
            pgettext(_CTX, "%(kind)s: %(n)s tələbə heç bir bölməyə yerləşdirilməyib.")
            % {"kind": kind_label, "n": len(missing)},
        )
    return {row.pk: wanted[row.pk] for row in enrolled}


def _names(raw, count) -> list:
    raw = raw if isinstance(raw, (list, tuple)) else []
    names = [_clean_name(raw[index]) if index < len(raw) else "" for index in range(count)]
    keys = [_name_key(name) for name in names if name]
    if len(keys) != len(set(keys)):
        raise SectionSetupError("duplicate_name", pgettext(_CTX, "İki bölmənin adı eynidir — adları fərqləndirin."))
    return names


def _units(organization, raw, count) -> list:
    raw = raw if isinstance(raw, (list, tuple)) else []
    ids = [_uuid(raw[index]) if index < len(raw) else None for index in range(count)]
    wanted = {pk for pk in ids if pk}
    if wanted:
        OrgUnit = django_apps.get_model("organizations", "OrgUnit")
        found = set(OrgUnit.objects.filter(organization=organization, pk__in=wanted).values_list("pk", flat=True))
        ids = [pk if pk in found else None for pk in ids]
    return ids


# ── Yazı ─────────────────────────────────────────────────────────────────────


def _lab_name(number, name) -> str:
    """Lab adı öz defolt adıdırsa («Lab-N») boş saxlanır — jurnal «234 K · Lab-N» yazır."""
    defaults = {_name_key(lab_groups.default_label(number)), f"lab{number}"}
    return "" if _name_key(name) in defaults else name


def _check_lessons(offering, field, keep_upto, label) -> None:
    bound = (
        Lesson.objects.filter(offering_id=offering.pk, **{f"{field}__gt": keep_upto})
        .order_by()
        .values_list(field, flat=True)
        .distinct()
    )
    numbers = sorted(set(bound))
    if numbers:
        raise SectionSetupError(
            "has_lessons",
            pgettext(
                _CTX,
                "%(group)s: «%(section)s» bölməsinə dərs bağlıdır — əvvəlcə həmin dərslərin bölməsini jurnalda "
                "dəyişin, sonra bölmə sayını azaldın.",
            )
            % {"group": offering.group.name if offering.group_id else "—", "section": label(numbers[0])},
        )


def _sync_rows(model, offering, count, names, units, *, is_lab) -> int:
    """Bölmə sətirləri 1..count (ad, mənbə alt qrup); artıq sətirlər silinir. Qaytarır: dəyişən sətir sayı."""
    changed = 0
    existing = {row.number: row for row in model.objects.select_for_update().filter(offering_id=offering.pk)}
    for number in range(1, count + 1):
        name = names[number - 1]
        if is_lab:
            name = _lab_name(number, name)
        fields = {"name": name}
        if not is_lab:
            fields["unit_id"] = units[number - 1]
        row = existing.pop(number, None)
        if row is None:
            model.objects.create(organization_id=offering.organization_id, offering=offering, number=number, **fields)
            changed += 1
            continue
        dirty = [field for field, value in fields.items() if getattr(row, field) != value]
        if dirty:
            for field in dirty:
                setattr(row, field, fields[field])
            row.save(update_fields=[*dirty, "updated_at"])
            changed += 1
    if existing:
        model.objects.filter(pk__in=[row.pk for row in existing.values()]).delete()
        changed += len(existing)
    return changed


#: Növlər: (açar, ``Enrollment`` sahəsi, model, lab-dırmı, görünən ad).
_KINDS = (("seminar", "seminar_group", SeminarGroup, False), ("lab", "lab_group", LabGroup, True))


def _kind_label(kind) -> str:
    return pgettext(_CTX, "Seminar") if kind == "seminar" else pgettext(_CTX, "Laboratoriya")


def _desired_kind(organization, raw, enrolled, kind):
    """Növün istənən vəziyyəti; ``raw is None`` — bu növə TOXUNULMUR (məs. sətirdə seminar saatı yoxdur)."""
    if raw is None:
        return None
    raw = raw if isinstance(raw, dict) else {}
    count = _count(raw.get("count"))
    return {
        "count": count,
        "names": _names(raw.get("names"), count),
        "units": _units(organization, raw.get("units"), count) if kind == "seminar" else [None] * count,
        "place": _placement(raw.get("placement"), count, enrolled, _kind_label(kind)),
        "nested": bool(raw.get("nested")),
    }


def _new_value(desired, row, kind, field):
    return desired[kind]["place"][row.pk] if desired[kind] is not None else getattr(row, field)


def _check_nested(desired, enrolled, offering) -> None:
    """İç-içə rejim: bir lab qrupu iki seminar alt qrupunu qarışdırmır."""
    lab = desired["lab"]
    if lab is None or not lab["nested"] or not lab["count"]:
        return
    mixed: dict = defaultdict(set)
    for row in enrolled:
        mixed[lab["place"][row.pk]].add(_new_value(desired, row, "seminar", "seminar_group"))
    bad = sorted(number for number, sections in mixed.items() if number and len(sections) > 1)
    if bad:
        raise SectionSetupError(
            "lab_mixed",
            pgettext(_CTX, "«%(lab)s» lab qrupunda iki seminar alt qrupunun tələbəsi var — qarışdırmaq olmaz.")
            % {"lab": lab["names"][bad[0] - 1] or lab_groups.label(bad[0], offering)},
        )


def _rows_differ(model, offering, spec, *, is_lab) -> bool:
    current = {row.number: row for row in model.objects.filter(offering_id=offering.pk)}
    if set(current) != set(range(1, spec["count"] + 1)):
        return True
    for number, row in current.items():
        name = _lab_name(number, spec["names"][number - 1]) if is_lab else spec["names"][number - 1]
        if row.name != name or (not is_lab and row.unit_id != spec["units"][number - 1]):
            return True
    return False


def _label_for(kind, offering):
    module = seminar_groups if kind == "seminar" else lab_groups
    return lambda number: module.label(number, offering)


def apply_sections(*, organization, user, key, seminar=None, lab=None, request=None) -> dict:
    """(fənn, dövr, qrup) jurnalının seminar alt qruplarını və lab qruplarını istənən vəziyyətə gətir (modul başlığı).

    ``seminar`` — ``{"count", "names": [...], "units": [OrgUnit id | ""], "placement": {enrollment_id: nömrə}}``;
    ``lab`` — ``{"count", "names", "placement", "nested": bool}``; ``None`` — həmin növə toxunulmur. Qaytarır:
    ``{"changed", "students", "sections"}``. Xəta — :class:`SectionSetupError`; çağıranın tranzaksiyası geri qaytarılır.
    """
    key = tuple(key or ())
    offering = _offerings(organization, [key]).get(key) if len(key) == 3 else None
    if offering is None:
        raise SectionSetupError("not_found", pgettext(_CTX, "Jurnal tapılmadı."), status=404)
    with transaction.atomic():
        CourseOffering.objects.select_for_update().filter(pk=offering.pk).values_list("pk", flat=True).first()
        enrolled = list(
            Enrollment.objects.select_for_update(of=("self",)).filter(
                organization_id=offering.organization_id, offering_id=offering.pk, status=Enrollment.Status.ENROLLED
            )
        )
        desired = {
            "seminar": _desired_kind(organization, seminar, enrolled, "seminar"),
            "lab": _desired_kind(organization, lab, enrolled, "lab"),
        }
        _check_nested(desired, enrolled, offering)
        movers = [
            row
            for row in enrolled
            if any(_new_value(desired, row, kind, field) != getattr(row, field) for kind, field, _m, _l in _KINDS)
        ]
        dirty = {
            kind: desired[kind] is not None and _rows_differ(model, offering, desired[kind], is_lab=is_lab)
            for kind, _field, model, is_lab in _KINDS
        }
        if not (movers or any(dirty.values())):
            return {"changed": False, "students": 0, "sections": 0}
        reason = lab_groups_manage.block_reason(offering)
        if reason:
            raise SectionSetupError("blocked", reason, status=409)
        if not lab_groups_manage.can_manage(user, offering):
            raise SectionSetupError(
                "forbidden", pgettext(_CTX, "Bu jurnalın bölmələrini dəyişməyə icazəniz yoxdur."), status=403
            )
        sections = 0
        for kind, field, model, is_lab in _KINDS:
            spec = desired[kind]
            if spec is None:
                continue
            _check_lessons(offering, field, spec["count"], _label_for(kind, offering))
            if dirty[kind]:
                sections += _sync_rows(model, offering, spec["count"], spec["names"], spec["units"], is_lab=is_lab)
        old = {str(row.pk): [row.seminar_group, row.lab_group] for row in movers}
        now = timezone.now()
        for row in movers:
            row.seminar_group = _new_value(desired, row, "seminar", "seminar_group")
            row.lab_group = _new_value(desired, row, "lab", "lab_group")
            row.updated_at = now
        if movers:
            Enrollment.objects.bulk_update(movers, ["seminar_group", "lab_group", "updated_at"])
        log_action(
            AuditAction.UPDATE,
            user=user,
            organization=offering.organization,
            obj=offering,
            old_values={"students": old},
            new_values={
                kind: (desired[kind]["names"] or desired[kind]["count"]) if desired[kind] is not None else "kept"
                for kind, _f, _m, _l in _KINDS
            }
            | {"students": {str(row.pk): [row.seminar_group, row.lab_group] for row in movers}},
            changes={"verb": "split_wizard_sections", "moved": len(movers), "sections": sections},
            reason=pgettext(_CTX, "Bölgü sehrbazı: seminar alt qrupları və lab qrupları"),
            request=request,
            resource_type=RESOURCE,
            resource_id=str(offering.pk),
        )
    lab_groups.forget(offering)
    seminar_groups.forget(offering)
    return {"changed": True, "students": len(movers), "sections": sections}


__all__ = ["MAX_SECTIONS", "SectionSetupError", "apply_sections", "journal_state", "registry_subgroups"]
