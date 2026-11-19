"""Tyutorun «qrup dövrəsi» (sahib 2026-11-19) — tələbə/qrup işlərinin hamısı tyutorun özündə.

Sahibin sözü: «tyutora özəllik olaraq rol ver ki qrupa tələbə əlavə etmək, qruplardan tələbə köçürmək, qrup
yaratmaq … tələbə datasını görməkdən, müəllim qrup-qrup köçürməsi, xarici dildə xarici dil qrupu açmaq, əlavə
tələbə əlavə etmək, lab qrupları yaratmaq, alt qrupları etmək — bütün bu circle-i edə bilsin».

Əməl → açar (tyutorda ARTIQ olanlar ✓, bu modulun verdikləri ＋):

* qrup yaratmaq / tələbə əlavə / qruplar arası köçürmə / ana qrupu bölmək (alt qrup) — ✓ ``unit.group_manage``
  (qrup reyestri; köçürmə rəsmi ``transfer_student_group`` xidməti ilə, DB qapısı dəyişmir);
* jurnala alt qrupdan əlavə tələbə (sənəd məcburi qalır) — ✓ ``journal.roster``;
* tələbə datası — ✓ ``people.view_students`` / ``student.registry_view``; ＋ ``student.records_view``
  (ÜOMG, transkript), ＋ ``people.view_contacts`` / ``people.view_demographics`` (kartda əlaqə, cins/yaş);
* müəllimin qrupdan-qrupa təhvili — ＋ ``journal.reassign`` (əhatə açılışın QRUPU ilə yoxlanır);
* lab qrupları — ＋ YENİ ``journal.lab_groups``: QRUPU aktorun əhatəsində olan jurnalın lab qrupları
  (``registrar.lab_groups_manage.can_manage``). Kafedra müdirinin ``workload.distribute`` açarı QƏSDƏN verilmir —
  o, bütün yük bölgüsünü açardı;
* xarici dil səviyyə qrupu — ＋ YENİ ``journal.level_cohorts``: dil kafedrasında (artıq səviyyə qrupu olan
  kafedra) qrup açmaq və ÖZ açdığı qrupu idarə etmək; tələbə yerləşdirmə / çıxarma yenə yalnız aktorun
  ``journal.roster`` əhatəsindəki tələbələr üçün (``registrar.language_cohorts``).

QƏSDƏN VERİLMƏYƏN: ``student.movement`` (akademik məzuniyyət, xaric, bərpa — dekanlıq / TXM qərarı).

ƏHATƏ: rollar UNIT-dir — yazı əməlləri ``Membership.scope_unit`` alt-ağacı (tyutorda fakültə) ilə qalır.
Tyutor ↔ proqram koordinatoru paritet qrupundadır (``default_roles_role_audit.ROLE_PARITY_GROUPS``) — açarlar
hər ikisinə yazılır. Mövcud tenantlar: miqrasiya ``organizations/0086``.

NİYƏ AYRI MODUL? ``permissions.py`` və ``default_roles_university.py`` ölçü büdcəsinin (600) sərhədindədir:
kataloq ``permissions_role_audit.merge_role_audit_permissions``, şablon ``apply_role_audit_grants`` ilə birləşir.
"""

from django.utils.translation import pgettext_lazy

_PERM_CTX = "organizations.permission.label"

PERM_JOURNAL_LAB_GROUPS = "journal.lab_groups"
PERM_JOURNAL_LEVEL_COHORTS = "journal.level_cohorts"

_TUTOR_CIRCLE_KEYS: tuple[str, ...] = (
    "student.records_view",
    "people.view_contacts",
    "people.view_demographics",
    "journal.reassign",
    PERM_JOURNAL_LAB_GROUPS,
    PERM_JOURNAL_LEVEL_COHORTS,
)

#: Rol adı → verilən açarlar (QƏSDƏN dondurulub; miqrasiya 0086 eyni dəsti sətir-sətir işlədir).
TUTOR_CIRCLE_GRANTS: dict[str, tuple[str, ...]] = {
    "tutor": _TUTOR_CIRCLE_KEYS,
    "program_coordinator": _TUTOR_CIRCLE_KEYS,
}

TUTOR_CIRCLE_PERMISSION_LABELS = {
    PERM_JOURNAL_LAB_GROUPS: pgettext_lazy(_PERM_CTX, "Öz qruplarının jurnallarında lab qruplarını idarə etmək"),
    PERM_JOURNAL_LEVEL_COHORTS: pgettext_lazy(
        _PERM_CTX, "Dil kafedrasında xarici dil səviyyə qrupu açmaq (öz tələbələri üçün)"
    ),
}


def merge_tutor_circle_permissions(categories: dict, permission_labels: dict) -> None:
    """Yeni açarları «journal» kateqoriyasına YERİNDƏ əlavə edir (idempotent)."""
    bucket = categories.setdefault("journal", [])
    for key in TUTOR_CIRCLE_PERMISSION_LABELS:
        if key not in bucket:
            bucket.append(key)
    permission_labels.update(TUTOR_CIRCLE_PERMISSION_LABELS)


def _covered(permissions, key) -> bool:
    return key in permissions or f"{key.split('.', 1)[0]}.*" in permissions or "*" in permissions


def apply_tutor_circle_grants(roles):
    """Rol şablonlarına açarları idempotent əlavə edir (``*`` / prefiks wildcard daşıyana toxunmur)."""
    for role in roles:
        permissions = role.setdefault("permissions", [])
        for key in TUTOR_CIRCLE_GRANTS.get(role.get("name"), ()):
            if not _covered(permissions, key):
                permissions.append(key)
    return roles


__all__ = [
    "PERM_JOURNAL_LAB_GROUPS",
    "PERM_JOURNAL_LEVEL_COHORTS",
    "TUTOR_CIRCLE_GRANTS",
    "TUTOR_CIRCLE_PERMISSION_LABELS",
    "apply_tutor_circle_grants",
    "merge_tutor_circle_permissions",
]
