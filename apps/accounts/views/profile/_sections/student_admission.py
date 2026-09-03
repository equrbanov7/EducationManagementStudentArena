"""Ekran 08 «Tələbə qəbulu — ATİS və qrup təyinatı» — bölmə context-i.

BACKEND TƏKRAR YAZILMIR. Bütün idxal maşını (şablon, oxuma, quru icra, tətbiq,
audit) mövcud ``apps.accounts.services.intake`` paketindədir və 26 testlə
qorunur (``PHASE1_STUDENT_INTAKE.md``). Bu bölmə həmin maşının ÜSTÜNƏ ekran
08-in tələb etdiyi qatı qoyur:

* 4 addımlı stepper (``core.ui.status_catalog`` → ``intake_steps``);
* KPI zolağı (Cəmi sətir · Yoxlamadan keçdi · Bloklayan xəta · Xəbərdarlıq);
* ATİS sütunları (ixtisas kodu, bal, imtahan növü, forma, maliyyələşmə) —
  ``intake.spec``-ə OPSİONAL olaraq əlavə edilib, köhnə fayl pozulmur;
* qrup təyinatı addımı (avtomatik təklif + əl ilə dəyişmə + yeni qrup).

⚠️ KÖHNƏ AÇAR SAXLANILIR: ``student-intake`` bölməsi olduğu kimi işləyir
(link, test və sidebar girişi qırılmır). ``student-admission`` onun
GENİŞLƏNDİRİLMİŞ görünüşüdür və eyni endpoint-lərə gedir.
"""

from __future__ import annotations

from django.urls import reverse
from django.utils.translation import pgettext

from core.ui import status_catalog

from .student_intake import build_student_intake_section

_CTX = "accounts.student_admission"

#: Ekran 08-in ATİS sütunları — «Sütunlar» panelində ayrıca qrup kimi göstərilir.
ATIS_COLUMN_KEYS = ("atis_id", "program_code", "admission_score", "exam_type", "education_form", "funding")


def _steps() -> list:
    """4 addımlı stepper — etiketlər status kataloqundan (TƏK mənbə)."""
    notes = {
        "uploaded": pgettext(_CTX, "Tələbə Xidmətləri Mərkəzi"),
        "checked": pgettext(_CTX, "Bloklayan xəta olan sətir qrupa təyin edilə bilmir"),
        "distributed": pgettext(_CTX, "İxtisas kodu ilə fakültəyə düşür"),
        "assigned": pgettext(_CTX, "Avtomatik təklif — əl ilə dəyişilə bilər"),
    }
    return [
        {
            "label": str(status.label),
            "note": notes.get(status.key, ""),
            "state": "current" if index == 0 else "todo",
            "key": status.key,
        }
        for index, status in enumerate(status_catalog.family("intake_steps"))
    ]


def build_student_admission_section(request, section, *, active_organization, allowed_sections, active_section):
    """«Tələbə qəbulu» bölməsi (yerində mutasiya)."""
    if "student-admission" not in allowed_sections or active_section != "student-admission":
        return

    # Baza çərçivə (icazə + endpoint-lər + sütunlar) MÖVCUD qurucudan gəlir;
    # `allowed_sections`/`active_section` müvəqqəti olaraq köhnə açarla ötürülür
    # ki, o funksiyanın qapısı dəyişməsin (davranış eynidir).
    build_student_intake_section(
        request,
        section,
        active_organization=active_organization,
        allowed_sections={"student-intake"},
        active_section="student-intake",
    )
    if not section.get("has_access"):
        section["access_denied_message"] = pgettext(
            _CTX, "Tələbə qəbulu üçün icazəniz yoxdur — `user.import` açarı tələb olunur."
        )
        return

    from apps.accounts.services import people

    actor = people.resolve_actor(request)
    section["can_assign_groups"] = bool(actor.can_assign_groups)
    section["create_group_url"] = reverse("accounts:student_admission_create_group")
    section["steps"] = _steps()
    section["steps_label"] = pgettext(_CTX, "Qəbul axınının addımları")
    section["atis_columns"] = [column for column in section.get("columns", []) if column["key"] in ATIS_COLUMN_KEYS]
    section["base_columns"] = [column for column in section.get("columns", []) if column["key"] not in ATIS_COLUMN_KEYS]
    section["kpi_tiles"] = [
        {"label": pgettext(_CTX, "CƏMİ SƏTİR"), "value": 0, "key": "total"},
        {"label": pgettext(_CTX, "YOXLAMADAN KEÇDİ"), "value": 0, "key": "ok"},
        {"label": pgettext(_CTX, "BLOKLAYAN XƏTA"), "value": 0, "key": "blocking", "tone": "danger"},
        {"label": pgettext(_CTX, "XƏBƏRDARLIQ"), "value": 0, "key": "warning", "tone": "warning"},
    ]
    # Form atributları YALNIZ serverdən gəlir (şablon müqaviləsi).
    section["group_form_data"] = {"data-sa-group-form": "1"}
    section["intro"] = pgettext(
        _CTX,
        "ATİS-dən gələn qəbul siyahısı yüklənir, sistem sətirləri yoxlayır "
        "(FİN təkrarı, ixtisas kodunun uyğunluğu, sənəd tamlığı), sonra tələbələr "
        "ixtisasın qruplarına təyin edilir. Qrup təklifi avtomatikdir — dil bölməsi "
        "və boş yerə görə; operator onu dəyişə bilər.",
    )


__all__ = ["ATIS_COLUMN_KEYS", "build_student_admission_section"]
