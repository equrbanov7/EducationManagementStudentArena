"""Filter descriptors shared with the cabinet filter bar contract."""

from django.utils.translation import pgettext


def filter_fields(filters, courses, organizations, profile):
    def t(text):
        return pgettext("profile.statistics", text)

    if profile in ("student", "restricted"):
        return []
    fields = [
        {"name": "stat_date_from", "label": t("Başlanğıc tarixi"), "kind": "date", "value": filters["date_from"]},
        {"name": "stat_date_to", "label": t("Son tarix"), "kind": "date", "value": filters["date_to"]},
    ]
    for key, label, rows, label_key in (
        ("course", t("Kurs"), courses, "title"),
        ("organization", t("Təşkilat"), organizations, "name"),
    ):
        if rows:
            fields.append(
                {
                    "name": f"stat_{key}",
                    "label": label,
                    "kind": "select",
                    "value": filters[key] or "",
                    "searchable": True,
                    "options": [{"value": "", "label": t("Hamısı")}]
                    + [{"value": str(row["id"]), "label": row[label_key]} for row in rows],
                }
            )
    return fields
