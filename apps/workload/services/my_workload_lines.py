"""«Mənim dərs yüküm» — bölgü sətirlərini FƏNN + QRUP (tapşırıq sətri) üzrə birləşdirir (sahib 2026-10-15).

Sahib: «631/5K-nı birləşdir, 3 ədəd ayrı deyil, məndə birlikdədir … mühazirə seminar birdir». Əvvəl hər
``TeacherAssignment`` ayrıca sətir idi (Mühazirə 30 / Seminar 15 / Laboratoriya 45 — eyni fənn və qrup üç dəfə).
İndi bir tapşırıq sətri = bir xətt, fəaliyyətlər açılışda: «Mühazirə 30 · Seminar 15», saat = cəm (45).

Bölgü sətirləri (``teacher_workload_rows``) DƏYİŞMİR — etiraz hədəfi və cəmlər onlarla işləyir; bu modul yalnız
TƏQDİMAT qatıdır (bölmə cədvəli, JSON ``lines`` və Excel ixracı eyni funksiyanı işlədir).

Redaktə keçidi: aktorun ``workload.distribute`` əhatəsinə düşən kafedranın xəttində «Redaktə et» →
«Yük bölgüsü» redaktoru həmin sətrə fokusla (``row_edit.distribution_edit_url``). Müəllimdə açar yoxdur —
keçid çıxmır (öz kafedrasının müdiri olan müəllimdə çıxır).

Patok (sahib 2026-11-10: «patokları birlikdə yaz, ayrı-ayrı alt-alta yazma»): eyni axının sətirləri
(``patok_lead_id or row_id`` + eyni semestr) BİR xətdir — qruplar «236 BT, 536 T», fəaliyyətlər cəmlənir
(«Mühazirə 15 · Seminar 30»), saat = cəm, hər qrupun jurnalı ayrıca keçid (``journals``). Aparıcı sətir başqa
müəllimdədirsə tərəfdaş sətirlər öz aralarında birləşir. Cəmlər və etirazlar birləşməmiş ``rows`` ilə işləyir.
"""

from __future__ import annotations

from ..constants import Activity, DegreeLevel, EducationForm, Season
from .row_edit import distribution_edit_url

# ⚠️ Etiketlər LAZY qalır (import anında `str()` dili dondururdu — QA-1 F3); mətnə çevirmə çağırış anındadır.
_FORM_LABELS = {str(value): label for value, label in EducationForm.choices}
_LEVEL_LABELS = {str(value): label for value, label in DegreeLevel.choices}
_SEASON_ORDER = {str(value): index for index, (value, _label) in enumerate(Season.choices)}
_ACTIVITY_ORDER = {str(value): index for index, (value, _label) in enumerate(Activity.choices)}


def _label(labels: dict, value: str) -> str:
    """Seçim etiketi AKTİV dildə (çağırış anında); naməlum dəyər — olduğu kimi."""
    label = labels.get(value)
    return str(label) if label is not None else value


def _activity_text(activities: list[dict]) -> str:
    """Tək fəaliyyət — yalnız ad (saat «Saat» sütunundadır); bir neçə — «Mühazirə 30 · Seminar 15»."""
    if len(activities) == 1:
        return activities[0]["label"]
    return " · ".join(f"{item['label']} {item['hours']}" for item in activities)


def group_workload_lines(rows, *, edit_chair_ids=None) -> list[dict]:
    """Bölgü sətirləri → xətlər (tapşırıq sətri başına bir). ``edit_chair_ids`` — redaktə keçidi olan kafedralar."""
    edit_chair_ids = {str(item) for item in (edit_chair_ids or ())}
    lines: dict = {}
    for row in rows:
        key = row.get("row_id") or row.get("id")
        line = lines.get(key)
        if line is None:
            chair_id = str(row.get("chair_id") or "")
            line = lines[key] = {
                "key": key,
                "row_id": row.get("row_id", ""),
                "patok_lead_id": str(row.get("patok_lead_id") or ""),
                "task_id": row.get("task_id", ""),
                "chair_id": chair_id,
                "chair_name": row.get("chair_name", ""),
                "academic_year": row.get("academic_year", ""),
                "season": row.get("season", ""),
                "season_label": row.get("season_label", ""),
                "subject": row.get("subject", ""),
                "groups": row.get("groups", ""),
                "education_form": row.get("education_form", ""),
                "education_form_label": _label(_FORM_LABELS, row.get("education_form", "")),
                "degree_level": row.get("degree_level", ""),
                "degree_level_label": _label(_LEVEL_LABELS, row.get("degree_level", "")),
                "offering_id": row.get("offering_id", ""),
                "is_intensive": bool(row.get("is_intensive")),
                "is_hourly_paid": False,
                "hours": 0,
                "activities": [],
                "assignment_ids": [],
                "edit_url": (
                    distribution_edit_url(
                        chair_id=chair_id, academic_year=row.get("academic_year", ""), row_id=row.get("row_id", "")
                    )
                    if chair_id and chair_id in edit_chair_ids and row.get("row_id")
                    else ""
                ),
            }
        hours = int(row.get("hours") or 0)
        line["hours"] += hours
        line["is_hourly_paid"] = line["is_hourly_paid"] or bool(row.get("is_hourly_paid"))
        line["assignment_ids"].append(row.get("id", ""))
        line["offering_id"] = line["offering_id"] or row.get("offering_id", "")
        same = next((item for item in line["activities"] if item["activity"] == row.get("activity")), None)
        if same is None:
            line["activities"].append(
                {"activity": row.get("activity", ""), "label": row.get("activity_label", ""), "hours": hours}
            )
        else:  # eyni fəaliyyət iki yarımqrupa — bir yerdə
            same["hours"] += hours
    result = _merge_patok_streams(list(lines.values()))
    for line in result:
        line["activities"].sort(key=lambda item: _ACTIVITY_ORDER.get(item["activity"], 99))
        line["activity_label"] = _activity_text(line["activities"])
    result.sort(key=lambda item: (_SEASON_ORDER.get(item["season"], 99), item["subject"].casefold(), item["groups"]))
    return result


def _journal(line: dict) -> list[dict]:
    return [{"offering_id": line["offering_id"], "label": line["groups"]}] if line["offering_id"] else []


def _merge_patok_streams(lines: list[dict]) -> list[dict]:
    """Sətir xətləri → patok axını başına bir xətt (axınsız sətir — olduğu kimi, ``journals`` əlavə olunur)."""
    streams: dict = {}
    for line in lines:
        stream = line.pop("patok_lead_id", "") or line["row_id"] or line["key"]
        streams.setdefault((line["season"], stream), []).append(line)
    merged = []
    for (_season, stream), members in streams.items():
        if len(members) == 1:
            line = members[0]
            line.update(journals=_journal(line), is_patok=False, row_ids=[line["row_id"]] if line["row_id"] else [])
            merged.append(line)
            continue
        # Aparıcı əvvəl, sonra tərəfdaşlar qrup adına görə.
        members.sort(key=lambda item: (item["row_id"] != stream, item["groups"].casefold()))
        head = members[0]
        line = dict(head)
        groups: list[str] = []
        journals: list[dict] = []
        activities: dict = {}
        for member in members:
            if member["groups"] and member["groups"] not in groups:
                groups.append(member["groups"])
            for journal in _journal(member):
                if all(item["offering_id"] != journal["offering_id"] for item in journals):
                    journals.append(journal)
            for item in member["activities"]:
                bucket = activities.setdefault(item["activity"], {**item, "hours": 0})
                bucket["hours"] += item["hours"]
        line.update(
            groups=", ".join(groups),
            activities=list(activities.values()),
            hours=sum(member["hours"] for member in members),
            is_hourly_paid=any(member["is_hourly_paid"] for member in members),
            is_intensive=any(member["is_intensive"] for member in members),
            assignment_ids=[item for member in members for item in member["assignment_ids"]],
            row_ids=[member["row_id"] for member in members if member["row_id"]],
            journals=journals,
            offering_id=journals[0]["offering_id"] if journals else "",
            is_patok=True,
        )
        merged.append(line)
    return merged


__all__ = ["group_workload_lines"]
