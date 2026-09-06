"""Heyət siyahısını (Excel/CSV) sistemə yerləşdirir — DRY-RUN defolt.

Sahibin 2026-09-06 tapşırığı: «kim hansı vəzifədədir» siyahısını sistemə sal;
sistemdə qarşılığı olmayan vəzifələr hələlik olduğu kimi qalsın.

    manage.py seed_staff_roster --file ~/Downloads/Siyahı.xlsx --org <slug>
    manage.py seed_staff_roster --file … --org … --apply --credentials-out /tmp/parollar.csv

NƏ EDİR
    * siyahını oxuyur (bölmə başlığı / şəxs sətri ayrılır);
    * vəzifə → rol xəritəsini tətbiq edir (`services/staff_roster.py`);
    * bölmə adına ən yaxın `OrgUnit`-i tapır (üzvlüyün əhatəsi üçün);
    * mövcud istifadəçini ad-soyada görə tapır → üzvlüyünü DÜZƏLDİR,
      tapmasa YENİ hesab yaradır (`intake/create.py` özəyi ilə — eyni parol
      siyasəti, eyni audit izi).

NƏ ETMİR
    * tanınmayan vəzifəyə rol UYDURMUR (`member` + vəzifə mətni);
    * mövcud üzvlüyü SİLMİR (yalnız əlavə edir/aktivləşdirir);
    * `--apply` olmadan heç nə yazmır.
"""

from __future__ import annotations

import csv
import pathlib
from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.services import staff_roster as roster
from core.rls_pooling import rls_worker_atomic

_KIND_TEACHER = "teacher"

#: Bu rollar tədris heyətidir — profil rolu «müəllim» qalır. Qalanlarda profil
#: rolu `member`-ə endirilir (kabinetdə müəllim səthləri açılmasın).
_TEACHING_ROLES = {"teacher", "dean", "vice_dean", "chair_head", "tutor", "lab_assistant"}


def _split_patronymic(full_name: str) -> tuple[str, str]:
    """«Soyad Ad Ata adı» → (qalan, ata adı). Ata adı yoxdursa boş sətir."""
    tokens = str(full_name or "").split()
    return (" ".join(tokens[:2]), tokens[2]) if len(tokens) >= 3 else (full_name, "")


def _read_rows(path: pathlib.Path):
    if path.suffix.lower() in {".xlsx", ".xlsm"}:
        try:
            import openpyxl
        except ImportError as exc:  # pragma: no cover — mühit problemi
            raise CommandError("openpyxl quraşdırılmayıb — CSV işlədin.") from exc
        sheet = openpyxl.load_workbook(path, data_only=True).worksheets[0]
        return [(row[0], row[1] if len(row) > 1 else "") for row in sheet.iter_rows(values_only=True)]
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [(row[0] if row else "", row[1] if len(row) > 1 else "") for row in csv.reader(handle)]


class Command(BaseCommand):
    help = "Heyət siyahısını oxuyur, vəzifə → rol xəritəsini tətbiq edir (dry-run defolt)."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Excel (.xlsx) və ya CSV yolu")
        parser.add_argument("--org", required=True, help="Təşkilat slug-ı")
        parser.add_argument("--apply", action="store_true", help="Yaz (defolt: yalnız hesabat)")
        parser.add_argument("--credentials-out", default="", help="Yeni hesabların parolu üçün CSV yolu")
        parser.add_argument("--limit", type=int, default=0, help="Yalnız ilk N sətir (sınaq üçün)")

    def handle(self, *args, **options):
        # RLS transaction-pooling təhlükəsizliyi (FAZA 4/Task 1): request-dən kənar
        # bütün DB işi bir worker-atomic sərhədi içindədir.
        with rls_worker_atomic():
            self._run(**options)

    def _run(self, **options):
        from apps.organizations.models import Membership, Organization, OrgUnit

        path = pathlib.Path(options["file"]).expanduser()
        if not path.exists():
            raise CommandError(f"Fayl tapılmadı: {path}")
        try:
            organization = Organization.objects.get(slug=options["org"])
        except Organization.DoesNotExist as exc:
            raise CommandError(f"Təşkilat tapılmadı: {options['org']}") from exc

        people = roster.parse_rows(_read_rows(path))
        if options["limit"]:
            people = people[: options["limit"]]
        units = list(OrgUnit.objects.filter(organization=organization, is_active=True))
        roles = {role.name: role for role in organization.roles.all()}

        # Ad-soyad ÜZRƏ eyniadlılar: siyahıda «Vəliyeva Fəridə Rəsul» iki fərqli
        # bölmədə var. Uyğunlaşdırma yalnız ad+soyada baxdığı üçün hər iki sətir
        # EYNİ hesaba bağlanır və o hesab iki rol daşıyır, ikinci şəxs isə heç vaxt
        # hesab almır. Avtomatik həll YOXDUR (eyni adam, yoxsa iki adam?) — ona görə
        # belə sətirlər FAIL-CLOSED atlanır və hesabatda ayrıca göstərilir.
        name_counts = Counter(roster.split_name(person["name"]) for person in people)

        plans, missing_roles, unmatched_units, unmapped = [], set(), set(), 0
        for person in people:
            role_name, mapped = roster.role_for(person["section"], person["position"])
            unmapped += int(not mapped)
            if role_name not in roles:
                missing_roles.add(role_name)
            unit = roster.match_unit(person["section"], units)
            if unit is None and person["section"]:
                unmatched_units.add(person["section"])
            first, last = roster.split_name(person["name"])
            # DİQQƏT: sayım İSTİFADƏÇİ üzrədir, üzvlük üzrə yox — komanda təkrar
            # işlədiləndə bir adamda bir neçə üzvlük olur və üzvlük sayımı hər kəsi
            # yalançı «çox mənalı» edərdi.
            match_ids = list(
                Membership.objects.filter(
                    organization=organization, user__first_name__iexact=first, user__last_name__iexact=last
                )
                # `.order_by()` MƏCBURİDİR: `Membership.Meta.ordering` sahəsi
                # DISTINCT-ə əlavə olunur və eyni istifadəçinin bir neçə üzvlüyü
                # «fərqli hesab» kimi görünərdi (Django-nun klassik tələsi).
                .order_by()
                .values_list("user_id", flat=True)
                .distinct()[:2]
            )
            if len(match_ids) > 1:
                # Ad-soyad eyni olanda TƏLƏBƏ/məzun hesabları kənarlaşdırılır:
                # klonda «Babayeva Nigar» adına prorektor rolu tələbə hesabına
                # yapışmışdı. Heyət hesabı BİRDİRSƏ seçim birmənalıdır.
                staff_ids = [
                    user_id
                    for user_id in match_ids
                    if Membership.objects.filter(organization=organization, user_id=user_id)
                    .exclude(role__name__in=roster.NON_STAFF_ROLE_NAMES)
                    .exists()
                ]
                if len(staff_ids) == 1:
                    match_ids = staff_ids
            ambiguous = ""
            if name_counts[(first, last)] > 1:
                ambiguous = "siyahıda eyni ad-soyad birdən çox sətirdədir"
            elif len(match_ids) > 1:
                ambiguous = "bazada eyni ad-soyadlı birdən çox HEYƏT hesabı var"
            elif match_ids and not (
                Membership.objects.filter(organization=organization, user_id=match_ids[0])
                .exclude(role__name__in=roster.NON_STAFF_ROLE_NAMES)
                .exists()
            ):
                # Tapılan yeganə hesab TƏLƏBƏ hesabıdır. Eyni adam ola bilər
                # (laborant kimi işləyən magistr), ad toqquşması da ola bilər —
                # sistem bunu bilə bilməz, ona görə fail-closed: heyət rolu
                # tələbə hesabına AVTOMATİK yapışdırılmır.
                ambiguous = "yalnız TƏLƏBƏ hesabı tapıldı — eyni adamdırsa əl ilə təsdiqləyin"
            existing = (
                Membership.objects.filter(organization=organization, user_id=match_ids[0])
                .select_related("user", "role")
                .first()
                if match_ids
                else None
            )
            plans.append(
                {
                    "person": person,
                    "role_name": role_name,
                    "mapped": mapped,
                    "unit": unit,
                    "existing": existing.user if existing else None,
                    "current_role": existing.role.name if existing else "",
                    "ambiguous": ambiguous,
                }
            )

        self._report(plans, organization, missing_roles, unmatched_units, unmapped)
        if not options["apply"]:
            self.stdout.write(self.style.WARNING("\nDRY-RUN — heç nə yazılmadı. Yazmaq üçün: --apply"))
            return
        self._apply(plans, organization, roles, options["credentials_out"])

    # ── Hesabat ─────────────────────────────────────────────────────────────
    def _report(self, plans, organization, missing_roles, unmatched_units, unmapped):
        self.stdout.write(f"\n=== HEYƏT SİYAHISI · {organization.name} ===")
        self.stdout.write(f"Şəxs: {len(plans)} · rol xəritələnən: {len(plans) - unmapped} · qalıq (member): {unmapped}")
        by_role = Counter(plan["role_name"] for plan in plans)
        for role_name, count in by_role.most_common():
            self.stdout.write(f"   {role_name:24s} {count}")
        ambiguous = [plan for plan in plans if plan.get("ambiguous")]
        creates = sum(1 for plan in plans if plan["existing"] is None and not plan.get("ambiguous"))
        self.stdout.write(
            f"\nYeni hesab: {creates} · mövcud hesab: {len(plans) - creates - len(ambiguous)}"
            f" · çox mənalı (atlanır): {len(ambiguous)}"
        )
        if ambiguous:
            self.stdout.write(self.style.WARNING("ÇOX MƏNALI — əl ilə həll edilməlidir (heç nə yazılmır):"))
            for plan in ambiguous:
                person = plan["person"]
                self.stdout.write(
                    f"   · {person['name']} — {person['section']} / {person['position']}" f"  [{plan['ambiguous']}]"
                )
        if missing_roles:
            self.stdout.write(self.style.ERROR(f"Təşkilatda OLMAYAN rollar: {', '.join(sorted(missing_roles))}"))
        if unmatched_units:
            self.stdout.write(self.style.WARNING(f"Vahidi tapılmayan bölmə: {len(unmatched_units)}"))
            for name in sorted(unmatched_units)[:10]:
                self.stdout.write(f"   · {name}")

    # ── Tətbiq ──────────────────────────────────────────────────────────────
    def _apply(self, plans, organization, roles, credentials_out):
        from apps.accounts.services.intake.create import claim_username, create_account
        from apps.organizations.models import Membership
        from core.roles import ProfileRole

        created, updated, skipped, credentials = 0, 0, 0, []
        taken = set()
        for plan in plans:
            role = roles.get(plan["role_name"])
            # Eyniadlılıq həll olunmayana qədər heç nə yazmırıq: səhv hesaba rol
            # yapışdırmaq, yoxsa dublikat hesab yaratmaq — hər ikisi geri qaytarılması
            # çətin data qüsurudur (bax `_run`-dakı `name_counts` şərhi).
            if plan.get("ambiguous"):
                skipped += 1
                continue
            if role is None:
                skipped += 1
                continue
            person = plan["person"]
            first, last = roster.split_name(person["name"])
            with transaction.atomic():
                user = plan["existing"]
                if user is None:
                    username = claim_username(roster.username_seed(person["name"]), taken=taken)
                    taken.add(username)
                    _, patronymic = _split_patronymic(person["name"])
                    user, password = create_account(
                        organization=organization,
                        kind=_KIND_TEACHER,
                        # `create_account` bütün profil sahələrini gözləyir —
                        # siyahıda yalnız ad/vəzifə var, qalanı boş göndərilir.
                        values={
                            "username": username,
                            "first_name": first,
                            "last_name": last,
                            "email": "",
                            "fin": None,  # siyahıda FİN yoxdur; sahə unikaldır, boş sətir toqquşur
                            "patronymic": patronymic,
                            "gender": "",
                            "birth_date": None,
                            "phone": "",
                            "student_code": "",
                        },
                        role=role,
                        actor=None,
                        scope_unit=plan["unit"],
                        audit_reason="staff_roster_created",
                    )
                    credentials.append((username, person["name"], person["section"], person["position"], password))
                    created += 1
                else:
                    Membership.objects.get_or_create(
                        user=user,
                        organization=organization,
                        role=role,
                        scope_unit=plan["unit"],
                        defaults={"is_active": True},
                    )
                    updated += 1
                profile = getattr(user, "profile", None)
                if profile is not None:
                    profile.staff_position = person["position"][:120]
                    if plan["role_name"] not in _TEACHING_ROLES:
                        profile.role = ProfileRole.MEMBER
                    profile.save(update_fields=["staff_position", "role", "updated_at"])

        self.stdout.write(self.style.SUCCESS(f"\n✓ Yaradıldı: {created} · yeniləndi: {updated} · ötürüldü: {skipped}"))
        if credentials and credentials_out:
            out = pathlib.Path(credentials_out).expanduser()
            with out.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["username", "ad", "bölmə", "vəzifə", "birdəfəlik_parol"])
                writer.writerows(credentials)
            self.stdout.write(self.style.WARNING(f"Parollar: {out} — bir dəfə göstərilir, təhlükəsiz saxlayın."))
