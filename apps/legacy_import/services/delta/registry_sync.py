"""``registry_sync`` fazası — köhnə sistemin snapshot vəziyyətinə görə AKTİV tələbə reyestrinin nizamlanması.

Sahib 2026-10-25: «yeni jurnal datalarında analiz çıxardarsa, aktiv tələbə sayında nizamlamağa çalış».
Delta paketinin ``students`` bölməsi köhnə sistemin cari vəziyyətidir (qrup, ``azadedildi``) və cutover
snapshot-u ilə fərq (``baseline``) daşıyır. Faza fərqləri YALNIZ rəsmi axınla tətbiq edir:

* **qrup** — ``registrar.movements.create_movement(kind=group_transfer)`` (reyestrin «Qrupdan qrupa
  köçürmə» əmri: iki fazalı sübut + jurnal qeydiyyatlarının nəsil zənciri + ``StudentMovement`` ledger-i);
* **azad edilmə** — eyni servis ``kind=expulsion`` (status, cari qeydiyyatların dondurulması, giriş bağlanır);
  əmr nömrəsi/tarixi köhnə sistemdəndir (``order_no`` / ``order_date``; yoxdursa sinxron əmri).

Nə vaxt TOXUNULMUR (yalnız hesabat):

* köhnə sistemdə dəyişiklik cutover-DƏN SONRA deyil (``baseline`` qrupu = cari qrup) — yeni sistem qalibdir;
* yeni sistemdə cutover-dən sonra əl ilə hərəkət/status/köçürmə izi var (RİM/dekanlıq) — yeni sistem qalibdir;
* alt qrup ↔ ana qrup fərqi (``settings.parent_group`` və ya ad şablonu) — köçürmə deyil;
* hədəf qrup tapılmır, aktiv deyil və ya «silinməli»/«xaric» qabıdır; tələbənin bir neçə aktiv qeydi var;
  legacy-də eyni adamın iki sətri fərqli qrup göstərir; status ``enrolled`` deyil.

Bildiriş GETMİR (delta qaydası). Ekrana yalnız SAYLAR; adlar və qrup cədvəli ``--names-out`` faylına.
İdempotentdir: ikinci qaçışda qrup eynidir / status artıq ``expelled`` — 0 yazı.
"""

from __future__ import annotations

import datetime
from collections import Counter, defaultdict

from django.apps import apps as django_apps
from django.core.exceptions import ValidationError
from django.db import transaction

from .resolve import person_key, text

#: Cutover snapshot-unun tarixi (myedu_old) — bundan sonrakı yeni sistem izləri «əl ilə dəyişiklik» sayılır.
CUTOVER_DATE = datetime.date(2026, 8, 17)
#: Köhnə sistemin snapshot tarixi (paketdə ``snapshot.source_date`` yoxdursa).
DEFAULT_SOURCE_DATE = datetime.date(2026, 10, 21)
SYNC_REASON = "Köhnə sistemdən sinxron"
_JUNK_GROUP_MARKERS = ("silinmeli", "xaricolan", "test")
#: Adlı siyahıya düşən (sahib qərarı tələb edən) ötürülən hallar.
_NAMED_SKIPS = (
    "group.system_changed",
    "expel.system_changed",
    "group.legacy_duplicate_conflict",
    "group.other_speciality",
    "group.subgroup_parent",
    "group.target_unusable",
)


def sync_registry(run) -> None:
    """Fazanın giriş nöqtəsi (``DeltaRun.run``)."""

    RegistrySync(run).execute()


class RegistrySync:
    def __init__(self, run):
        self.run = run
        self.org = run.organization
        snapshot = run.bundle.get("snapshot") or {}
        self.source_date = _date(snapshot.get("source_date")) or DEFAULT_SOURCE_DATE
        self.cutover = _date(snapshot.get("cutover_date")) or CUTOVER_DATE
        self.order_number = f"KS-SINX-{self.source_date:%Y%m%d}"
        self.reason = f"{SYNC_REASON}: {self.source_date:%Y-%m-%d} vəziyyəti"
        self.Record = django_apps.get_model("registrar", "StudentAcademicRecord")

    # ── əsas axın ─────────────────────────────────────────────────────────
    def execute(self) -> None:
        rows_by_user = self._resolve_rows()
        expelled_by_user = self._resolve_expelled(set(rows_by_user))
        records = self._records(set(rows_by_user) | set(expelled_by_user))
        touched = self._manually_changed({record.pk for record in records.values() if isinstance(record, self.Record)})
        before = self._group_counts()
        period = self.org.academic_periods.filter(is_current=True, is_active=True).first()
        for scope, mapping in (("in_snapshot", rows_by_user), ("not_in_snapshot", expelled_by_user)):
            for user_id, rows in sorted(mapping.items(), key=lambda item: str(item[0])):
                record = records.get(user_id)
                if record == "multi" or record is None:
                    self.run.count(f"registry.skip.{'multi_record' if record else 'no_record'}")
                    continue
                self._apply(self._decide(rows, record, touched, scope=scope), record, rows[0], period)
        self._not_in_snapshot(set(rows_by_user))
        self._group_report(before, self._group_counts(), self._legacy_counts())

    def _resolve_rows(self) -> dict:
        """``user_id → [legacy sətirləri]`` (həll olunmayanlar yalnız sayılır)."""

        out: dict = defaultdict(list)
        for row in sorted(self.run.bundle["students"], key=lambda item: item["id"]):
            user_id, outcome = self.run.students.resolve(row["id"], create=False)
            if user_id is None:
                self.run.count("registry.unresolved")
                continue
            out[user_id].append(row)
        return out

    def _resolve_expelled(self, known_users) -> dict:
        """Paketin ``expelled_students`` bölməsi (cari semestrdə olmayan azad edilmişlər) — YALNIZ güclü sübutla:
        cutover ledger-i, ``institutional_identifier`` və ya FİN (ad tutuşdurması yoxdur). Əsas bölmədə sətri olan
        hesab (yenidən qəbul) buraya düşmür."""

        from .resolve import ledger_map

        rows = sorted(self.run.bundle.get("expelled_students") or [], key=lambda item: item["id"])
        if not rows:
            return {}
        UserProfile = django_apps.get_model("accounts", "UserProfile")
        ids = [str(row["id"]) for row in rows]
        ledger = ledger_map(self.org, "student", ids)
        by_inst = dict(
            UserProfile.objects.filter(institutional_identifier__in=ids).values_list(
                "institutional_identifier", "user_id"
            )
        )
        fins = sorted({_fin(row) for row in rows} - {""})
        by_fin = {
            fin.upper(): user_id
            for fin, user_id in UserProfile.objects.filter(fin__in=fins).values_list("fin", "user_id")
            if fin
        }
        out: dict = defaultdict(list)
        for row in rows:
            key = str(row["id"])
            user_id = int(ledger[key]) if key in ledger else by_inst.get(key) or by_fin.get(_fin(row))
            if user_id is None:
                self.run.count("registry.expelled_unlinked")
                continue
            if user_id in known_users:
                self.run.count("registry.expelled_readmitted")
                continue
            out[user_id].append({**row, "azadedildi": 1})
        return out

    def _records(self, user_ids) -> dict:
        """``user_id → StudentAcademicRecord | "multi"`` — enrolled / akademik məzuniyyət qeydləri."""

        out: dict = {}
        queryset = self.Record.objects.filter(
            organization=self.org, student_id__in=list(user_ids), status__in=("enrolled", "academic_leave")
        ).select_related("group", "program")
        for record in queryset:
            out[record.student_id] = "multi" if record.student_id in out else record
        expelled = set(
            self.Record.objects.filter(
                organization=self.org, student_id__in=[uid for uid in user_ids if uid not in out]
            ).values_list("student_id", flat=True)
        )
        for user_id in expelled:
            out.setdefault(user_id, _Closed())
        return out

    def _manually_changed(self, record_ids) -> set:
        """Cutover-dən sonra yeni sistemdə əl ilə hərəkət/köçürmə/status izi olan qeydlər (sinxronun öz izi xaric)."""

        if not record_ids:
            return set()
        Movement = django_apps.get_model("registrar", "StudentMovement")
        AuditLog = django_apps.get_model("audit", "AuditLog")
        ids = list(record_ids)
        changed = set(
            Movement.objects.filter(organization=self.org, record_id__in=ids, created_at__date__gte=self.cutover)
            .exclude(reason__startswith=SYNC_REASON)
            .values_list("record_id", flat=True)
        )
        audits = (
            AuditLog.objects.filter(
                resource_type__in=("registrar.group_transfer", "registrar.student_status"),
                resource_id__in=[str(pk) for pk in ids],
                created_at__date__gte=self.cutover,
            )
            .exclude(reason__startswith=SYNC_REASON)
            .values_list("resource_id", flat=True)
        )
        changed.update(_uuid(value) for value in audits)
        return changed

    # ── qərar ─────────────────────────────────────────────────────────────
    def _decide(self, rows, record, touched, *, scope: str = "in_snapshot") -> dict:
        if isinstance(record, _Closed):
            return {"kind": "already_closed"}
        active = [row for row in rows if int(row.get("azadedildi") or 0) != 1]
        if not active:
            if record.pk in touched:
                return {"kind": "expel.system_changed"}
            return {"kind": f"expel.{scope}", "expel": True, "row": rows[0]}
        targets = {}
        for row in active:
            unit, how = self._target(row.get("group_id"))
            targets[getattr(unit, "pk", how)] = (unit, row)
        if len(targets) > 1:
            return {"kind": "group.legacy_duplicate_conflict"}
        ((target, row),) = targets.values()
        if target is None:
            return {"kind": "group.target_missing"}
        decision = {"target": target, "row": row}
        if target.pk == record.group_id:
            return {**decision, "kind": "group.same"}
        if not target.is_active or _junk(target.name):
            return {**decision, "kind": "group.target_unusable"}
        if record.group is not None and _parent_sub(record.group, target):
            return {**decision, "kind": "group.subgroup_parent"}
        if not _same_speciality(record, target):
            return {**decision, "kind": "group.other_speciality"}
        evidence = _legacy_evidence(row)
        if evidence is None:
            return {**decision, "kind": "group.legacy_unchanged_system_wins"}
        if record.pk in touched:
            return {**decision, "kind": "group.system_changed"}
        if record.status != "enrolled":
            return {**decision, "kind": f"group.status_{record.status}"}
        return {**decision, "kind": f"group.transfer.{evidence}", "transfer": True}

    def _legacy_counts(self) -> Counter:
        """Köhnə sistemdə (paketin cari semestr tələbələri) azad edilməmiş tələbə sayı — hədəf qrup üzrə."""

        counts: Counter = Counter()
        for row in self.run.bundle["students"]:
            if int(row.get("azadedildi") or 0) == 1:
                continue
            unit, _how = self._target(row.get("group_id"))
            if unit is not None:
                counts[unit.pk] += 1
        return counts

    def _target(self, legacy_group_id):
        legacy = self.run.legacy_groups.get(legacy_group_id)
        if legacy is None:
            return None, "missing"
        return self.run.catalog.group_for(legacy)

    # ── tətbiq ────────────────────────────────────────────────────────────
    def _apply(self, decision, record, row, period) -> None:
        kind = decision["kind"]
        if not (decision.get("transfer") or decision.get("expel")):
            self.run.count(f"registry.{kind}")
            if kind in _NAMED_SKIPS:
                self.run.names(f"registry_{kind}", _display(row), self._label(record, decision))
            return
        from apps.registrar.public import movements

        try:
            with transaction.atomic():
                if decision.get("expel"):
                    order_number, order_date = self._expel_order(decision["row"])
                    movements.create_movement(
                        record=record,
                        kind=movements.MovementKind.EXPULSION,
                        order_number=order_number,
                        order_date=order_date,
                        reason=self.reason,
                        actor=self.run.actor,
                    )
                else:
                    movements.create_movement(
                        record=record,
                        kind=movements.MovementKind.GROUP_TRANSFER,
                        order_number=self.order_number,
                        order_date=self.source_date,
                        reason=self.reason,
                        actor=self.run.actor,
                        period=period,
                        new_group=decision["target"],
                    )
        except (movements.MovementError, ValidationError) as error:
            code = getattr(error, "code", "") or error.__class__.__name__
            self.run.count(f"registry.{kind.split('.')[0]}.failed")
            self.run.names(f"registry_{kind}_failed", _display(row), f"{self._label(record, decision)} · {code}")
            return
        self.run.count(f"registry.{kind}")
        self.run.count("written.student_movements")
        self.run.names(f"registry_{kind}", _display(row), self._label(record, decision))

    def _expel_order(self, row):
        number = text(row.get("order_no"), limit=64) or self.order_number
        when = _date(row.get("order_date"))
        if when is None or when > self.source_date:
            when = self.source_date
        return number, when

    def _label(self, record, decision) -> str:
        current = getattr(getattr(record, "group", None), "name", "") or "—"
        target = getattr(decision.get("target"), "name", "")
        return f"{current} → {target}" if target and target != current else current

    # ── hesabat ───────────────────────────────────────────────────────────
    def _group_counts(self) -> Counter:
        from django.db.models import Count

        rows = (
            self.Record.objects.filter(organization=self.org, status="enrolled", group__isnull=False)
            .values("group_id")
            .annotate(total=Count("id"))
        )
        return Counter({row["group_id"]: row["total"] for row in rows})

    def _not_in_snapshot(self, resolved_users) -> None:
        """Yeni sistemdə aktiv, amma köhnə sistemin cari semestr snapshot-unda olmayan tələbələr (yalnız say)."""

        years = self.Record.objects.filter(organization=self.org, status="enrolled").exclude(
            student_id__in=list(resolved_users)
        )
        by_year = Counter(years.values_list("admission_year", flat=True))
        self.run.count("registry.system_active_not_in_snapshot", sum(by_year.values()))
        for year, amount in by_year.items():
            self.run.count(f"registry.system_active_not_in_snapshot.year_{year or 'unknown'}", amount)

    def _group_report(self, before: Counter, after: Counter, legacy: Counter) -> None:
        self.run.count("registry.active_before", sum(before.values()))
        self.run.count("registry.active_after", sum(after.values()))
        OrgUnit = django_apps.get_model("organizations", "OrgUnit")
        keys = set(before) | set(after) | set(legacy)
        names = dict(OrgUnit.objects.filter(pk__in=list(keys)).values_list("pk", "name"))
        for key in sorted(keys, key=lambda pk: names.get(pk, "")):
            old, new, wanted = before.get(key, 0), after.get(key, 0), legacy.get(key, 0)
            if old != new:
                self.run.count("registry.groups_changed")
            if key in legacy and new != wanted:
                self.run.count("registry.groups_differ_from_legacy")
            if old != new or (key in legacy and new != wanted):
                self.run.names("registry_group_count", names.get(key, str(key)), f"{old} → {new} · köhnə: {wanted}")


class _Closed:
    """Tələbənin yalnız bağlı (xaric/məzun) qeydi var."""


def _legacy_evidence(row) -> str | None:
    """Köhnə sistemdə qrup cutover-dən SONRA dəyişibmi: ``moved`` / ``new`` / ``None`` (dəyişməyib)."""

    baseline = row.get("baseline") or {}
    if baseline and baseline.get("group_id") not in (None, row.get("group_id")):
        return "moved"
    if row.get("is_new"):
        return "new"
    return None


def _parent_sub(current, target) -> bool:
    """Alt qrup ↔ ana qrup (iz və ya ad şablonu, hər iki istiqamət) — köçürmə sayılmır."""

    from apps.registrar.public import subgroup_rollup

    def parent_of(unit):
        raw = unit.settings if isinstance(unit.settings, dict) else {}
        return str(raw.get("parent_group") or "")

    if parent_of(target) == str(current.pk) or parent_of(current) == str(target.pk):
        return True
    one, other = _dotless(current.name), _dotless(target.name)
    return subgroup_rollup.is_subgroup_of(one, other) or subgroup_rollup.is_subgroup_of(other, one)


def _dotless(name) -> str:
    """«136 Sİ» ↔ «136 Si-1»: ``"İ".casefold()`` nöqtəli «i̇» verir və ad şablonu tutmur — I/İ/ı eyniləşdirilir."""

    return str(name or "").replace("İ", "I").replace("ı", "i")


def _same_speciality(record, target) -> bool:
    """Hədəf qrup tələbənin ixtisasındadır (qrupun ata vahidi = cari qrupun atası və ya proqramın ixtisası).

    Qrup köçürməsi proqramı dəyişmir — başqa ixtisasın qrupuna köçürmə ``program_transfer`` qərarıdır.
    """

    allowed = {getattr(record.group, "parent_id", None), getattr(record.program, "specialty_unit_id", None)} - {None}
    return not allowed or target.parent_id in allowed


def _junk(name) -> bool:
    key = person_key(name)
    return any(marker in key for marker in _JUNK_GROUP_MARKERS)


def _fin(row) -> str:
    return str((row or {}).get("fincode") or "").strip().upper()


def _date(value):
    try:
        return datetime.date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def _uuid(value):
    import uuid

    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return value


def _display(row: dict) -> str:
    return " ".join(
        part for part in (text(row.get("last_name")), text(row.get("first_name")), text(row.get("father_name"))) if part
    )


__all__ = ["CUTOVER_DATE", "SYNC_REASON", "RegistrySync", "sync_registry"]
