"""Monitorinq şöbəsi rolları — tədris prosesinə YALNIZ-OXU, bütün təşkilat üzrə (sahib 2026-11-19).

Sahib: «Monitorinq şöbəsinə jurnallara, sillabuslara, fənn qovluqlarına FULL baxmaq icazəsi ver. Dərs cədvəlinə,
cədvəl idarəetməsinə baxmaq icazəsi olsun … monitorinq zamanı nəyə ehtiyac olarsa. Keçilmiş dərslərə və s.»

Əvvəl şöbənin müdiri ``admin_unit_head`` idi (UNIT əhatəsi, öz şöbəsi) — akademik səthlərdən heç nə görmürdü.

──────────────────────────────────────────────────────────────────────────────
Rollar
──────────────────────────────────────────────────────────────────────────────
* ``monitoring_head`` — «Monitorinq şöbəsinin müdiri» (səviyyə 70);
* ``monitoring_staff`` — «Monitorinq şöbəsinin əməkdaşı» (səviyyə 60).

Hər ikisi EYNİ dəsti daşıyır və dəstdə **bir dənə də yazma açarı yoxdur** (``*.edit`` / ``*.manage`` / ``*.approve``
/ ``*.input`` …). Yeganə istisna bütün heyət rollarına avtomatik verilən ``application.create``-dir («Müraciətlərim» —
öz ərizəsini göndərmək; ``default_roles_university._grant_application_permissions``).

⚠️ SƏVİYYƏLƏR 80-dən AŞAĞIDIR QƏSDƏN: ``core.roles.ProfileRole`` ``level >= 80`` olan rola implicit ``org_admin``
aliası verir (tenant idarəetməsi). ORGANIZATION əhatəlidirlər: ``get_permission_scope`` açarı daşıyan ORGANIZATION
roluna ORG-WIDE nəticə verir (səviyyəyə baxmır); üzvlükdə ``scope_unit`` («Monitorinq şöbəsi») saxlanılır, amma
əhatəni DARALTMIR — yalnız üzv reyestrində şöbəsini göstərir.

──────────────────────────────────────────────────────────────────────────────
Açar → səth (hamısı yalnız oxu; yazı endpoint-ləri öz yazma açarını ayrıca tələb edir)
──────────────────────────────────────────────────────────────────────────────
* ``journal.view`` — jurnal siyahısı + istənilən jurnal + xlsx ixracı (``journal_access.can_open_journal``);
  ``grade.view`` — jurnaldakı bal/davamiyyət oxusu.
* ``journal.lessons_unit`` — «Keçilmiş dərslər»in nəzarət görünüşü (``lessons_log.supervision_q``).
* ``syllabus.view`` — «Sillabuslar» (siyahı + önizləmə + PDF; ``syllabus.services.scoping.can_view``).
* ``subject_folder.view_unit`` — «Kafedra materialları»: fənn qovluqlarının dərc edilmiş materialları.
* ``schedule.view`` — «Cədvəl idarəetməsi» YALNIZ-OXU (qrup / müəllim üzrə həftəlik cədvəl; yazı ``schedule.manage``).
* ``people.view_teachers`` / ``people.view_students`` — müəllim və tələbə siyahıları (kontakt / demoqrafik sütunsuz).
* ``unit.view`` — struktur, kafedra profili, «Qruplar»; ``catalog.view`` — ixtisaslar + fənn kataloqu.
* ``plan.view`` / ``semester.view`` — tədris planı və semestr açılışı (oxu).
* ``workload.view`` / ``workload.report`` — dərs yükü icmalı (oxu).
* ``analytics.view_all`` / ``analytics.view_unit`` — analitika; ``student.records_view`` — akademik qeydlər;
  ``student.registry_view`` — tələbə reyestri (oxu + ixrac).

Qəyyum dəstindən (``default_roles_oversight``) QƏSDƏN götürülməyənlər: ``audit.*``, ``accounting.view``,
``application.view_all``, ``people.hr_analytics``, ``people.view_contacts``, ``people.view_demographics``,
``role.view``, ``survey.results.view``, ``user.search`` (RİM mərkəzi — hesab idarəsi səthidir) və ``exam.view``
(imtahan səthi monitorinqin işi deyil; üstəlik şablon ``exam.view`` daşıyana ``appeal.create`` yazma açarı əlavə edir).

Mövcud tenantlar: miqrasiya ``organizations/0085`` (rollar + «Monitorinq» bölməsindəki üzvlüklərin köçürülməsi).
"""

from __future__ import annotations

from core.constants import RoleScopeType

MONITORING_HEAD_ROLE = "monitoring_head"
MONITORING_STAFF_ROLE = "monitoring_staff"

#: Monitorinq şöbəsinin YALNIZ-OXU dəsti — iki rol üçün EYNİ. Yazma açarı əlavə ETMƏYİN (test kilidləyir).
MONITORING_READ_PERMISSIONS = (
    "unit.view",
    "member.view",
    "catalog.view",
    "course.view",
    "schedule.view",
    "syllabus.view",
    "subject_folder.view_unit",
    "journal.view",
    "journal.lessons_unit",
    "grade.view",
    "group.view",
    "people.view_teachers",
    "people.view_students",
    "plan.view",
    "semester.view",
    "workload.view",
    "workload.report",
    "analytics.view_all",
    "analytics.view_unit",
    "student.records_view",
    "student.registry_view",
)

MONITORING_ROLES = [
    {
        "name": MONITORING_HEAD_ROLE,
        "display_name": "Monitorinq şöbəsinin müdiri",
        "level": 70,
        "scope_type": RoleScopeType.ORGANIZATION,
        "permissions": list(MONITORING_READ_PERMISSIONS),
        "description": "Monitoring department head — organization-wide read-only view of the teaching process",
    },
    {
        "name": MONITORING_STAFF_ROLE,
        "display_name": "Monitorinq şöbəsinin əməkdaşı",
        "level": 60,
        "scope_type": RoleScopeType.ORGANIZATION,
        "permissions": list(MONITORING_READ_PERMISSIONS),
        "description": "Monitoring department staff — organization-wide read-only view of the teaching process",
    },
]

__all__ = [
    "MONITORING_HEAD_ROLE",
    "MONITORING_READ_PERMISSIONS",
    "MONITORING_ROLES",
    "MONITORING_STAFF_ROLE",
]
