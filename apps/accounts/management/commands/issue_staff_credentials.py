"""``issue_staff_credentials`` — fakültənin müəllim və işçiləri üçün ilkin parol siyahısını tamamlayır (sahib 2026-10-19).

Sahib: «RİM qovluğunda müəllimlərin ilkin parolları var; siyahıda adı olmayanları (yeni əlavələrlə birlikdə)
da sistemə əlavə et — dekan və dekan müavininə fakültə üzrə paylanacaq». Bu əmr həmin «əskik» hissəni verir:

* **Hədəf**: ``--faculty`` fakültəsinin alt-ağacında AKTİV, tələbə olmayan üzvlüyü olan hesablar (müəllim,
  dekanlıq, kafedra, metodist və s.).
* **Mövcud siyahı** (``--known-usernames``, sətirdə bir istifadəçi adı — PAROL YOX): bu hesablara TOXUNULMUR,
  onlara artıq paylanmış ilkin parol var.
* **Parol yalnız aktivləşməmiş hesaba** verilir (e-poçtu təsdiqlənməyib VƏ ya ilk-giriş axını bitməyib).
  Sistemdə artıq öz parolu ilə işləyən hesab «aktivləşib» kimi hesabatda qalır, parolu SIFIRLANMIR.
* Yeni parol verilən hesab ``provision_student_credentials`` ilə eyni ilk-giriş axınına düşür (ilk girişdə
  e-poçt + OTP + yeni parol məcburidir).

Çıxış: ``--report-out`` CSV (bütün fakültə heyəti: vəziyyət və əməl; parol YOX) və ``--apply`` ilə
``--credentials-out`` CSV (yalnız yeni verilən parollar). Stdout-a YALNIZ saylar düşür (workflow logu).
``--find-name`` «Ad Soyad» hissələri ilə üzv axtarır və tapılanların rolunu/fakültəsini hesabata yazır
(fakültə bilinməyəndə — məs. dekan müavininin fakültəsini tapmaq üçün).

**Tələbələr** (``--audience students``, sahib 2026-10-19 axşam): fakültə üzrə OXUYAN (akademik status «enrolled»,
hesab və tələbə üzvlüyü aktiv) tələbələr. Siyahı faylında sətir ``username<TAB>parol`` ola bilər — onda siyahıdakı
parol bazadakı hash ilə YOXLANILIR (yazmadan); aktivləşməmiş hesabda parol artıq uyğun deyilsə (sonradan sıfırlanıb),
ona da yeni ilkin parol verilir. ``--faculty`` boşdursa bütün fakültələr. PBKDF2 hesablaması paralel axınlarla gedir
(hashlib GIL-i buraxır).

İstifadə::

    manage.py issue_staff_credentials --org qku --faculty "Yüksək texnologiyalar" \\
        --known-usernames /tmp/known.txt --report-out /tmp/report.csv
    manage.py issue_staff_credentials --org qku --faculty "…" --known-usernames /tmp/known.txt \\
        --report-out /tmp/report.csv --apply --credentials-out /tmp/creds.csv \\
        --reason "Fakültə üzrə ilkin parol siyahısının tamamlanması" --i-know-this-is-production
"""

from __future__ import annotations

import os
import pathlib
import unicodedata
from concurrent.futures import ThreadPoolExecutor

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils.crypto import get_random_string

from core.audit import log_action
from core.constants import AuditAction
from core.export_safety import safe_csv_writer
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

User = get_user_model()

#: ``provision_student_credentials`` ilə eyni oxunaqlı əlifba (0/O, 1/l/I yox).
_PASSWORD_ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789"
_NON_STAFF_ROLES = ("student", "lead_student", "alumni", "member")
_STUDENT_ROLES = ("student", "lead_student")
_REHEARSAL_GUC = "emsarena.rehearsal_target"
_REASON_MIN = 20
#: Kollec, İngilis dili mərkəzi və s. «fakültə» tipində olmaya bilər — qrup/ixtisas/kafedra/lab xaric hər vahid.
_LEAF_UNIT_TYPES = ("group", "specialty", "chair", "lab")

STATE_ACTIVATED = "aktivləşib"
STATE_PENDING = "aktivləşməyib"


def fold(value) -> str:
    text = str(value or "").casefold()
    for src, dst in (("ə", "e"), ("ı", "i"), ("ğ", "g"), ("ş", "s"), ("ç", "c"), ("ö", "o"), ("ü", "u")):
        text = text.replace(src, dst)
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch)).strip()


def _disposable_database() -> bool:
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting(%s, true)", [_REHEARSAL_GUC])
        row = cursor.fetchone()
    return bool(row and row[0] == "disposable")


def _ancestors(unit) -> dict:
    names, current, depth = {}, unit, 0
    while current is not None and depth < 6:
        names.setdefault(current.unit_type, current.name)
        current = current.parent
        depth += 1
    return names


def _parallel(fn, items):
    """PBKDF2 (check/make_password) CPU-yə bağlıdır, amma hashlib GIL-i buraxır — axınlar real paralellik verir."""
    if not items:
        return []
    with ThreadPoolExecutor(max_workers=max(2, min(16, (os.cpu_count() or 2) * 2))) as pool:
        return list(pool.map(fn, items))


def _activated(profile) -> bool:
    return bool(profile is not None and profile.email_verified and not profile.password_change_required)


class Command(BaseCommand):
    help = "Fakültə heyətinin ilkin parol siyahısını tamamlayır (yalnız siyahıda olmayan, aktivləşməmiş hesablar)."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True)
        parser.add_argument("--faculty", default="", help="Fakültənin adı (hissə ilə; böyük/kiçik hərf fərqi yoxdur)")
        parser.add_argument(
            "--known-usernames", default="", help="Artıq ilkin parolu olan istifadəçi adları (sətirdə bir)"
        )
        parser.add_argument("--audience", choices=("staff", "students"), default="staff")
        parser.add_argument("--find-name", default="", help="Ad hissələri ilə üzv axtarışı (rol + fakültə hesabata)")
        parser.add_argument(
            "--admission-year",
            type=int,
            default=None,
            help="--audience students: yalnız bu qəbul ilinin tələbələri (məs. 2026 = 1-ci kurs; sahib 2026-10-26)",
        )
        parser.add_argument("--report-out", default="", help="Hesabat CSV (parolsuz)")
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--credentials-out", default="", help="--apply: yeni parolların CSV-si")
        parser.add_argument("--reason", default="", help="--apply üçün səbəb (≥20 simvol)")
        parser.add_argument("--i-know-this-is-production", action="store_true")

    # ── giriş ────────────────────────────────────────────────────────────────
    def handle(self, *args, **opts):
        if opts["apply"]:
            if not opts["credentials_out"]:
                raise CommandError("--apply üçün --credentials-out məcburidir (parollar bir daha görünmür).")
            if len(opts["reason"].strip()) < _REASON_MIN:
                raise CommandError(f"--apply üçün --reason ən azı {_REASON_MIN} simvol olmalıdır.")
            if not opts["faculty"].strip() and opts["audience"] != "students":
                raise CommandError("--apply üçün --faculty məcburidir.")
        with rls_worker_atomic(), bypass_rls():
            if opts["apply"] and not (_disposable_database() or opts["i_know_this_is_production"]):
                raise CommandError("staff_credentials_not_disposable: real bazada --i-know-this-is-production verin.")
            self._run(opts)

    def _run(self, opts):
        Organization = django_apps.get_model("organizations", "Organization")
        organization = Organization.objects.filter(slug=opts["org"].strip()).first()
        if organization is None:
            raise CommandError(f"Təşkilat tapılmadı: {opts['org']!r}")
        known = self._known(opts["known_usernames"])
        if opts["audience"] == "students":
            return self._run_students(organization, known, opts)
        rows: list[dict] = []
        if opts["find_name"].strip():
            rows.extend(self._find(organization, opts["find_name"]))
        targets = []
        faculty = None
        if opts["faculty"].strip():
            faculty = self._faculty(organization, opts["faculty"])
            staff_rows, targets = self._faculty_staff(organization, faculty, known)
            rows.extend(staff_rows)
        issued = []
        if opts["apply"] and targets:
            issued = self._issue(organization, targets, opts["reason"].strip())
            issued_ids = {item["user_id"] for item in issued}
            for row in rows:
                if row.get("user_id") in issued_ids:
                    row["action"] = "yeni ilkin parol verildi"
        if opts["report_out"]:
            self._write_report(opts["report_out"], rows)
        if opts["credentials_out"] and issued:
            self._write_credentials(opts["credentials_out"], issued)
        staff = [r for r in rows if r["kind"] == "staff"]
        self.stdout.write(
            "staff_credentials: "
            f"faculty_found={int(faculty is not None)} staff={len(staff)} "
            f"in_known_list={sum(1 for r in staff if r['in_list'] == 'bəli')} "
            f"activated={sum(1 for r in staff if r['state'] == STATE_ACTIVATED)} "
            f"new_targets={len(targets)} issued={len(issued)} "
            f"find_matches={sum(1 for r in rows if r['kind'] == 'find')} "
            f"mode={'APPLY' if opts['apply'] else 'DRY-RUN'}"
        )

    # ── köməkçilər ───────────────────────────────────────────────────────────
    @staticmethod
    def _known(path: str) -> dict[str, str]:
        """istifadəçi adı → siyahıdakı parol («» = parol verilməyib, yalnız ad)."""
        if not path:
            return {}
        file = pathlib.Path(path)
        if not file.exists():
            raise CommandError("--known-usernames faylı tapılmadı.")
        known: dict[str, str] = {}
        for line in file.read_text(encoding="utf-8").splitlines():
            username, _, password = line.partition("\t")
            if username.strip():
                known[username.strip().casefold()] = password.strip()
        return known

    @staticmethod
    def _faculty(organization, query: str):
        OrgUnit = django_apps.get_model("organizations", "OrgUnit")
        wanted = fold(query)
        matches = [
            unit
            for unit in OrgUnit.objects.filter(organization=organization, is_active=True).exclude(
                unit_type__in=_LEAF_UNIT_TYPES
            )
            if wanted in fold(unit.name)
        ]
        exact = [unit for unit in matches if fold(unit.name) == wanted]
        if len(matches) > 1 and len(exact) == 1:
            matches = exact  # «Kollec» həm «Kollec», həm «Kollec (köhnə)» ola bilər — dəqiq ad üstündür
        if len(matches) != 1:
            raise CommandError(f"faculty_not_unique: {len(matches)} fakültə uyğun gəldi — adı dəqiqləşdirin.")
        return matches[0]

    def _memberships(self, organization):
        Membership = django_apps.get_model("organizations", "Membership")
        return (
            Membership.objects.filter(organization=organization, is_active=True, user__is_active=True)
            .exclude(role__name__in=_NON_STAFF_ROLES)
            .exclude(user__is_superuser=True)
            .select_related("user__profile", "role", "scope_unit__parent__parent__parent")
        )

    def _faculty_staff(self, organization, faculty, known):
        prefix = faculty.path or ""
        per_user: dict[int, dict] = {}
        for membership in self._memberships(organization).filter(scope_unit__isnull=False):
            unit = membership.scope_unit
            if not (unit.pk == faculty.pk or (prefix and (unit.path or "").startswith(prefix))):
                continue
            user = membership.user
            names = _ancestors(unit)
            entry = per_user.setdefault(
                user.pk,
                {
                    "kind": "staff",
                    "user_id": user.pk,
                    "user": user,
                    "faculty": faculty.name,
                    "chair": names.get("chair") or names.get("department") or "",
                    "roles": set(),
                    "full_name": (f"{user.last_name} {user.first_name}").strip() or user.username,
                    "username": user.username,
                },
            )
            entry["roles"].add(membership.role.display_name or membership.role.name)
            if not entry["chair"]:
                entry["chair"] = names.get("chair") or names.get("department") or ""
        rows, targets = [], []
        for entry in sorted(per_user.values(), key=lambda e: (e["chair"], fold(e["full_name"]))):
            profile = getattr(entry["user"], "profile", None)
            activated = _activated(profile)
            in_list = entry["username"].casefold() in known
            entry["roles"] = ", ".join(sorted(entry["roles"]))
            entry["state"] = STATE_ACTIVATED if activated else STATE_PENDING
            entry["in_list"] = "bəli" if in_list else "xeyr"
            if in_list:
                entry["action"] = "siyahıdakı ilkin parol"
            elif activated:
                entry["action"] = "öz parolu ilə işləyir — parol verilmir"
            else:
                entry["action"] = "yeni ilkin parol veriləcək"
                targets.append(entry)
            rows.append(entry)
        return rows, targets

    def _find(self, organization, query: str):
        tokens = [fold(t) for t in query.split() if t.strip()]
        found = []
        for membership in self._memberships(organization):
            user = membership.user
            name = fold(f"{user.last_name} {user.first_name} {user.username}")
            if not tokens or not all(t in name for t in tokens):
                continue
            names = _ancestors(membership.scope_unit) if membership.scope_unit_id else {}
            found.append(
                {
                    "kind": "find",
                    "user_id": user.pk,
                    "faculty": names.get("faculty", ""),
                    "chair": names.get("chair") or names.get("department") or "",
                    "roles": membership.role.display_name or membership.role.name,
                    "full_name": (f"{user.last_name} {user.first_name}").strip() or user.username,
                    "username": user.username,
                    "state": STATE_ACTIVATED if _activated(getattr(user, "profile", None)) else STATE_PENDING,
                    "in_list": "",
                    "action": "axtarış nəticəsi",
                }
            )
        return found

    # ── tələbələr ────────────────────────────────────────────────────────────
    def _run_students(self, organization, known, opts):
        faculty = self._faculty(organization, opts["faculty"]) if opts["faculty"].strip() else None
        rows = self._students(organization, faculty, admission_year=opts.get("admission_year"))
        pending = [r for r in rows if r["state"] == STATE_PENDING and known.get(r["username"].casefold())]
        verdicts = _parallel(lambda r: check_password(known[r["username"].casefold()], r["user"].password), pending)
        valid_ids = {r["user_id"] for r, ok in zip(pending, verdicts) if ok}
        targets = []
        for row in rows:
            in_list = row["username"].casefold() in known
            row["in_list"] = "bəli" if in_list else "xeyr"
            if row["state"] == STATE_ACTIVATED:
                row["action"] = "öz parolu ilə işləyir — parol verilmir"
            elif row["user_id"] in valid_ids:
                row["action"] = "siyahıdakı ilkin parol (yoxlanıldı)"
            elif in_list and not known[row["username"].casefold()]:
                row["action"] = "siyahıdakı ilkin parol"
            else:
                row["action"] = "yeni ilkin parol veriləcək"
                row["reason_new"] = "siyahıdakı parol uyğun deyil" if in_list else "siyahıda yoxdur"
                targets.append(row)
        issued = []
        if opts["apply"] and targets:
            issued = self._issue(organization, targets, opts["reason"].strip(), verb="issue_student_credentials")
            issued_ids = {item["user_id"] for item in issued}
            for row in rows:
                if row["user_id"] in issued_ids:
                    row["action"] = "yeni ilkin parol verildi"
        if opts["report_out"]:
            self._write_student_report(opts["report_out"], rows)
        if opts["credentials_out"] and issued:
            self._write_student_credentials(opts["credentials_out"], issued)
        self.stdout.write(
            "staff_credentials: "
            f"audience=STUDENTS faculty_found={int(faculty is not None)} students={len(rows)} "
            f"in_known_list={sum(1 for r in rows if r['in_list'] == 'bəli')} "
            f"activated={sum(1 for r in rows if r['state'] == STATE_ACTIVATED)} "
            f"list_password_valid={len(valid_ids)} "
            f"list_password_stale={sum(1 for r in targets if r['in_list'] == 'bəli')} "
            f"no_faculty={sum(1 for r in rows if not r['faculty'])} "
            f"new_targets={len(targets)} issued={len(issued)} "
            f"mode={'APPLY' if opts['apply'] else 'DRY-RUN'}"
        )

    @staticmethod
    def _placement(group):
        """Qrup → (fakültə vahidi, əsas qrup adı, alt qrup adı, ixtisas adı)."""
        top_group, specialty, faculty, current, depth = group, "", None, group, 0
        while current is not None and depth < 8:
            if current.unit_type == "group":
                top_group = current
            elif current.unit_type == "specialty" and not specialty:
                specialty = current.name
            elif current.unit_type not in _LEAF_UNIT_TYPES:
                faculty = current
                break
            current = current.parent
            depth += 1
        subgroup = group.name if top_group.pk != group.pk else ""
        return faculty, top_group.name, subgroup, specialty

    def _students(self, organization, faculty, *, admission_year=None):
        Membership = django_apps.get_model("organizations", "Membership")
        Record = django_apps.get_model("registrar", "StudentAcademicRecord")
        student_ids = Membership.objects.filter(
            organization=organization, is_active=True, role__name__in=_STUDENT_ROLES
        ).values("user_id")
        records = (
            Record.objects.filter(
                organization=organization,
                is_active=True,
                status="enrolled",
                student__is_active=True,
                student__is_superuser=False,
                student_id__in=student_ids,
            )
            .select_related("student__profile", "program", "group__parent__parent__parent__parent__parent")
            .order_by("student_id", "-created_at")
        )
        if admission_year:
            records = records.filter(admission_year=admission_year)
        rows, seen = [], set()
        for record in records:
            if record.student_id in seen:
                continue  # bir neçə aktiv proqram — ən son qeyd
            seen.add(record.student_id)
            unit, group_name, subgroup, specialty = (None, "", "", "")
            if record.group_id:
                unit, group_name, subgroup, specialty = self._placement(record.group)
            if faculty is not None and (unit is None or unit.pk != faculty.pk):
                continue
            user = record.student
            profile = getattr(user, "profile", None)
            rows.append(
                {
                    "kind": "student",
                    "user_id": user.pk,
                    "user": user,
                    "faculty": unit.name if unit is not None else "",
                    "program": specialty or getattr(record.program, "name", "") or "",
                    "group": group_name,
                    "subgroup": subgroup,
                    "code": getattr(profile, "institutional_identifier", "") or "",
                    "full_name": (f"{user.last_name} {user.first_name}").strip() or user.username,
                    "username": user.username,
                    "state": STATE_ACTIVATED if _activated(profile) else STATE_PENDING,
                }
            )
        rows.sort(key=lambda r: (fold(r["faculty"]), fold(r["group"]), fold(r["full_name"])))
        return rows

    @staticmethod
    def _write_student_report(path, rows):
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = safe_csv_writer(fh)
            writer.writerow(
                [
                    "nov",
                    "fakulte",
                    "ixtisas",
                    "qrup",
                    "alt_qrup",
                    "telebe_kodu",
                    "ad_soyad",
                    "username",
                    "veziyyet",
                    "siyahida",
                    "emel",
                ]
            )
            for r in rows:
                writer.writerow(
                    [
                        r["kind"],
                        r["faculty"],
                        r["program"],
                        r["group"],
                        r["subgroup"],
                        r["code"],
                        r["full_name"],
                        r["username"],
                        r["state"],
                        r["in_list"],
                        r["action"],
                    ]
                )

    @staticmethod
    def _write_student_credentials(path, issued):
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = safe_csv_writer(fh)
            writer.writerow(["fakulte", "qrup", "ad_soyad", "username", "sebeb", "ilkin_parol"])
            for r in issued:
                writer.writerow(
                    [r["faculty"], r["group"], r["full_name"], r["username"], r.get("reason_new", ""), r["password"]]
                )

    def _issue(self, organization, targets, reason, *, verb="issue_staff_credentials"):
        issued = []
        passwords = [get_random_string(10, _PASSWORD_ALPHABET) for _ in targets]
        encoded = _parallel(make_password, passwords)
        with transaction.atomic():
            for entry, password, hashed in zip(targets, passwords, encoded):
                user = User.objects.select_for_update(of=("self",)).select_related("profile").get(pk=entry["user_id"])
                profile = getattr(user, "profile", None)
                if profile is None or _activated(profile):
                    continue  # yarışda aktivləşibsə toxunma
                user.password = hashed
                user.save(update_fields=["password"])
                profile.password_change_required = True
                profile.email_verified = False
                profile.save(update_fields=["password_change_required", "email_verified", "updated_at"])
                log_action(
                    action=AuditAction.UPDATE,
                    user=None,
                    organization=organization,
                    obj=user,
                    resource_type="accounts.initial_credentials",
                    resource_id=str(user.pk),
                    resource_repr=user.username,
                    changes={"verb": verb, "faculty": entry["faculty"]},
                    reason=reason,
                )
                issued.append({**entry, "password": password})
        return issued

    @staticmethod
    def _write_report(path, rows):
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = safe_csv_writer(fh)
            writer.writerow(
                ["nov", "fakulte", "kafedra", "rol", "ad_soyad", "username", "veziyyet", "siyahida", "emel"]
            )
            for r in rows:
                writer.writerow(
                    [
                        r["kind"],
                        r["faculty"],
                        r["chair"],
                        r["roles"],
                        r["full_name"],
                        r["username"],
                        r["state"],
                        r["in_list"],
                        r["action"],
                    ]
                )

    @staticmethod
    def _write_credentials(path, issued):
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = safe_csv_writer(fh)
            writer.writerow(["fakulte", "kafedra", "rol", "ad_soyad", "username", "ilkin_parol"])
            for r in issued:
                writer.writerow([r["faculty"], r["chair"], r["roles"], r["full_name"], r["username"], r["password"]])
