"""«Kadr analitikası» aqreqatları — süzülmüş sətirlərdən (sorğusuz, yaddaşda).

Hər bölgü «fakültə → kafedra» ağacıdır: kafedra sətri + fakültə cəmi + ümumi cəm. Faiz kimi
toplanmayan göstəricilər (doluluq %, icra %) hər səviyyədə ÖZ sətirlərindən yenidən hesablanır —
kafedra faizlərinin ortası DEYİL.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from django.utils.translation import pgettext

from ...models import UserProfile
from ..people.analytics import AGE_BUCKETS, GENDER_LABELS
from . import constants as C


def pct(part, whole) -> float:
    return round(part * 100.0 / whole, 1) if whole else 0.0


def width_class(percent) -> str:
    """Zolaq eni CSS sinfi (5%-lik addım) — inline ``style`` YOXDUR (CSP)."""
    value = max(0.0, min(100.0, float(percent or 0)))
    return f"hr-w-{int(round(value / 5.0) * 5)}"


def _labels() -> dict:
    from apps.workload.public import position_labels

    titles = dict(UserProfile.AcademicTitle.choices)
    degrees = dict(UserProfile.AcademicDegree.choices)
    return {
        "title": {**{key: str(titles[key]) for key in C.TITLE_ORDER}, C.TITLE_NONE: str(C.UNSET_LABEL)},
        "degree": {**{key: str(degrees[key]) for key in C.DEGREE_ORDER}, C.DEGREE_NONE: pgettext(C.CTX, "Yoxdur")},
        "staff": {key: str(label) for key, label in C.STAFF_TYPES},
        "position": position_labels(),
    }


def distribution(counter: Counter, order, labels: dict, total: int) -> list[dict]:
    return [
        {
            "key": key,
            "label": labels.get(key, key),
            "count": counter.get(key, 0),
            "percent": pct(counter.get(key, 0), total),
            "width": width_class(pct(counter.get(key, 0), total)),
        }
        for key in order
    ]


# ── Fakültə → kafedra ağacı ────────────────────────────────────────────────


def tree(rows, metrics) -> dict:
    """``metrics(rows) -> dict`` hər kafedraya, fakültəyə və ümumi cəmə tətbiq olunur."""
    faculties: dict = defaultdict(lambda: {"rows": [], "chairs": defaultdict(list)})
    for row in rows:
        bucket = faculties[(row["faculty"], row["faculty_id"])]
        bucket["rows"].append(row)
        bucket["chairs"][(row["chair"], row["chair_id"])].append(row)

    groups = []
    for (faculty, faculty_id), bucket in faculties.items():
        chairs = [
            {"id": chair_id, "name": chair or str(C.NO_CHAIR_LABEL), **metrics(chair_rows)}
            for (chair, chair_id), chair_rows in bucket["chairs"].items()
        ]
        chairs.sort(key=lambda item: (not item["id"], item["name"].casefold()))
        groups.append(
            {
                "id": faculty_id,
                "name": faculty or str(C.NO_FACULTY_LABEL),
                "chairs": chairs,
                "total": metrics(bucket["rows"]),
            }
        )
    groups.sort(key=lambda item: (not item["id"], item["name"].casefold()))
    return {"groups": groups, "total": metrics(list(rows))}


def staff_metrics(rows) -> dict:
    counter = Counter(row["staff_type"] for row in rows)
    units = sum(row["staff_fraction"] or 0 for row in rows if row["staff_type"] not in (C.STAFF_HOURLY, C.STAFF_NONE))
    return {
        "teachers": len(rows),
        **{key: counter.get(key, 0) for key in C.STAFF_KEYS},
        "units": round(units, 2),
        "staffed": sum(counter.get(key, 0) for key in (C.STAFF_FULL, C.STAFF_HALF, C.STAFF_PARTIAL)),
    }


def composition_metrics(rows) -> dict:
    titles = Counter(row["title"] for row in rows)
    degrees = Counter(row["degree"] for row in rows)
    with_degree = len(rows) - degrees.get(C.DEGREE_NONE, 0)
    return {
        "teachers": len(rows),
        "titles": [titles.get(key, 0) for key in (*C.TITLE_ORDER, C.TITLE_NONE)],
        "phd": degrees.get("phd", 0),
        "dsc": degrees.get("dsc", 0),
        "degree_percent": pct(with_degree, len(rows)),
    }


def workload_metrics(rows) -> dict:
    loaded = [row for row in rows if row["load_band"] != "none"]
    norm = sum(row["norm_hours"] for row in loaded)
    planned = sum(row["planned_load"] for row in loaded)
    bands = Counter(row["load_band"] for row in rows)
    fill = round(planned * 100 / norm) if norm else 0
    return {
        "teachers": len(rows),
        "with_load": len(loaded),
        "norm": norm,
        "planned": planned,
        "hourly_paid": sum(row["hourly_paid_hours"] for row in rows),
        "fill": fill,
        "width": width_class(fill),
        "bands": [bands.get(key, 0) for key, _label in C.LOAD_BANDS],
        "over": bands.get("loaded", 0) + bands.get("risk", 0),
        "under": bands.get("free", 0),
    }


def activity_metrics(rows) -> dict:
    planned = sum(row["planned_hours"] for row in rows)
    held = sum(row["held_hours"] for row in rows)
    done = pct(held, planned)
    return {
        "teachers": len(rows),
        "teaching": sum(1 for row in rows if row["journals"]),
        "journals": sum(row["journals"] for row in rows),
        "lessons": sum(row["lessons"] for row in rows),
        "held": held,
        "planned": planned,
        "done": done,
        "width": width_class(done),
    }


# ── Bölmələr ───────────────────────────────────────────────────────────────


def kpis(rows) -> list[dict]:
    statuses = Counter(row["status"] for row in rows)
    staff = staff_metrics(rows)
    load = workload_metrics(rows)
    total = len(rows)

    def tile(key, label, value, note="", tone=""):
        return {"key": key, "label": label, "value": value, "note": note, "tone": tone}

    return [
        tile("total", pgettext(C.CTX, "Müəllimlər"), total, pgettext(C.CTX, "akademik heyət"), "accent-primary"),
        tile(
            "active",
            pgettext(C.CTX, "Aktiv hesab"),
            statuses.get(C.STATUS_ACTIVE, 0),
            "%s%%" % pct(statuses.get(C.STATUS_ACTIVE, 0), total),
            "accent-success",
        ),
        tile(
            "blocked",
            pgettext(C.CTX, "Dayandırılıb"),
            statuses.get(C.STATUS_BLOCKED, 0) + statuses.get(C.STATUS_ARCHIVED, 0),
            pgettext(C.CTX, "blok + arxiv"),
            "accent-danger",
        ),
        tile(
            "never",
            pgettext(C.CTX, "Heç daxil olmayıb"),
            sum(1 for row in rows if row["never_logged_in"]),
            pgettext(C.CTX, "ilk giriş yoxdur"),
            "accent-warning",
        ),
        tile(
            "initial",
            pgettext(C.CTX, "Aktivləşdirilməyib"),
            sum(1 for row in rows if row["not_activated"]),
            pgettext(C.CTX, "ilkin parolda"),
            "accent-warning",
        ),
        tile(
            "new",
            pgettext(C.CTX, "Bu il yeni"),
            sum(1 for row in rows if row["is_new"]),
            pgettext(C.CTX, "hesab yaradılıb"),
        ),
        tile(
            "staff",
            pgettext(C.CTX, "Ştatlı / saathesabı"),
            f"{staff['staffed']} / {staff[C.STAFF_HOURLY]}",
            pgettext(C.CTX, "ştat vahidi: %(units)s") % {"units": staff["units"]},
        ),
        tile("fill", pgettext(C.CTX, "Yük doluluğu"), f"{load['fill']}%", pgettext(C.CTX, "plan / norma")),
    ]


def composition(rows, *, demographics: bool) -> dict:
    labels = _labels()
    total = len(rows)
    out = {
        "titles": distribution(
            Counter(row["title"] for row in rows), (*C.TITLE_ORDER, C.TITLE_NONE), labels["title"], total
        ),
        "degrees": distribution(
            Counter(row["degree"] for row in rows), (*C.DEGREE_ORDER, C.DEGREE_NONE), labels["degree"], total
        ),
        "title_headers": [labels["title"][key] for key in (*C.TITLE_ORDER, C.TITLE_NONE)],
        "tree": tree(rows, composition_metrics),
        "gender": [],
        "age": [],
        "age_unknown": 0,
    }
    if demographics:
        gender_labels = {key: str(label) for key, label in GENDER_LABELS.items()}
        out["gender"] = distribution(
            Counter(row["gender"] if row["gender"] in gender_labels else "unspecified" for row in rows),
            ("male", "female", "unspecified"),
            gender_labels,
            total,
        )
        ages = Counter()
        for row in rows:
            age = row["age"]
            if age is None:
                continue
            for key, _label, low, high in AGE_BUCKETS:
                if (low is None or age >= low) and (high is None or age <= high):
                    ages[key] += 1
                    break
        out["age"] = distribution(
            ages, [key for key, *_rest in AGE_BUCKETS], {k: str(v) for k, v, *_r in AGE_BUCKETS}, total
        )
        out["age_unknown"] = sum(1 for row in rows if row["age"] is None)
    return out


def workload(rows) -> dict:
    loaded = [row for row in rows if row["load_band"] != "none"]
    over = sorted((row for row in loaded if row["load_band"] in ("loaded", "risk")), key=lambda r: -r["fill_percent"])
    under = sorted((row for row in loaded if row["load_band"] == "free"), key=lambda r: r["fill_percent"])
    return {
        "tree": tree(rows, workload_metrics),
        "band_headers": [str(label) for _key, label in C.LOAD_BANDS],
        "over": over[:10],
        "under": under[:10],
    }


def quality(rows) -> list[dict]:
    out = []
    for key, label in C.ISSUES:
        hits = [row for row in rows if key in row["issues"]]
        out.append(
            {
                "key": key,
                "label": str(label),
                "count": len(hits),
                "critical": key in C.CRITICAL_ISSUES,
                "sample": [row["name"] for row in hits[: C.QUALITY_SAMPLE]],
                "more": max(len(hits) - C.QUALITY_SAMPLE, 0),
            }
        )
    return out


__all__ = [
    "activity_metrics",
    "composition",
    "composition_metrics",
    "distribution",
    "kpis",
    "pct",
    "quality",
    "staff_metrics",
    "tree",
    "width_class",
    "workload",
    "workload_metrics",
]
