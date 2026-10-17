"""«Forma 1» dərs yükü → kafedranın MÖVCUD tapşırıq sətirlərinə müəllim bölgüsü (sahib 2026-10-12).

Sətir YARADILMIR: Forma 1 sətri (semestr + fənn + qruplar) tapşırıq sənədinin sətrinə
tutuşdurulur (sənəd TAPŞIRIQ kitabçasından gəlib — əksik sətir əvvəlcə
``import_teaching_task_workbook --sheet …`` ilə yaradılır). Tutuşmayan sətir hesabatdadır.

* Müəllim — TAM AD ilə (soyad + ad sözləri xanada olmalıdır), yalnız bu kafedranın aktiv
  müəllim üzvlüklərində; tapılmayan / qeyri-müəyyən / başqa kafedradakı — hesabat. Hesab
  YARADILMIR. Operator açıq həll verə bilər: ``--teacher "Soyad Ad=istifadəçi.adı"``.
* Fənn — sətrin fənni (kataloq) və ya xana mətni ilə oxşarlıq (≥ 0.88, boşluq/şəkilçi fərqsiz,
  sondakı «BT/QM» kimi ixtisas teqləri atılır); fənni boş blok sətri üçün bəndlərdən biri —
  onda kataloqdakı fənn sətrə yazılır (``RowPlanApplier.fill_subject``).
* Qruplar — açarların kəsişməsi («235BİO İNG» = «235 BİO ing», «234 BİO AZ» = «234 BİO»).
* Saat — fəaliyyət üzrə yeganə müəllim sətrin bütün saatını alır; bir neçə müəllim varsa
  hər biri Forma 1-dəki saatını (``is_hourly_paid`` — saathesabı bölməsi / s.h. müəllim).
* Yazı yalnız :class:`~.task_load_reassign.RowPlanApplier` ilə (düzəliş axını + blokerlər).
"""

from __future__ import annotations

import difflib
import re
from collections import Counter, defaultdict

from django.db.models import Q

from apps.organizations.models import Membership, OrgUnit
from core.constants import OrgUnitType

from ..constants import ACTIVITY_TOTAL_FIELD, TaskStatus
from ..models import TeachingTask
from .distribution import teacher_loads
from .imports import normalize
from .people import chair_teacher_memberships, join_chair_as_teacher
from .task_form1_parsing import group_key, group_tokens, name_words
from .task_load_reassign import ASSIGNED, REASSIGNED
from .task_workbook_choice import CHOSEN_NONE, block_options, rich_lines
from .task_workbook_parsing import clean_subject_name, is_block, slug_name

SUBJECT_THRESHOLD = 0.88
_TAG_RE = re.compile(r"(?:\s+[A-ZƏİÖÜĞŞÇ]{1,4}(?:/[A-ZƏİÖÜĞŞÇ]{1,4})*)+\s*$")


def subject_slug(text: str) -> str:
    text = clean_subject_name(str(text or ""))
    text = re.sub(r"^\s*(ATMF|SF)\b[\s.:]*", "", text)
    return slug_name(_TAG_RE.sub("", text))


def find_chair(organization, name: str):
    wanted = normalize(re.sub(r"(?i)\s*kafedras[ıi]\s*$", "", name or ""))
    chairs = OrgUnit.objects.filter(organization=organization, unit_type=OrgUnitType.CHAIR, is_active=True)
    exact = [c for c in chairs if normalize(c.name) == wanted]
    found = exact or [c for c in chairs if normalize(c.name).startswith(wanted)]
    return found[0] if len(found) == 1 else None


class _RowIndex:
    """Tapşırıq sətirlərinin fənn/qrup açarları (bir dəfə hesablanır)."""

    def __init__(self, task):
        self.rows = list(task.rows.select_related("subject").prefetch_related("groups"))
        self.labels, self.option_labels, self.group_keys = {}, {}, {}
        for row in self.rows:
            labels = {subject_slug(row.subject_text)}
            if row.subject_id:
                labels.add(subject_slug(row.subject.name))
            elif is_block(row.subject_text):
                options, _ = block_options(rich_lines(row.subject_text))
                self.option_labels[row.pk] = {subject_slug(o.text): o.text for o in options}
            self.labels[row.pk] = {label for label in labels if label}
            keys = {group_key(u.name) for u in row.groups.all()}
            keys |= {group_key(t) for t in group_tokens(row.groups_text)}
            self.group_keys[row.pk] = keys

    @staticmethod
    def _score(a: str, labels) -> float:
        return max((difflib.SequenceMatcher(None, a, b).ratio() for b in labels), default=0.0)

    def match(self, entry) -> tuple[list, float]:
        """→ ([(sətir, fənni boş blok sətri üçün uyğun bənd mətni | ""), ...], oxşarlıq)."""
        wanted = subject_slug(entry.chosen_subject or entry.subject_text)
        scored = []
        for row in self.rows:
            if row.season != entry.season:
                continue
            if entry.group_keys and not (entry.group_keys & self.group_keys[row.pk]):
                continue
            score, option = self._score(wanted, self.labels[row.pk]), ""
            options = self.option_labels.get(row.pk, {})
            option_score = self._score(wanted, options)
            if option_score > score:
                score = option_score
                option = max(options.items(), key=lambda kv: difflib.SequenceMatcher(None, wanted, kv[0]).ratio())[1]
            if score >= SUBJECT_THRESHOLD:
                scored.append((score, row, option))
        if not scored:
            return [], 0.0
        best = max(score for score, _, _ in scored)
        chosen = [(row, option) for score, row, option in scored if score >= best - 0.02]
        if not entry.group_keys and len(chosen) > 1:
            return [], best  # qrupsuz sətir yalnız yeganə namizədə yazılır
        return chosen, best


class Form1Importer:
    def __init__(self, *, importer, chair, teacher_map=None, allow_outside_chair=False):
        self.importer = importer
        #: Sahib 2026-10-12: başqa kafedranın (və ya müəllim rolu olmayan — dekan müavini) TƏK uyğun hesabı qəbul.
        self.allow_outside_chair = allow_outside_chair
        self.org = importer.org
        self.chair = chair
        self.applier = importer.applier
        self.teacher_map = {frozenset(name_words(k)): v for k, v in (teacher_map or {}).items()}
        self.counters: Counter = Counter()
        self.report_rows: list[dict] = []
        self._teacher_cache: dict = {}
        self._chair_users = [
            m.user for m in chair_teacher_memberships(self.org, chair, include_unscoped=False) if m.user.is_active
        ]

    # ── müəllim ───────────────────────────────────────────────────────────
    def resolve_teacher(self, words: tuple) -> tuple:
        if words in self._teacher_cache:
            return self._teacher_cache[words]
        from django.contrib.auth import get_user_model

        result = (None, "not_found")
        for key, username in self.teacher_map.items():
            if key and key <= set(words):
                user = get_user_model().objects.filter(username=username, is_active=True).first()
                result = (user, "mapped") if user is not None else (None, "mapped_user_not_found")
                break
        else:
            found = {u.pk: u for u in self._chair_users if self._name_match(u, words)}
            if len(found) == 1:
                result = (next(iter(found.values())), "matched")
            elif len(found) > 1:
                result = (None, "ambiguous")
            elif self.allow_outside_chair and (outside := self._outside_users(words)) and len(outside) == 1:
                result = (outside[0], "matched_outside_chair")
                self._join_chair(outside[0])
            elif self._outside_chair(words):
                result = (None, "outside_chair")
        self.counters[f"teacher_{result[1]}"] += 1
        self._teacher_cache[words] = result
        return result

    @staticmethod
    def _name_match(user, words) -> bool:
        first, last = slug_name(user.first_name), slug_name(user.last_name)
        return bool(first and last) and first in words and last in words

    def _join_chair(self, user) -> None:
        """Başqa kafedranın müəllimi bu kafedranın yükünü alır → kafedrada ƏLAVƏ müəllim üzvlüyü (əsas deyil).

        Yük servisi müəllimi yalnız kafedra üzvü olanda təyin edir (`workload.teacher_not_in_chair`). Sahib
        2026-10-12 «hamısını bağla» qərarı ilə açıq əlavə; öz kafedrası dəyişmir; audit jurnalına yazılır."""
        if not self.importer.apply:
            return
        if join_chair_as_teacher(
            organization=self.org,
            user=user,
            chair=self.chair,
            actor_user=self.importer.actor_user,
            reason="workload.form1_import: başqa kafedranın müəllimi bu kafedranın yükünü alır (sahib qərarı)",
        ):
            self.counters["chair_membership_added"] += 1
        if user not in self._chair_users:
            self._chair_users.append(user)

    def _outside_users(self, words) -> list:
        """Təşkilatın İSTƏNİLƏN aktiv qeyri-tələbə üzvü (ad + soyad) — unikal istifadəçilər."""
        memberships = (
            Membership.objects.filter(organization=self.org, is_active=True, role__is_active=True)
            .exclude(role__name__in=("student", "lead_student", "alumni"))
            .select_related("user")
        )
        found = {m.user.pk: m.user for m in memberships if m.user is not None and m.user.is_active}
        return [u for u in found.values() if self._name_match(u, words)]

    def _outside_chair(self, words) -> bool:
        memberships = Membership.objects.filter(
            Q(organization=self.org, is_active=True, role__is_active=True),
            role__name__in=("teacher", "assistant"),
        ).select_related("user")
        return any(self._name_match(m.user, words) for m in memberships if m.user is not None)

    # ── əsas ──────────────────────────────────────────────────────────────
    def run(self, task: TeachingTask, entries: list, skipped: list) -> None:
        index = _RowIndex(task)
        contributions: dict = defaultdict(list)  # (row_pk, activity) → [(user_id|None, saat|None, hourly)]
        rows_by_pk = {row.pk: row for row in index.rows}
        entry_reports = {}
        for item in skipped:
            self.counters[f"line_{item['reason']}"] += 1
            self.report_rows.append({"line": item["line"], "subject": item["subject"], "rows": item["reason"]})
        for entry in entries:
            if entry.chosen_by == CHOSEN_NONE:
                continue  # parse_form1 «no_choice_marker» kimi qeyd edib
            user, teacher_action = self.resolve_teacher(entry.name_words)
            matched, score = index.match(entry)
            report = {
                "line": entry.line,
                "season": entry.season,
                "teacher": " ".join(entry.name_words),
                "teacher_action": teacher_action,
                "username": user.username if user is not None else "",
                "hourly": int(entry.hourly),
                "groups": entry.groups_text.replace("\n", " | "),
                "subject": clean_subject_name(entry.subject_text),
                "chosen_subject": entry.chosen_subject,
                "chosen_by": entry.chosen_by,
                "hours": " ".join(f"{a}={h}" for a, h in sorted(entry.hours.items())),
                "rows": f"matched:{len(matched)}" if matched else "no_task_row",
                "score": f"{score:.2f}",
            }
            self.report_rows.append(report)
            if not matched:
                self.counters["line_no_task_row"] += 1
                continue
            self.counters["line_matched"] += 1
            for row, option in matched:
                if option and row.subject_id is None:
                    report["rows"] += ";" + self._fill_subject(row, option)
                entry_reports.setdefault(row.pk, []).append(report)
                for activity, hours in entry.hours.items():
                    target = self._row_activity(row, activity, entry.hours)
                    if target is None:
                        report["rows"] += f";{activity}_not_in_row"
                        self.counters["activity_not_in_row"] += 1
                        continue
                    if target != activity:
                        report["rows"] += f";{activity}->{target}"
                        self.counters["activity_mapped"] += 1
                    activity = target
                    contributions[(row.pk, activity)].append(
                        (user.pk if user is not None else None, hours if len(matched) == 1 else None, entry.hourly)
                    )
        self._apply(task, rows_by_pk, contributions, entry_reports, index)

    @staticmethod
    def _row_activity(row, activity: str, entry_hours: dict):
        """Forma 1-in «Məşğələ» saatı sətirdə «Laboratoriya» kimi (və əksinə) ola bilər: sətirdə
        bu fəaliyyət yoxdursa, Forma 1 sətrinin özündə olmayan digər praktik fəaliyyətə yazılır."""
        if int(getattr(row, ACTIVITY_TOTAL_FIELD[activity], 0) or 0) > 0:
            return activity
        alternative = {"seminar": "lab", "lab": "seminar"}.get(activity)
        if (
            alternative
            and alternative not in entry_hours
            and int(getattr(row, ACTIVITY_TOTAL_FIELD[alternative], 0) or 0) > 0
        ):
            return alternative
        return None

    def _fill_subject(self, row, option: str) -> str:
        """Fənni boş blok sətri: Forma 1-dəki bəndin kataloq fənni sətrə yazılır (yaradılmır)."""
        subject = self.importer.subject_index.get(normalize(option))
        if subject is None:
            self.counters["subject_not_in_catalog"] += 1
            return "subject_not_in_catalog"
        return self.applier.fill_subject(row, subject) or "subject_kept"

    def _desired(self, row, activity, items) -> list | str:
        total = int(getattr(row, ACTIVITY_TOTAL_FIELD[activity], 0) or 0)
        resolved = [item for item in items if item[0] is not None]
        if not resolved:
            return []
        merged: dict = {}
        for user_id, hours, hourly in resolved:
            key = (user_id, hourly)
            merged[key] = None if (hours is None or merged.get(key, 0) is None) else merged.get(key, 0) + hours
        if len(merged) == 1 and len(resolved) == len(items):
            (user_id, hourly), _ = next(iter(merged.items()))
            return [(user_id, total, hourly)]
        if any(hours is None for hours in merged.values()):
            return "split_unclear"
        return [(user_id, min(hours, total), hourly) for (user_id, hourly), hours in merged.items()]

    def _apply(self, task, rows_by_pk, contributions, entry_reports, index) -> None:
        loads_before = teacher_loads(task)  # yenidən təsdiqdə yalnız yeni/dəyişən müəllimə bildiriş
        if self.importer.apply and contributions and task.status == TaskStatus.DRAFT:
            self.importer._approve_official_workbook(task)
        per_row: dict = defaultdict(dict)
        blocked: dict = {}
        for (row_pk, activity), items in contributions.items():
            desired = self._desired(rows_by_pk[row_pk], activity, items)
            if isinstance(desired, str):
                blocked[row_pk] = desired
            elif desired:
                per_row[row_pk][activity] = desired
        written = 0
        for row_pk in sorted(set(per_row) | set(blocked), key=str):
            row = rows_by_pk[row_pk]
            if row_pk in blocked:
                action = f"blocked:{blocked[row_pk]}"
                self.applier.counters["blocked"] += 1
            else:
                action, detail = self.applier.apply_plan(row, per_row[row_pk])
                written += action in (ASSIGNED, REASSIGNED)
                action = f"{action}:{detail}" if detail else action
            for report in entry_reports.get(row_pk, []):
                report.setdefault("assignment", [])
                report["assignment"].append(action)
        for report in self.report_rows:
            if isinstance(report.get("assignment"), list):
                report["assignment"] = " ; ".join(sorted(set(report["assignment"])))
        untouched = [row for row in index.rows if row.pk not in entry_reports]
        self.counters["task_rows_not_in_form1"] = len(untouched)
        if self.importer.apply:
            task.refresh_from_db(fields=["status"])
            amended = task.status == TaskStatus.AMENDED and self.applier.counters["amendment_opened"]
            if (written and task.status in (TaskStatus.APPROVED, TaskStatus.DISTRIBUTING)) or amended:
                self.importer._confirm_and_enroll(task, loads_before=loads_before)


__all__ = ["Form1Importer", "SUBJECT_THRESHOLD", "find_chair", "subject_slug"]
