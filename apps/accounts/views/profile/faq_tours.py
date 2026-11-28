"""Rol üzrə menyu videolarının məzmunu və kabinet bölmələrinə zaman keçidləri."""

import json
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlencode

from django.urls import reverse


@lru_cache(maxsize=1)
def tour_catalog():
    return json.loads(Path(__file__).with_name("faq_tours.json").read_text(encoding="utf-8"))


def tour_key(role):
    return "tour-" + role.replace("_", "-")


def tour_rows():
    if "lab_assistant" in tour_catalog():
        yield (
            "laborant-journal",
            "Laborant öz jurnalını və kafedranın elektron jurnalını necə açır?",
            "Laborantın elektron jurnalı",
            "",
            "Elektron jurnalı aç",
            "laborant-journal",
            (
                "Sol menyuda «Elektron jurnal»ı açın. Tədris ilini və dövrü seçin. Özünüzə təyin olunmuş fənnin jurnalına keçin.",
                "«Qiymətləndirmə», «Midterm» və «Yekun qiymət» tablarına baxın. Əvvəlki dövrdə həmin fənnin qiymətləndirmə sxeminə uyğun «Kollokvium», «Kurs işi» və «Sərbəst iş» də görünə bilər.",
                "Kafedrada baxışınıza açılan başqa müəllimin jurnalını seçin. Tarix sütununu basıb günün dərsini və qeydlərini oxuyun. Dərs yazmaq üçün öz təyinatınızı və jurnalın cari dövrünü yoxlayın.",
            ),
            "laborant elektron jurnal kafedra baxış keçmiş semestr kurs işi sərbəst iş yekun kollokvium midterm",
            ("tour_member_lab_assistant",),
        )
        yield (
            "laborant-department",
            "Laborant keçilmiş dərsi, lab qrupunu, kafedra materialını və sillabusu haradan açır?",
            "Laborantın kafedra menyusu",
            "lessons-log",
            "Keçilmiş dərsləri aç",
            "laborant-department",
            (
                "«Keçilmiş dərslər»də fənni tapın, uyğun sətri açın və nəticəni CSV kimi endirin.",
                "«Lab qrupları»nda jurnalı seçin. Laboratoriya alt qrupunu yaradın, tələbəni köçürün və saxlanan siyahını yoxlayın.",
                "«Kafedra materialları»nda fənnin mövzusunu açın. Özünüzə təyin olunmuş fənnin təsdiqlənmiş sillabusuna sillabus siyahısından keçin. Baxışınıza açılan digər müəllimin təsdiqli sillabusunu həmin fənnin jurnalından aça bilərsiniz.",
            ),
            "laborant dərslər CSV elektron jurnal altqrup köçürmək kafedra material mövzu sillabus",
            ("tour_member_lab_assistant",),
        )
        yield (
            "laborant-components",
            "Laborant qiymətləndirmə pəncərəsində midterm, kurs işi və sərbəst iş balını necə yazır?",
            "Laborantın qiymətləndirmə tabları",
            "",
            "Elektron jurnalı aç",
            "laborant-components",
            (
                "Özünüzə təyin olunmuş fənnin jurnalını və uyğun dövrü seçin. Açıq qiymətləndirmə pəncərəsində tələbənin sətrini tapın.",
                "Müvafiq «Midterm», «Kurs işi» və ya «Sərbəst iş» tabını açın. Tələbənin balını daxil edin və saxlayın. Fənnin sxemində olan tablardan istifadə edin.",
                "Jurnalı təkrar açıb tələbənin sətrində saxlanmış balı yoxlayın. Başqa müəllimin yalnız baxış üçün açılan jurnalında yazı imkanını öz jurnalınızla müqayisə edin.",
            ),
            "laborant kurs işi sərbəst iş midterm bal yazmaq qiymətləndirmə pəncərəsi saxlamaq",
            ("tour_member_lab_assistant",),
        )
    for role, item in tour_catalog().items():
        label = item["label"]
        yield (
            tour_key(role),
            f"{label} kabinetində menyu və tablardan necə istifadə edim?",
            f"{label} üçün video",
            "",
            "",
            tour_key(role),
            (
                "«Videoda mövzuya keç»i açın və sol menyuda istifadə etmək istədiyiniz bölməni seçin.",
                "Seçilən vaxtda bölmənin açılışını izləyin. Alt bölmələri ayrıca seçmək üçün tabın adının yanındakı vaxta basın.",
            ),
            label + " rolum kabinetim menyu bölmə tab video təlimat vəzifə",
            ("tour_member_" + role,),
        )


def active_tour_roles(request):
    """Active tenant roles in primary order, including custom roles without a stock tour."""
    from .faq_editor_catalog import memberships

    org = getattr(request, "organization", None)
    if (
        not org
        or not getattr(org, "is_active", True)
        or getattr(org, "status", "active") != "active"
        or not request.user.is_authenticated
        or not request.user.is_active
    ):
        return {}
    if request.user.is_superuser:
        return {"rehber": tour_catalog()["rehber"]["label"]} if "rehber" in tour_catalog() else {}
    roles = {}
    aliases = {"student": "telebe", "teacher": "muellim"}
    for membership in memberships(request):
        role = membership.role
        if not role.is_active or role.organization_id != org.pk or membership.organization_id != org.pk:
            continue
        name = aliases.get(role.name, role.name)
        label = tour_catalog().get(name, {}).get("label") or getattr(role, "display_name", "") or role.name
        roles.setdefault(name, label)
    return roles


def tour_roles(request):
    return tuple(name for name in active_tour_roles(request) if name in tour_catalog())


def tour_capabilities(request):
    return {"tour_member_" + name: True for name in tour_roles(request)}


def guide_url(key, start=None):
    query = {"section": "faq", "faq_guide": key}
    if start is not None:
        query["faq_at"] = start
    return reverse("accounts:profile") + "?" + urlencode(query) + "#faq-guide"
