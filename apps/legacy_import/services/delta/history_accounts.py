"""Tarixi boşluq tələbələri → hədəf hesabı (``history`` fazası).

Tutuşdurma delta-nın ``StudentMapper``-idir (ledger → ``institutional_identifier`` → FİN → ad + soyad; ambiqü
heç vaxt təxmin edilmir). Tapılmayan tələbə (əsasən cutover-də e-poçt qüsuruna görə hesabı açılmayan 100 nəfər
— ``repair_accounts`` P0-2 kohortu) üçün hesab YARADILIR, amma onun HAZIRDA oxuyub-oxumamasına görə iki yolla:

* **hazırda oxuyur** → delta-nın öz yolu (``StudentMapper`` → ``legacy_accounts.create_legacy_student``: RİM-in
  ``intake.create`` axını, parolsuz, ``legacy.<ad>@placeholder.invalid``, SAR legacy qrupunda);
* **məzun / xaric / keçmiş tələbə** → cutover-in arxiv qolu (``rehearsal_sar_archive``): ``repair_accounts`` ilə
  eyni staged hesab (``myedu.student.<id>``, yer-tutucu e-poçt, parolsuz) → üzvlük ``alumni`` → ``archive_staged_account``
  (üzvlük aktiv — jurnal qapısı açıqdır, GİRİŞ BAĞLIDIR), SAR ``repair_sar.materialise`` ilə (qrup/proqram/il/FİN
  qaydası olduğu kimi). Lazım olsa RİM ``restore_archived_account`` ilə aktivləşdirir.

«Hazırda oxuyur» qaydası ``repair_enrollments_select``-in E2/E3 sübutudur (kohort ili + 2025/2026 fəaliyyəti),
üstəgəl **E4**: legacy qrupu yeni sistemdə həll olunur və həmin qrupun SAR tələbələrinin çoxu AKTİV ``student``
üzvlüyündədir (yeni sistemin öz baxışı — «yeni sistem qalibdir»). Azad edilmiş (``azadedildi=1``) heç vaxt cari deyil.
"""

from __future__ import annotations

from collections import Counter

from django.apps import apps as django_apps
from django.db import transaction

from ..legacy_demographics import legacy_birth_date
from .people import student_gender
from .resolve import person_key, text

LAST_YEAR_PREFIX = "2025/2026"


def _display(row: dict) -> str:
    return " ".join(
        part for part in (text(row.get("last_name")), text(row.get("first_name")), text(row.get("father_name"))) if part
    )


class HistoryAccounts:
    """legacy ``students.id`` → ``user_id`` (yaradılmış hesablar da daxil)."""

    def __init__(self, run, section: dict, *, activity: dict):
        self.run = run
        self.mapper = run.students
        self.fin_counts = Counter(section.get("fin_counts") or {})
        self.activity = activity  # legacy id → {"2025/2026 Yaz", …}
        self.resolved: dict = {}
        self._group_state: dict = {}
        self._alumni_role = None
        self._sar_rows: list = []

    # ── giriş nöqtəsi ─────────────────────────────────────────────────────
    def resolve_all(self, legacy_ids) -> dict:
        """``StudentMapper.prepare`` ilə eyni üç keçid: əvvəl hamı YARATMADAN tutuşdurulur, sonra yaradılır."""

        mapper = self.mapper
        create, recheck = [], []
        for legacy_id in sorted(set(legacy_ids)):
            result = mapper._resolve(legacy_id, create=False)
            if result[0] is None and result[1] == "not_found":
                create.append(legacy_id)
            elif result[0] is None and str((mapper.students.get(legacy_id) or {}).get("fincode") or "").strip():
                recheck.append(legacy_id)
            else:
                mapper._remember(legacy_id, result)
        for legacy_id in create:
            self._create(legacy_id)
        for legacy_id in recheck:
            mapper.resolve(legacy_id, create=False)
        if self._sar_rows:
            self._materialise_records()
        self.resolved = {
            legacy_id: user_id for legacy_id, (user_id, _outcome) in mapper._cache.items() if user_id is not None
        }
        return self.resolved

    # ── yaratma qərarı ────────────────────────────────────────────────────
    def is_current(self, row: dict) -> str:
        """Sübut kodu (boş = hazırda oxumur). E2/E3 — ``repair_enrollments_select`` qaydası; E4 — yeni sistem."""

        from ..repair_enrollments_select import _current_students

        if int(row.get("azadedildi") or 0) == 1:
            return ""
        legacy = self.run.legacy_groups.get(row.get("group_id")) or {}
        cohort = {row["id"]: (_year(legacy.get("start_year")), str(legacy.get("bak_or_mag") or "").strip())}
        evidence = _current_students(
            students={str(row["id"]): (0, "")},
            status={row["id"]: 0},
            cohort=cohort,
            activity={row["id"]: self.activity.get(row["id"], set())},
            placed=set(),
        ).get(row["id"])
        if evidence:
            return evidence[1]
        return "E4_group_active" if self._group_is_active(legacy) else ""

    def _group_is_active(self, legacy: dict) -> bool:
        if not legacy:
            return False
        key = legacy["id"]
        if key not in self._group_state:
            unit, _how = self.run.catalog.group_for(legacy)
            self._group_state[key] = unit is not None and _majority_active(self.run.organization, unit)
        return self._group_state[key]

    def _create(self, legacy_id) -> None:
        mapper = self.mapper
        row = mapper.students.get(legacy_id)
        evidence = self.is_current(row) if row else ""
        if evidence:
            self.run.count(f"history.student.current.{evidence.lower()}")
            result = mapper.resolve(legacy_id)  # delta yolu: create_legacy_student (azad edilmişi yaratmır)
            if result[0] is None:
                self.run.names("history_student_not_created", _display(row), result[1])
            return
        if row is None:
            mapper._remember(legacy_id, (None, "source_missing"))
            return
        # Bu qaçışda ƏVVƏL yaradılmış hesab legacy-də eyni adamın ikinci sətridirsə (FİN / ad + ata adı) — o hesab;
        # delta-nın ``prepare`` qaydası ilə eyni: paketin bölgüsündən asılı olmayaraq bir adam = bir hesab.
        again = mapper._resolve(legacy_id, create=False)
        if again[1] != "not_found":
            mapper._remember(legacy_id, again)
            return
        first, last = text(row.get("first_name"), limit=150), text(row.get("last_name"), limit=150)
        if not first or not last:
            mapper._remember(legacy_id, (None, "name_unreadable"))
            return
        user = self._create_archived(legacy_id, row, first, last)
        mapper._remember(legacy_id, (user.pk, "history_archived_created"))
        mapper.created.append((legacy_id, user.pk))
        mapper.student_ids.add(user.pk)
        mapper.by_inst[str(legacy_id)] = user.pk
        mapper.by_name[(person_key(last), person_key(first))].append(
            (user.pk, person_key(row.get("father_name")), legacy_birth_date(row.get("birthday") or None))
        )
        self.run.names("history_student_archived_created", _display(row), f"myedu.student.{legacy_id}")

    def _create_archived(self, legacy_id, row, first: str, last: str):
        """``repair_accounts.create_account`` formasında staged hesab → ``alumni`` arxivi (cutover arxiv qolu)."""

        from apps.accounts.public import archive_staged_account, stage_imported_account

        from ..rehearsal_identity_placeholder import placeholder_email
        from ..repair_accounts import EVIDENCE_REASON_CODE, role_for
        from ..repair_archive import evidence_digest

        organization, actor = self.run.organization, self.run.actor
        alumni = self._alumni()
        with transaction.atomic():
            staged = stage_imported_account(
                organization=organization,
                role=role_for(organization, "student"),
                actor=actor,
                username=f"myedu.student.{legacy_id}",
                email=placeholder_email("student", int(legacy_id)),
                student_identifier=str(legacy_id),
            )
            user = staged.user
            User = django_apps.get_model("auth", "User")
            User._default_manager.filter(pk=user.pk).update(first_name=first, last_name=last)
            Membership = django_apps.get_model("organizations", "Membership")
            Membership.objects.filter(user_id=user.pk, organization=organization, is_active=False).update(
                role_id=alumni.pk
            )
            profile_fields = {"email_verified": False}
            patronymic = text(row.get("father_name"), limit=100)
            if patronymic:
                profile_fields["patronymic"] = patronymic
            birth = legacy_birth_date(row.get("birthday") or None)
            if birth is not None:
                profile_fields["birth_date"] = birth
            gender = student_gender(row)
            if gender != "unspecified":
                profile_fields["gender"] = gender
            UserProfile = django_apps.get_model("accounts", "UserProfile")
            UserProfile.objects.filter(user_id=user.pk, organization=organization).update(**profile_fields)
            archive_staged_account(
                user=User._default_manager.get(pk=user.pk),
                organization=organization,
                expected_role=alumni,
                actor=actor,
                email_authoritative=True,
                email_authority_evidence_digest=evidence_digest(
                    organization_pk=organization.pk, user_pk=user.pk, legacy_pk=str(legacy_id)
                ),
                email_authority_reason_code=EVIDENCE_REASON_CODE,
            )
        self.run.count("history.student.archived_created")
        self._sar_rows.append((int(legacy_id), user.pk, f"myedu.student.{legacy_id}", row))
        return user

    def _alumni(self):
        if self._alumni_role is None:
            from apps.accounts.public import ARCHIVE_ROLE_NAME

            Role = django_apps.get_model("organizations", "Role")
            self._alumni_role = Role.objects.filter(
                organization=self.run.organization, name=ARCHIVE_ROLE_NAME, is_active=True
            ).first()
            if self._alumni_role is None:
                raise RuntimeError("legacy_delta_history_alumni_role_unavailable")
        return self._alumni_role

    def _materialise_records(self) -> None:
        """SAR (qrup/proqram/kurikulum/il) + unikal FİN — ``repair_sar`` qaydası olduğu kimi."""

        from ..repair_sar import materialise

        rows = [
            (legacy_pk, user_pk, username, {**row, "fincode": row.get("fincode") or ""})
            for legacy_pk, user_pk, username, row in self._sar_rows
        ]
        created, sources = materialise(self.run.organization, rows, fin_occurrences=self.fin_counts)
        self.run.count("history.student.record_created", created)
        for key, value in sources.items():
            self.run.count(f"history.student.record.{key}", value)
        Record = django_apps.get_model("registrar", "StudentAcademicRecord")
        for user_pk, group_pk in Record.objects.filter(
            organization=self.run.organization, student_id__in=[row[1] for row in rows], is_active=True
        ).values_list("student_id", "group_id"):
            self.mapper.group_of[user_pk] = group_pk


def _majority_active(organization, unit) -> bool:
    """Qrupun aktiv SAR tələbələrinin YARIDAN ÇOXU aktiv ``student`` üzvlüyündədir."""

    Record = django_apps.get_model("registrar", "StudentAcademicRecord")
    Membership = django_apps.get_model("organizations", "Membership")
    members = set(
        Record.objects.filter(organization=organization, group=unit, is_active=True).values_list(
            "student_id", flat=True
        )
    )
    if not members:
        return False
    active = Membership.objects.filter(
        organization=organization, user_id__in=members, role__name="student", is_active=True, user__is_active=True
    ).count()
    return active * 2 > len(members)


def _year(value) -> int:
    digits = str(value or "").strip()
    return int(digits) if digits.isdigit() else 0


__all__ = ["HistoryAccounts"]
