"""«Semestr açılışı» → «Semestr hazırlığı» paneli — GLUE qatı (sahib 2026-10-03).

Məntiq ``apps.registrar.semester_readiness``-dədir; burada yalnız şablon forması: kafedra cədvəlinin
sətirləri (rəqəm = süzgəc linki: həmin kafedra + problem), açılış sətrindəki problem nişanları və
«Problem» süzgəc sahəsi.
"""

from __future__ import annotations

from urllib.parse import urlencode

from django.urls import reverse
from django.utils.translation import pgettext

_CTX = "accounts.semester"

ISSUE_CELL_TEMPLATE = "accounts/profile/sections/teaching_office/_offering_issues.html"


def issue_labels() -> dict:
    return {
        "no_teacher": pgettext(_CTX, "Müəllim yoxdur"),
        "no_syllabus": pgettext(_CTX, "Sillabus yoxdur"),
        "no_schedule": pgettext(_CTX, "Cədvəl yoxdur"),
        "no_journal": pgettext(_CTX, "Jurnal yazılmır"),
    }


def issue_short_labels() -> dict:
    """Sətir nişanı üçün qısa ad (tam ad ``title``-dadır) — dar sütunda sətir hündürləşməsin."""
    return {
        "no_teacher": pgettext(_CTX, "Müəllim"),
        "no_syllabus": pgettext(_CTX, "Sillabus"),
        "no_schedule": pgettext(_CTX, "Cədvəl"),
        "no_journal": pgettext(_CTX, "Jurnal"),
    }


def issue_cell(issues: list) -> dict:
    labels, short = issue_labels(), issue_short_labels()
    return {
        "include": ISSUE_CELL_TEMPLATE,
        "nowrap": True,
        "issues": [{"key": key, "label": labels[key], "short": short[key]} for key in issues],
    }


def issue_filter_field(value: str) -> dict:
    options = [{"value": "", "label": pgettext(_CTX, "Hamısı")}]
    options += [{"value": key, "label": label} for key, label in issue_labels().items()]
    return {
        "name": "sm_issue",
        "label": pgettext(_CTX, "Problem"),
        "kind": "select",
        "value": value,
        "options": options,
    }


def readiness_context(readiness: dict, base_params: dict) -> dict:
    """Kafedra sətirləri: hər problem sayı «həmin kafedra + problem» süzgəcinə linkdir."""
    profile_url = reverse("accounts:profile")
    keep = {key: value for key, value in base_params.items() if value not in ("", None)}
    keep.pop("sm_page", None)

    def link(chair_id: str, issue: str) -> str:
        return f"{profile_url}?{urlencode({**keep, 'sm_chair': chair_id, 'sm_issue': issue})}"

    rows = []
    for row in readiness.get("rows", []):
        rows.append(
            {
                **row,
                "name": row["name"] or pgettext(_CTX, "Kafedrası yazılmayıb"),
                "tone": "full" if row["pct"] >= 80 else "half" if row["pct"] >= 40 else "low",
                "cells": [
                    {"key": key, "value": row[key], "url": link(row["chair_id"], key) if row["chair_id"] else ""}
                    for key in issue_labels()
                ],
            }
        )
    return {"rows": rows, "totals": readiness.get("totals", {}), "labels": issue_labels()}


__all__ = ["issue_cell", "issue_filter_field", "issue_labels", "issue_short_labels", "readiness_context"]
