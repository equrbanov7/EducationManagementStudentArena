"""Köçürmə-sonrası TƏMİR əmrləri üçün ortaq skelet (2026-09-02 auditi).

Niyə ayrıca səth
----------------
Repetisiya (``legacy_import_rehearse``) BÜTÖV bir run-dur: ledger sətirləri
``run_id``-yə bağlıdır, ``upsert_entity_map`` eyni legacy açar üçün FƏRQLİ
derivation hash-ı ``legacy_entity_identity_conflict`` ilə rədd edir və
``transform_version`` policy-dən törəyir.  Yəni **artıq köçürülmüş hədəfdə
fazaların hədəflənmiş təkrar icrası mümkün deyil** — bu, təsadüf deyil, dizayn
qərarıdır (sübutun toxunulmazlığı).

Ona görə auditin tapdığı qüsurlar iki yerdə bağlanır:

1. **Fazanın qaydası** düzəldilir ki, NÖVBƏTİ tam repetisiya doğru olsun;
2. **Təmir əmri** artıq köçürülmüş hədəfdə həmin qərarı auditli şəkildə geri alır.

Hər təmir əmrinin qapıları (hamısı bu moduldadır)
-------------------------------------------------
* ``--dry-run`` DEFAULT-dur; yazmaq üçün ``--apply`` AÇIQ şəkildə verilməlidir;
* baza ya ``emsarena.rehearsal_target = 'disposable'`` GUC-unu daşımalıdır
  (yəni atılabilən repetisiya nüsxəsidir), ya da operator
  ``--i-know-this-is-production`` bayrağını AÇIQ şəkildə yazmalıdır;
* ``--organization`` ilə tenant məhdudlaşdırılır (default ``myedu-univ``);
* qərar cədvəli həmişə çap olunur (dry-run-da da);
* dəyişən hər sətir üçün ``core.audit.log_action`` yazılır;
* HEÇ NƏ SİLİNMİR və mövcud legacy dəyər üzərinə yazılmır;
* idempotentdir: ikinci icra 0 dəyişiklik göstərməlidir.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.apps import apps as django_apps
from django.core.management.base import CommandError
from django.db import connection

#: ``rehearsal_target_guard`` ilə eyni marker — atılabilən repetisiya bazası.
REPAIR_TARGET_GUC = "emsarena.rehearsal_target"
REPAIR_TARGET_GUC_VALUE = "disposable"

#: Audit sətirlərinin ortaq prefiksi; hər əmr öz şəkilçisini əlavə edir.
AUDIT_REASON_PREFIX = "legacy_repair"

DEFAULT_ORGANIZATION_SLUG = "myedu-univ"


@dataclass(frozen=True)
class RepairContext:
    """Bir təmir icrasının bütün açarları — əmrlər arasında eyni formadadır."""

    organization: object
    actor: object
    apply: bool
    limit: int

    @property
    def mode(self) -> str:
        return "APPLY" if self.apply else "DRY-RUN"


def add_repair_arguments(parser) -> None:
    """Bütün təmir əmrlərinin ORTAQ arqument dəsti."""

    parser.add_argument("--organization", default=DEFAULT_ORGANIZATION_SLUG, help="Tenant slug (default: myedu-univ)")
    parser.add_argument("--apply", action="store_true", help="Dəyişiklikləri YAZ (default: yalnız hesabat)")
    parser.add_argument("--dry-run", action="store_true", help="Açıq dry-run (default davranış)")
    parser.add_argument("--limit", type=int, default=0, help="Ən çox bu qədər sətri emal et (0 = limitsiz)")
    parser.add_argument("--actor", default="", help="Audit aktoru (username); default: təşkilatın sahibi")
    parser.add_argument(
        "--i-know-this-is-production",
        action="store_true",
        help="Repetisiya markeri olmayan bazada icraya AÇIQ icazə (serverdə tələb olunur)",
    )


def database_is_disposable_target() -> bool:
    """Baza ``ALTER DATABASE … SET emsarena.rehearsal_target='disposable'`` daşıyırmı?"""

    if connection.vendor != "postgresql":
        # sqlite yalnız test yoludur: orada real data yoxdur, marker də yoxdur.
        return True
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_setting(%s, true)", [REPAIR_TARGET_GUC])
            row = cursor.fetchone()
    except Exception:
        return False
    return bool(row) and str(row[0] or "").strip() == REPAIR_TARGET_GUC_VALUE


def assert_writable_target(*, allow_production: bool) -> str:
    """Fail-closed: markersiz bazada yazmaq yalnız açıq bayraqla mümkündür."""

    if database_is_disposable_target():
        return "rehearsal_target"
    if allow_production:
        return "production_acknowledged"
    raise CommandError(
        "legacy_repair_target_not_disposable: bazada "
        f"{REPAIR_TARGET_GUC}='{REPAIR_TARGET_GUC_VALUE}' markeri yoxdur. "
        "Bu, real (prod) baza ola bilər — davam etmək üçün --i-know-this-is-production verin."
    )


def resolve_organization(slug: str):
    organization = (
        django_apps.get_model("organizations", "Organization").objects.filter(slug=str(slug or "").strip()).first()
    )
    if organization is None:
        raise CommandError(f"legacy_repair_organization_unknown: {slug!r}")
    return organization


def resolve_actor(organization, username: str):
    """Audit aktoru: açıq verilən istifadəçi, yoxsa təşkilatın sahibi.

    Aktor ``member.edit`` icazəsini daşımalıdır — hesab keçidləri məhz onun
    adından, mövcud qapılardan keçərək edilir.
    """

    user_model = django_apps.get_model("auth", "User")
    username = str(username or "").strip()
    if username:
        actor = user_model._default_manager.filter(username=username).first()
        if actor is None:
            raise CommandError(f"legacy_repair_actor_unknown: {username!r}")
        return actor
    actor = getattr(organization, "owner", None)
    if actor is None:
        actor = user_model._default_manager.filter(is_superuser=True, is_active=True).order_by("pk").first()
    if actor is None:
        raise CommandError("legacy_repair_actor_unavailable: --actor verin")
    return actor


def build_context(options) -> RepairContext:
    """Ortaq arqumentləri bir konteksdə topla və qapıları yoxla."""

    if options.get("apply") and options.get("dry_run"):
        raise CommandError("legacy_repair_mode_conflict: --apply və --dry-run birlikdə verilə bilməz")
    apply_writes = bool(options.get("apply"))
    if apply_writes:
        assert_writable_target(allow_production=bool(options.get("i_know_this_is_production")))
    organization = resolve_organization(options.get("organization"))
    limit = int(options.get("limit") or 0)
    if limit < 0:
        raise CommandError("legacy_repair_limit_invalid")
    return RepairContext(
        organization=organization,
        actor=resolve_actor(organization, options.get("actor")),
        apply=apply_writes,
        limit=limit,
    )


def render_table(headers, rows, *, max_rows: int = 40) -> str:
    """Deterministik, sabit-enli qərar cədvəli (operator gözü üçün)."""

    body = [[("" if cell is None else str(cell)) for cell in row] for row in rows]
    shown = body[:max_rows]
    widths = [len(str(head)) for head in headers]
    for row in shown:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))
    lines = [
        "  ".join(str(head).ljust(widths[index]) for index, head in enumerate(headers)),
        "  ".join("-" * width for width in widths),
    ]
    lines.extend("  ".join(cell.ljust(widths[index]) for index, cell in enumerate(row)) for row in shown)
    if len(body) > len(shown):
        lines.append(f"… və daha {len(body) - len(shown)} sətir (tam siyahı üçün --limit işlədin)")
    return "\n".join(lines)


def render_summary(title: str, context: RepairContext, counters) -> str:
    lines = [
        "",
        f"=== {title} — {context.mode} ===",
        f"Təşkilat: {context.organization.slug}   Aktor: {context.actor.username}",
        "",
    ]
    width = max((len(key) for key in counters), default=0)
    lines.extend(f"  {key.ljust(width)} : {value}" for key, value in counters.items())
    if not context.apply:
        lines.append("")
        lines.append("  (DRY-RUN — heç nə yazılmadı. Yazmaq üçün --apply verin.)")
    return "\n".join(lines)


__all__ = [
    "AUDIT_REASON_PREFIX",
    "DEFAULT_ORGANIZATION_SLUG",
    "REPAIR_TARGET_GUC",
    "REPAIR_TARGET_GUC_VALUE",
    "RepairContext",
    "add_repair_arguments",
    "assert_writable_target",
    "build_context",
    "database_is_disposable_target",
    "render_summary",
    "render_table",
    "resolve_actor",
    "resolve_organization",
]
