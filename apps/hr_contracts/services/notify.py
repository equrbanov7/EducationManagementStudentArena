"""Bildirişlər — in-app + e-poçt, tranzaksiya COMMIT olandan SONRA və BEST-EFFORT (xəta yazını sındırmır).

* «Müqavilə göndərildi» → işçiyə: «Yeni əmək müqaviləniz e-poçtunuza göndərilib. Sistemə daxil olub tanış olduğunuzu
  təsdiqləyin.» (link: «Müqavilələrim»). İmzalı nüsxə / HR-a təhvil addımı YOXDUR (sahib 2026-10-19) — işçinin
  sistemdəki «Tanış oldum, təsdiqləyirəm» təsdiqi axının SON addımıdır.
* İşçi təsdiqlədi → müqaviləni GÖNDƏRƏN HR istifadəçisinə.
* Bitmə xatırlatması / müddəti bitdi → işçiyə və əhatəsi işçinin bölməsini örtən ``hr.contracts_manage``
  daşıyıcılarına (ORGANIZATION rolu hamısını alır; açar ROL şablonunda AÇIQ yazılmalıdır — ``*`` daşıyan rektor və
  s. hər xatırlatmada spam almasın deyə daxil edilmir, ``registrar.retake_notify`` ilə eyni qayda).

E-poçt ``core.email_tasks.send_template_email_async`` (Celery, M365 backend) ilə HƏR alıcıya ayrıca gedir
(alıcılar bir-birini görmür); «Sistem tənzimləmələri» → ``hr.contract_email_enabled`` söndürülübsə yalnız in-app.
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.urls import reverse
from django.utils import formats
from django.utils.translation import pgettext

from core.constants import RoleScopeType
from core.permissions import has_permission

from ..constants import CTX, EMPLOYEE_SECTION, HR_SECTION, PERM_MANAGE
from .access import staff_memberships
from .queries import email_enabled

logger = logging.getLogger(__name__)

EMAIL_TEMPLATE = "hr_contracts/emails/contract_notice.html"
NOTIFICATION_TYPE = "system"


def section_link(section: str, **params) -> str:
    from urllib.parse import quote

    query = "".join(f"&{key}={quote(str(value), safe='')}" for key, value in params.items() if value)
    return f"{reverse('accounts:profile')}?section={section}{query}"


def person_name(user) -> str:
    if user is None:
        return ""
    return (user.get_full_name() or "").strip() or user.username


def _date(value) -> str:
    return formats.date_format(value, "d.m.Y") if value else "—"


def hr_recipients(contract, *, exclude=()) -> list:
    """``hr.contracts_manage`` AÇIQ yazılmış aktiv rollar; UNIT rolu yalnız işçinin bölməsini örtürsə."""
    unit = contract.unit
    from core.rls import bypass_rls

    seen, users = set(exclude), []
    with bypass_rls():  # sorğu açıq təşkilat süzgəcli; RLS kontekstindən asılı olmasın (rəy A6)
        rows = list(
            staff_memberships(contract.organization).select_related("user", "role", "scope_unit").order_by("user_id")
        )
    for membership in rows:
        if membership.user_id in seen:
            continue
        permissions = [entry for entry in (membership.role.permissions or []) if entry != "*"]
        if not has_permission(permissions, PERM_MANAGE):
            continue
        scope_type = membership.role.scope_type
        if scope_type == RoleScopeType.UNIT:
            scope_unit = membership.scope_unit
            if unit is None or scope_unit is None:
                continue
            if not (unit.pk == scope_unit.pk or (unit.path or "").startswith(f"{scope_unit.path}/")):
                continue
        elif scope_type != RoleScopeType.ORGANIZATION:
            continue
        seen.add(membership.user_id)
        users.append(membership.user)
    return users


def _send(*, recipients, title: str, message: str, link: str, contract, kind: str, email_lines=None):
    """Alıcılar ÇAĞIRIŞ anında həll olunmuş siyahıdır (rəy A6); bildiriş və e-poçt yalnız COMMIT-dən sonra gedir.

    Əvvəl alıcılar ``on_commit`` callback-inin İÇİNDƏ sorğulanırdı — ``RLS_TRANSACTION_SCOPED`` rejimində tenant GUC-u
    commit ilə sıfırlandığı üçün üzvlük sorğusu boş qayıdırdı və HR bildiriş almırdı.
    """
    recipients = [user for user in recipients if user is not None]
    if not recipients:
        return
    transaction.on_commit(lambda: _deliver(recipients, title, message, link, contract, kind, email_lines))


def _deliver(recipients, title, message, link, contract, kind, email_lines):
    try:
        from apps.notifications.public import create_notification_for_users

        create_notification_for_users(
            recipients=recipients,
            title=title[:255],
            message=message[:2000],
            link=link,
            notification_type=NOTIFICATION_TYPE,
            metadata={"hr_contract_id": str(contract.pk), "kind": kind},
            organization=contract.organization,
        )
    except Exception:  # noqa: BLE001 — bildiriş heç vaxt əsas yazını sındırmır
        logger.warning("HR contract in-app notification failed (%s).", kind, exc_info=True)
    if email_enabled():
        _email(recipients, title=title, lines=email_lines or [message], link=link, kind=kind)


def _email(recipients, *, title: str, lines, link: str, kind: str) -> None:
    from core.utils import build_absolute_url

    try:
        from core.email_tasks import send_template_email_async

        url = build_absolute_url(link)
        for user in recipients:
            address = (getattr(user, "email", "") or "").strip()
            if "@" not in address:
                continue
            send_template_email_async.delay(
                subject=title[:200],
                template_name=EMAIL_TEMPLATE,
                context={"heading": title, "name": person_name(user), "lines": list(lines), "url": url},
                recipient_list=[address],
            )
    except Exception:  # noqa: BLE001 — növbə/SMTP əlçatmazdırsa in-app bildiriş yenə qalır
        logger.warning("HR contract e-mail enqueue failed (%s).", kind, exc_info=True)


# ── Hadisələr ────────────────────────────────────────────────────────────────


def contract_sent(contract) -> None:
    def _go():
        title = pgettext(CTX, "Yeni əmək müqaviləniz göndərildi")
        message = pgettext(
            CTX, "Yeni əmək müqaviləniz e-poçtunuza göndərilib. Sistemə daxil olub tanış olduğunuzu təsdiqləyin."
        )
        lines = [
            message,
            pgettext(CTX, "Müqavilə № {number} · {position}").format(
                number=contract.number, position=contract.position or "—"
            ),
        ]
        if contract.sent_note:
            lines.append(contract.sent_note)
            message = f"{message} {contract.sent_note}"
        _send(
            recipients=[contract.employee],
            title=title,
            message=message,
            link=section_link(EMPLOYEE_SECTION),
            contract=contract,
            kind="sent",
            email_lines=lines,
        )

    _go()  # alıcılar və mətnlər İNDİ (cari RLS kontekstində) həll olunur; çatdırılma — commit-dən sonra


def contract_acknowledged(contract) -> None:
    def _go():
        if contract.sent_by_id is None or contract.sent_by_id == contract.employee_id:
            return
        name = person_name(contract.employee)
        title = pgettext(CTX, "Müqavilə təsdiqləndi: {name}").format(name=name)
        message = pgettext(CTX, "{name} № {number} əmək müqaviləsi ilə tanış olduğunu təsdiqlədi.").format(
            name=name, number=contract.number
        )
        if contract.acknowledge_note:
            message = f"{message} {contract.acknowledge_note}"
        _send(
            recipients=[contract.sent_by],
            title=title,
            message=message,
            link=section_link(HR_SECTION, hrc_q=contract.number),
            contract=contract,
            kind="acknowledged",
        )

    _go()  # alıcılar və mətnlər İNDİ (cari RLS kontekstində) həll olunur; çatdırılma — commit-dən sonra


def _days_text(left: int) -> str:
    if left <= 0:
        return pgettext(CTX, "bu gün bitir")
    return pgettext(CTX, "bitməsinə {days} gün qalıb").format(days=left)


def expiry_reminder(contract, *, left: int) -> None:
    def _go():
        name = person_name(contract.employee)
        when = _days_text(left)
        end = _date(contract.end_date)
        employee_title = pgettext(CTX, "Əmək müqavilənizin müddəti bitir")
        employee_message = pgettext(
            CTX,
            "№ {number} əmək müqavilənizin {when} (bitmə tarixi: {end}). Ətraflı məlumat üçün Kadrlar şöbəsinə müraciət edin.",
        ).format(number=contract.number, when=when, end=end)
        _send(
            recipients=[contract.employee],
            title=employee_title,
            message=employee_message,
            link=section_link(EMPLOYEE_SECTION),
            contract=contract,
            kind="reminder",
        )
        hr_title = pgettext(CTX, "Müqavilə müddəti bitir: {name}").format(name=name)
        hr_message = pgettext(CTX, "{name} — «{position}», № {number}: {when} (bitmə tarixi: {end}).").format(
            name=name, position=contract.position or "—", number=contract.number, when=when, end=end
        )
        _send(
            recipients=hr_recipients(contract, exclude={contract.employee_id}),
            title=hr_title,
            message=hr_message,
            link=section_link(HR_SECTION, hrc_q=contract.number),
            contract=contract,
            kind="reminder",
        )

    _go()  # alıcılar və mətnlər İNDİ (cari RLS kontekstində) həll olunur; çatdırılma — commit-dən sonra


def expired_notice(contract) -> None:
    def _go():
        name = person_name(contract.employee)
        end = _date(contract.end_date)
        _send(
            recipients=[contract.employee],
            title=pgettext(CTX, "Əmək müqavilənizin müddəti bitdi"),
            message=pgettext(
                CTX, "№ {number} əmək müqavilənizin müddəti {end} tarixində bitib. Kadrlar şöbəsinə müraciət edin."
            ).format(number=contract.number, end=end),
            link=section_link(EMPLOYEE_SECTION),
            contract=contract,
            kind="expired",
        )
        _send(
            recipients=hr_recipients(contract, exclude={contract.employee_id}),
            title=pgettext(CTX, "Müqavilənin müddəti bitdi: {name}").format(name=name),
            message=pgettext(
                CTX, "{name} — «{position}», № {number}: müddəti {end} tarixində bitib, yenilənməyib."
            ).format(name=name, position=contract.position or "—", number=contract.number, end=end),
            link=section_link(HR_SECTION, hrc_q=contract.number),
            contract=contract,
            kind="expired",
        )

    _go()  # alıcılar və mətnlər İNDİ (cari RLS kontekstində) həll olunur; çatdırılma — commit-dən sonra


__all__ = [
    "contract_acknowledged",
    "contract_sent",
    "expired_notice",
    "expiry_reminder",
    "hr_recipients",
    "person_name",
    "section_link",
]
