"""``add_legacy_guest_students_20261109`` — köhnə sistemin jurnalında iştirakı/balı olan, yeni sistemdə həmin fənnə
yazılmayan tələbəni alt qrupdan həmin jurnala əlavə et (sahib 2026-11-09: «köhnədə ie/balı varsa jurnalda görünməlidir»).

Plan (``legacy-guests/1``, şifrəli release ilə gəlir, YALNIZ FİN/ad + açılış id-si):
``{"format": "legacy-guests/1", "items": [{"offering": "<uuid>", "fin": "...", "name": "Soyad Ad", "reason": "..."}]}``.
Tələbə əvvəl FİN-lə, FİN yoxdursa təşkilatın tələbə üzvləri arasında «Soyad Ad» ilə (yalnız TƏK uyğunluq) tapılır;
əlavə :func:`apps.registrar.guest_roster.add_guest_student` ilə (eyni qapılar: siyahı açıq, aktiv akademik qeyd, eyni
fənn üzrə başqa jurnalda aktiv deyil — əks halda sətir ATLANIR, birləşmə edilmir). Defolt dry-run (eyni kod, geri
qaytarılır); stdout-a YALNIZ saylar (``legacy_guests: açar=say``). Geri qaytarma: jurnaldan çıxarma (RİM) — audit izi
``registrar.guest_roster`` sətirlərindədir.
"""

from __future__ import annotations

import json
from collections import Counter

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.person_names import name_key
from core.rls import apply_rls_request_context, bypass_rls
from core.rls_pooling import rls_worker_atomic

FORMAT = "legacy-guests/1"
PREFIX = "legacy_guests:"
MAX_ITEMS = 2000


def _norm(text) -> str:
    return " ".join(name_key(text or "").split()[:2])


def load_plan(path: str) -> list:
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        raise CommandError("legacy_guests_file_unreadable") from None
    if not isinstance(data, dict) or data.get("format") != FORMAT or not isinstance(data.get("items"), list):
        raise CommandError("legacy_guests_format_unknown")
    items = data["items"]
    if not items or len(items) > MAX_ITEMS:
        raise CommandError("legacy_guests_items_out_of_range")
    for item in items:
        if not isinstance(item, dict) or not str(item.get("offering") or "").strip():
            raise CommandError("legacy_guests_item_invalid")
        if not str(item.get("fin") or "").strip() and not str(item.get("name") or "").strip():
            raise CommandError("legacy_guests_item_invalid")
    return items


def resolve_students(organization, items) -> dict:
    """``{index → user}``: FİN (profil) → yoxdursa «Soyad Ad» tək uyğunluğu (təşkilatın aktiv tələbə üzvləri)."""
    User = get_user_model()
    Membership = django_apps.get_model("organizations", "Membership")
    students = User.objects.filter(
        memberships__organization=organization,
        memberships__role__name="student",
        memberships__is_active=True,
        is_active=True,
    ).select_related("profile")
    by_fin: dict = {}
    by_name: dict = {}
    for user in students.distinct():
        fin = str(getattr(getattr(user, "profile", None), "fin", "") or "").strip().upper()
        if fin:
            by_fin.setdefault(fin, []).append(user)
        by_name.setdefault(_norm(f"{user.last_name} {user.first_name}"), []).append(user)
    del Membership
    out = {}
    for index, item in enumerate(items):
        fin = str(item.get("fin") or "").strip().upper()
        found = by_fin.get(fin, []) if fin else []
        if not found:
            found = by_name.get(_norm(item.get("name")), [])
        if len(found) == 1:
            out[index] = found[0]
    return out


def run(*, organization, actor, items, counts, apply) -> None:
    from apps.registrar import guest_roster

    CourseOffering = django_apps.get_model("registrar", "CourseOffering")
    offerings = {
        str(o.pk): o
        for o in CourseOffering.objects.filter(
            organization=organization, pk__in={str(i["offering"]).strip() for i in items}
        ).select_related("subject", "period", "group")
    }
    users = resolve_students(organization, items)
    seen = set()
    for index, item in enumerate(items):
        offering = offerings.get(str(item["offering"]).strip())
        if offering is None or not offering.is_active:
            counts["skip_offering_unknown"] += 1
            continue
        student = users.get(index)
        if student is None:
            counts["skip_student_unresolved"] += 1
            continue
        key = (offering.pk, student.pk)
        if key in seen:
            counts["skip_duplicate_item"] += 1
            continue
        seen.add(key)
        reason = str(item.get("reason") or "").strip() or "Köhnə sistemin jurnalında iştirak/bal qeydi (2026-11-09)"
        try:
            with transaction.atomic():
                guest_roster.add_guest_student(offering=offering, student=student, by_user=actor, reason=reason)
        except ValidationError as exc:
            message = " ".join(str(m) for m in exc.messages)
            if "artıq jurnaldadır" in message or "onsuz da bu qrupun" in message:
                counts["skip_already_enrolled"] += 1
            elif "öz qrupunun jurnalında aktivdir" in message or "birdən çox aktiv jurnalı" in message:
                counts["skip_other_journal_active"] += 1
            elif "bağlanıb" in message or "bağlıdır" in message:
                counts["skip_roster_closed"] += 1
            elif "akademik qeyd" in message or "uyğun" in message:
                counts["skip_no_active_record"] += 1
            else:
                counts["skip_refused"] += 1
            continue
        counts["added"] += 1
        counts[f"added_{'level' if offering.group_id is None else 'group'}"] += 1


class Command(BaseCommand):
    help = "Köhnə jurnalda iştirakı olan tələbəni alt qrupdan həmin jurnala əlavə edir (plan faylı; defolt dry-run)."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--file", required=True, help=f"{FORMAT} JSON faylı")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")

    def handle(self, *args, **options):
        items = load_plan(options["file"])
        actor = (
            get_user_model()
            .objects.filter(username=str(options["actor"]).strip(), is_active=True, is_superuser=True)
            .first()
        )
        if actor is None:
            raise CommandError("actor_must_be_active_superuser")
        Organization = django_apps.get_model("organizations", "Organization")
        counts: Counter = Counter()
        with rls_worker_atomic(), bypass_rls():
            organization = Organization.objects.filter(slug=str(options["org"]).strip()).first()
            if organization is None:
                raise CommandError("legacy_guests_organization_unknown")
            apply_rls_request_context(user_id=actor.pk, org_id=organization.pk)
            with transaction.atomic():
                run(organization=organization, actor=actor, items=items, counts=counts, apply=bool(options["apply"]))
                if not options["apply"]:
                    transaction.set_rollback(True)
        self.stdout.write(f"{PREFIX} mode={'apply' if options['apply'] else 'dry_run'}")
        self.stdout.write(PREFIX + " " + " ".join(f"{key}={value}" for key, value in sorted(counts.items())))
