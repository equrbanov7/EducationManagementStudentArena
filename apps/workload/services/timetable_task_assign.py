"""Dərs cədvəli (.docx) → tapşırığın BOŞ sətir fəaliyyətinə cədvəldəki müəllim (sahib 2026-10-12 / 10-15).

Forma 1 göndərməyən kafedraların («Mexanika və riyaziyyat», «Yer kadastrı və meşəçilik» …) tapşırıq
sətirləri prod-dadır, amma müəllim bölgüsü yoxdur → açılış (jurnal) yaranmır → ``import_timetable_docx``
hüceyrəni ``subject_not_in_group`` kimi atır. Sahib: «cədvəli oxu; orada dərsi olan hər kəsi sistemdə
seç və yüklə» / «nələr yoxdursa əlavə olunmayıbsa hamısını et».

QAYDALAR (heç nə YARADILMIR: qrup, hesab; sətir/fənn/tapşırıq yalnız ``create_missing_rows`` ilə —
:mod:`.timetable_missing_rows`, sahib 2026-10-17 «dərs yükündə olmayanları da əlavə et»):

* Oxu — ``registrar.schedule_docx_parse.parse_docx``; qrup başlığı → qrup vahidləri
  ``schedule_docx_match.Resolver.group_units`` (alt qrup başlığı ana qrupu da gətirir).
* Sətir — həmin tədris ilinin ləğv olunmamış tapşırıqlarında, semestri (və ya semestri boşdursa fəsli)
  uyğun, qrupları başlığın qruplarından birini daxil edən, fənni OLAN dərs sətri. Fənn oxşarlığı
  matcher-in ``subject_score`` qaydası ilə (≥ 0.80; fərqli fənn 0.04-dən yaxındırsa ``subject_ambiguous``;
  yalnız hissə — ``subject_partial``). Seçmə blok sətri seçilmiş fənni (``row.subject``) ilə sayılır.
* Növ — hüceyrədə yoxdursa sətrin saat bölgüsündə TƏK fəaliyyət varsa o (matcher kimi); magistratura
  hüceyrəsində (növ işarəsi yoxdur) bölgüdən çıxmırsa mühazirə (``kind_default_lecture``); sətirdə
  hüceyrənin növü yoxdursa seminar↔laboratoriya (Forma 1 qaydası), yoxsa ``activity_not_in_row``.
* Yalnız BOŞ fəaliyyət — bölgü yoxdur və ya hamısı «Vakant»dır. Real müəllim varsa → ``already_assigned``
  (toxunulmur). Saat — sətrin PLAN saatı (``ACTIVITY_TOTAL_FIELD``, Forma 1 ilə eyni), ``is_hourly_paid=False``.
* Müəllim («Soyad İ.» və ya magistraturanın TAM ADI «Ad Soyad», hər iki sıra) — əvvəl sətrin kafedrasının
  müəllim üzvləri (dəqiq, sonra kiçik yazı xətası);
  sonra yalnız ``allow_outside_chair`` ilə təşkilatda TƏK aktiv müəllim / əməkdaş hesabı → kafedrada ƏLAVƏ
  müəllim üzvlüyü (``people.join_chair_as_teacher``, audit). Çox mənalı / tapılmayan → hesabat, yazı yox.
* Toplama — bir (sətir, fəaliyyət) bir dəfə yazılır; hüceyrələrdə fərqli müəllimlər → ``conflict``
  (yalnız hər biri AYRI alt qrupdadırsa və sətrin ``subgroup_count``-u alt qrup sayına bərabərdirsə saat
  bərabər bölünür). Həll olunmamış müəllimli hüceyrə də həmin cütü ``conflict`` edir.
* Yazı — yalnız :class:`~.task_load_reassign.RowPlanApplier` (düzəliş axını, blokerlər, açılış sinxronu);
  sonunda Forma 1 kimi ``Importer._confirm_and_enroll`` (bölgü təsdiqi → açılış + tələbə qeydiyyatı).
  Hər tapşırıq (= kafedra + il) öz savepoint-indədir və işdə BİR dəfə emal olunur: yeni sətirlər
  (:mod:`.timetable_missing_rows`) və mövcud sətirlərin bölgüsü eyni addımdadır → rəsmi təsdiq və bölgü
  təsdiqi bir dəfə (2026-10-17 rəyi: əvvəl köhnəlmiş ``draft`` statusu ilə ikinci dəfə təsdiqlənirdi).
  Təsdiq alınmasa həmin tapşırığın dəyişiklikləri VƏ sayları geri alınır (``task_blocked``).
  Əvvəl bölünmüş sənədin yenidən təsdiqi müəllimlərə təkrar «Dərs yükü təyin edildi» GÖNDƏRMİR — yalnız bu işdə
  bölgüsü yeni yaranan / dəyişən müəllimə bir dəfə (``distribution.teacher_loads``, sahib 2026-10-17).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q

from apps.registrar.public import schedule_docx_match, schedule_docx_parse

from ..constants import ACTIVITY_TOTAL_FIELD, TEACHER_ROLE_NAMES, TEACHING_ACTIVITIES, RowKind, Season, TaskStatus
from ..models import TeacherAssignment, TeachingTaskRow
from .distribution import teacher_loads
from .people import chair_teacher_memberships, join_chair_as_teacher
from .plan_calendar import _rank, season_from_period
from .scoping import WorkloadDenied
from .task_form1_import import Form1Importer
from .task_load_reassign import ASSIGNED, REASSIGNED
from .task_workbook_parsing import clean_subject_name, is_block
from .timetable_missing_rows import ROW_CREATED, ROW_PLANNED, MissingRowCreator

REPORT_HEADER = [
    "table", "row", "weekday", "start", "end", "group", "sub", "subject", "kind", "teacher",
    "status", "detail", "chair", "row_subject", "activity", "score", "username", "teacher_action", "assignment",
]  # fmt: skip

#: Hüceyrə statusları (stdout-da saylar).
PLANNED = "planned"
ALREADY_ASSIGNED = "already_assigned"
CONFLICT = "conflict"
_NON_STUDENT_EXCLUDE = ("student", "lead_student", "alumni")
_ACTIVITIES = tuple(str(activity) for activity in TEACHING_ACTIVITIES)
_JOIN_REASON = (
    "workload.timetable_assign: cədvəldəki müəllim bu kafedranın boş tapşırıq sətrini alır (sahib qərarı 2026-10-12)"
)


def period_season(period) -> str:
    """Dövrün fəsli — ``plan_calendar`` qaydası (dəqiq ad → addakı söz → başlanğıc ayı)."""
    ranked = [(rank, season) for season in Season.values if (rank := _rank(period, season)) is not None]
    return min(ranked)[1] if ranked else season_from_period(period)


@dataclass
class Cell:
    entry: object
    status: str = ""
    detail: str = ""
    row: object = None
    activity: str = ""
    score: float = 0.0
    user: object = None
    teacher_action: str = ""
    assignment: str = ""
    chair: object = None  # yeni sətir planı (dry-run-da sətir yoxdur, kafedra hesabatda görünsün)

    @property
    def sub(self) -> str:
        return self.entry.group.sub or self.entry.text.sub_group or ""

    def csv_row(self) -> list:
        entry, text = self.entry, self.entry.text
        row = self.row
        return [
            entry.table, entry.row, entry.weekday, entry.start.strftime("%H:%M"), entry.end.strftime("%H:%M"),
            entry.group.display, self.sub, text.subject, text.kind, text.teacher, self.status, self.detail,
            getattr(getattr(getattr(row, "task", None), "chair", None) or self.chair, "name", ""),
            getattr(getattr(row, "subject", None), "name", ""), self.activity,
            f"{self.score:.3f}" if self.score else "", getattr(self.user, "username", ""), self.teacher_action,
            self.assignment,
        ]  # fmt: skip


def _token_key(token: str) -> str:
    return " ".join(schedule_docx_parse.fold(token).replace(".", " ").split())


def parse_teacher_map(values) -> dict:
    """«Soyad İ.=istifadəçi.adı» (vergüllə və ya təkrarlanan) → ``{token: username}``."""
    result = {}
    for value in values or []:
        for part in str(value).split(","):
            token, sep, username = part.partition("=")
            if sep and token.strip() and username.strip():
                result[token.strip()] = username.strip()
    return result


def _matches(users, token: str, *, fuzzy: bool) -> list:
    """``schedule_docx_match`` müəllim qaydası: «Soyad İ.» (dəqiq soyad / ≥ ``TEACHER_FUZZY`` yazı xətası + baş
    hərf) və ya TAM AD «Ad Soyad» (hər iki sıra)."""
    return schedule_docx_match.teacher_matches(users, token, fuzzy=fuzzy)


class TimetableTaskAssigner:
    def __init__(
        self, *, importer, period, allow_outside_chair: bool = False, teacher_map=None, create_missing_rows=False
    ):
        self.importer = importer
        self.org = importer.org
        self.year = importer.year
        self.period = period
        self.applier = importer.applier
        self.allow_outside_chair = allow_outside_chair
        self.counters: Counter = Counter()
        self.cells: list[Cell] = []
        self._chair_users: dict = {}
        self._teacher_cache: dict = {}
        self._org_pools = None
        self._outside: set = set()  # (kafedra_id, user_id) — yazıdan əvvəl kafedraya üzv edilməli
        # Operatorun açıq xəritəsi («Əmiraslanlı F.=fatma.emiraslanova.2024»): soyad yazılışı fərqlidirsə.
        self.teacher_map = {_token_key(k): v for k, v in (teacher_map or {}).items()}
        self.create_missing_rows = create_missing_rows

    # ── sətirlər ──────────────────────────────────────────────────────────
    def _load_rows(self) -> None:
        season = period_season(self.period)
        rows = (
            TeachingTaskRow.objects.filter(
                organization=self.org,
                task__academic_year=self.year,
                row_kind=RowKind.TEACHING,
                subject__isnull=False,
            )
            .exclude(task__status=TaskStatus.CANCELLED)
            .filter(Q(period=self.period) | Q(period__isnull=True, season=season))
            .select_related("task", "task__chair", "subject")
            .prefetch_related("groups")
        )
        self.rows_by_group: dict = defaultdict(list)
        for row in rows:
            for group in row.groups.all():
                self.rows_by_group[group.pk].append(row)
        self.taken: dict = defaultdict(set)
        for row_id, activity, teacher_id in TeacherAssignment.objects.filter(
            row__in=[row for rows in self.rows_by_group.values() for row in rows], activity__in=_ACTIVITIES
        ).values_list("row_id", "activity", "teacher_id"):
            self.taken[(row_id, str(activity))].add(teacher_id)

    @staticmethod
    def _row_names(row) -> list:
        names = [row.subject.name]
        text = clean_subject_name(row.subject_text or "")
        if text and not is_block(text):
            names.append(text)
        return names

    def _best_rows(self, rows, subject: str):
        """→ (ən yaxşı sətirlər, oxşarlıq, səbəb) — matcher-in ``Resolver._best`` qaydası sətirlər üzərində."""
        score = schedule_docx_match.subject_score
        scored = sorted(
            ((max(score(subject, name) for name in self._row_names(row)), row) for row in rows), key=lambda x: -x[0]
        )
        if not scored or scored[0][0] < schedule_docx_match.SUBJECT_MIN_SCORE:
            partial = any(
                schedule_docx_match.subject_contains(name, subject) for row in rows for name in self._row_names(row)
            )
            return [], 0.0, ("subject_partial" if partial else "subject_not_in_group")
        best = scored[0][0]
        top = [row for value, row in scored if best - value < schedule_docx_match.SUBJECT_MARGIN]
        if len({row.subject_id for row in top}) > 1:
            return [], best, "subject_ambiguous"
        return top, best, ""

    @staticmethod
    def _activity(row, kind: str, default: str = "") -> tuple[str, str]:
        if kind:
            target = Form1Importer._row_activity(row, kind, {kind: 0})
            if target is None:
                return "", "activity_not_in_row"
            return target, (f"{kind}->{target}" if target != kind else "")
        kinds = [a for a in _ACTIVITIES if int(getattr(row, ACTIVITY_TOTAL_FIELD[a], 0) or 0) > 0]
        if len(kinds) == 1:
            return kinds[0], "kind_from_hours"
        if not kinds:  # sətirdə auditoriya saatı yoxdur — yazılacaq fəaliyyət yoxdur
            return "", "kind_unknown"
        return schedule_docx_match.default_kind(kinds, default)  # registrar matcher-i ilə eyni qayda

    # ── müəllim ───────────────────────────────────────────────────────────
    def _chair_pool(self, chair) -> list:
        if chair.pk not in self._chair_users:
            self._chair_users[chair.pk] = list(
                {
                    m.user.pk: m.user
                    for m in chair_teacher_memberships(self.org, chair, include_unscoped=False)
                    if m.user is not None and m.user.is_active
                }.values()
            )
        return self._chair_users[chair.pk]

    def _org_pool(self) -> tuple[list, list]:
        """(təşkilatın aktiv müəllim-rollu hesabları, bütün aktiv qeyri-tələbə hesabları)."""
        if self._org_pools is None:
            Membership = django_apps.get_model("organizations", "Membership")
            teachers, staff = {}, {}
            memberships = (
                Membership.objects.filter(
                    organization=self.org, is_active=True, role__is_active=True, user__is_active=True
                )
                .exclude(role__name__in=_NON_STUDENT_EXCLUDE)
                .select_related("user", "role")
            )
            for membership in memberships:
                staff[membership.user.pk] = membership.user
                if membership.role.name in TEACHER_ROLE_NAMES:
                    teachers[membership.user.pk] = membership.user
            self._org_pools = (list(teachers.values()), list(staff.values()))
        return self._org_pools

    def resolve_teacher(self, chair, token: str) -> tuple:
        key = (chair.pk, token)
        if key not in self._teacher_cache:
            self._teacher_cache[key] = self._resolve_teacher(chair, token)
        return self._teacher_cache[key]

    def mapped_teacher(self, token: str):
        """Operatorun açıq xəritəsi: → (user|None, action) və ya ``None`` (xəritədə yoxdur)."""
        mapped = self.teacher_map.get(_token_key(token))
        if not mapped:
            return None
        user = get_user_model().objects.filter(username=mapped, is_active=True).first()
        return (user, "teacher_map") if user is not None else (None, "teacher_map_unknown")

    def _resolve_teacher(self, chair, token: str) -> tuple:
        mapped = self.mapped_teacher(token)
        if mapped is not None:
            user, action = mapped
            if user is not None and user not in self._chair_pool(chair):
                self._outside.add((chair.pk, user.pk))  # açıq xəritə = operatorun qərarı
            return user, action
        if not schedule_docx_match.split_teacher(token)[0]:
            return None, "teacher_missing"
        pool = self._chair_pool(chair)
        for fuzzy, action in ((False, "chair"), (True, "chair_fuzzy")):
            found = _matches(pool, token, fuzzy=fuzzy)
            if len(found) == 1:
                return found[0], action
            if len(found) > 1:
                return None, "teacher_ambiguous"
        teachers, staff = self._org_pool()
        for users, action in ((teachers, "outside_chair"), (staff, "outside_chair_staff")):
            found = _matches(users, token, fuzzy=False)
            if len(found) > 1:
                return None, "teacher_ambiguous"
            if len(found) == 1:
                if not self.allow_outside_chair:
                    return None, "teacher_outside_chair"
                self._outside.add((chair.pk, found[0].pk))
                return found[0], action
        return None, "teacher_not_found"

    # ── əsas ──────────────────────────────────────────────────────────────
    def run(self, parsed) -> None:
        self._load_rows()
        resolver = schedule_docx_match.Resolver(self.org, self.period)
        for entry in parsed.entries:
            cell = Cell(entry=entry)
            self.cells.append(cell)
            self._match(cell, resolver)
        creator = None
        if self.create_missing_rows:
            creator = MissingRowCreator(self, resolver)
            creator.prepare()
        self._apply(self._aggregate(), creator)
        for cell in self.cells:
            self.counters[f"cell_{cell.status}"] += 1

    def _match(self, cell: Cell, resolver) -> None:
        text = cell.entry.text
        if text.special:
            cell.status = f"special_{text.special}"
            return
        if not text.subject:
            cell.status = "subject_missing"
            return
        if not text.teacher:
            cell.status = "teacher_missing"
            return
        units = resolver.group_units(cell.entry.group)
        if not units:
            cell.status = "group_not_found"
            return
        candidates = list({row.pk: row for unit in units for row in self.rows_by_group.get(unit.pk, [])}.values())
        if not candidates:
            cell.status = "group_no_task_rows"
            return
        top, cell.score, reason = self._best_rows(candidates, text.subject)
        if reason:
            cell.status = reason
            return
        default = "lecture" if (text.hours or text.teacher_full) else ""  # magistratura: növ işarəsi yoxdur
        targets = [(row, *self._activity(row, text.kind, default)) for row in top]
        found = [(row, activity, note) for row, activity, note in targets if activity]
        if not found:
            cell.row, cell.status = top[0], targets[0][2]
            return
        if len(found) > 1:
            cell.status = "row_ambiguous"
            return
        cell.row, cell.activity, cell.detail = found[0]
        if any(teacher_id is not None for teacher_id in self.taken.get((cell.row.pk, cell.activity), ())):
            cell.status = ALREADY_ASSIGNED
            return
        cell.user, cell.teacher_action = self.resolve_teacher(cell.row.task.chair, text.teacher)
        cell.status = PLANNED if cell.user is not None else cell.teacher_action

    def _aggregate(self) -> dict:
        """→ {sətir_pk: {fəaliyyət: [(müəllim_id, saat, False), …]}}; problemli cütün hüceyrələri ``conflict``."""
        groups: dict = defaultdict(list)
        for cell in self.cells:
            if cell.row is not None and cell.activity and cell.status not in (ALREADY_ASSIGNED,):
                if cell.status == PLANNED or cell.status.startswith("teacher_"):
                    groups[(cell.row.pk, cell.activity)].append(cell)
        plan: dict = defaultdict(dict)
        self.rows = {}
        for (row_pk, activity), cells in groups.items():
            planned = [cell for cell in cells if cell.status == PLANNED]
            if not planned:
                continue
            row = planned[0].row
            desired, reason = self._desired(row, activity, cells)
            if reason:
                for cell in planned:
                    cell.status, cell.detail = CONFLICT, reason
                continue
            plan[row_pk][activity] = desired
            self.rows[row_pk] = row
        return plan

    @staticmethod
    def _desired(row, activity: str, cells) -> tuple[list, str]:
        if any(cell.status != PLANNED for cell in cells):
            return [], "unresolved_peer"
        total = int(getattr(row, ACTIVITY_TOTAL_FIELD[activity], 0) or 0)
        users = {cell.user.pk for cell in cells}
        if len(users) == 1:
            return [(users.pop(), total, False)], ""
        subs: dict = {}
        for cell in cells:
            if not cell.sub or subs.setdefault(cell.sub, cell.user.pk) != cell.user.pk:
                return [], "teachers_differ"
        if len(subs) != int(row.subgroup_count or 1) or total % len(subs):
            return [], "teachers_differ"
        share = Counter(subs.values())
        return [(user_id, total // len(subs) * count, False) for user_id, count in sorted(share.items(), key=str)], ""

    def _apply(self, plan: dict, creator=None) -> None:
        """Kafedra (= tapşırıq, ``uniq_teaching_task_year_chair``) üzrə BİR addım: yeni sətirlər + mövcud sətirlər."""
        units: dict = defaultdict(lambda: ([], []))
        for row_pk in plan:
            units[self.rows[row_pk].task.chair_id][0].append(self.rows[row_pk])
        for chair_pk, specs in (creator.by_chair if creator is not None else {}).items():
            units[chair_pk][1].extend(specs)
        for rows, specs in units.values():
            snapshot = self._snapshot()
            try:
                with transaction.atomic():
                    results = self._apply_unit(rows, specs, plan, creator)
            except WorkloadDenied as exc:
                self._restore(snapshot)
                code = getattr(exc, "code", "") or "workload_denied"
                results = {row.pk: f"task_blocked:{code}" for row in rows}
                if specs:
                    creator.fail_blocked(specs, code)
                    self.counters["chair_rolled_back"] += 1
                self.counters["task_blocked"] += 1
            for cell in self.cells:
                if cell.status in (PLANNED, ROW_CREATED) and cell.row is not None and cell.row.pk in results:
                    cell.assignment = results[cell.row.pk]

    def _apply_unit(self, rows, specs, plan: dict, creator) -> dict:
        task, rows_amended = (rows[0].task if rows else None), False
        if specs:
            task, new_rows, desired, rows_amended = creator.write_rows(specs)
            rows, plan = [*rows, *new_rows], {**plan, **desired}
        if not rows:
            return {}
        return self._apply_task(task, rows, plan, rows_amended=rows_amended)

    def _snapshot(self) -> tuple:
        """Savepoint geri qayıdanda saylar da qayıtsın (prod log-u yalnız saylardır) + idxalçının fənn indeksi."""
        importer = self.importer
        counters = list({id(c): c for c in (self.counters, self.applier.counters, importer.counters)}.values())
        state = (dict(importer.subject_index), list(importer.subject_names), importer.next_code)
        return [(c, Counter(c)) for c in counters], state, list(importer.created_subjects)

    def _restore(self, snapshot: tuple) -> None:
        counters, state, created = snapshot
        for counter, saved in counters:
            counter.clear()
            counter.update(saved)
        importer = self.importer
        importer.subject_index, importer.subject_names, importer.next_code = state
        importer.created_subjects[:] = created

    def _apply_task(self, task, rows, plan: dict, *, rows_amended: bool = False) -> dict:
        """``rows_amended`` — yeni sətir bölünmüş sənədə düzəliş axını ilə əlavə olunub (təsdiq onu bağlayır)."""
        task.refresh_from_db(fields=["status", "distributed_at"])  # sətrin ``task``-ı köhnəlmiş ola bilər
        loads_before = teacher_loads(task)
        if self.importer.apply and task.status == TaskStatus.DRAFT:
            self.importer._approve_official_workbook(task)
        opened_before = self.applier.counters["amendment_opened"]
        results, written = {}, 0
        for row in sorted(rows, key=lambda r: (r.order, str(r.pk))):
            desired = plan[row.pk]
            current = self.applier.current_plan(row)
            if any(teacher_id for activity in desired for teacher_id, _, _ in current.get(activity, [])):
                results[row.pk] = ALREADY_ASSIGNED  # paralel dəyişiklik — real müəllimə toxunulmur
                continue
            self._join_outside(task, desired)
            # Yalnız boş/«Vakant» fəaliyyətlər ``desired``-dədir: mövcud bölgülü sətirdə də (vakant yerinə)
            # yazı ``reassign`` yolu ilə gedir — real müəllimli fəaliyyət yuxarıda kənarlaşdırılıb.
            self.applier.reassign = bool(current)
            action, detail = self.applier.apply_plan(row, desired)
            written += action in (ASSIGNED, REASSIGNED)
            results[row.pk] = f"{action}:{detail}" if detail else action
        self.applier.reassign = False
        if self.importer.apply:
            task.refresh_from_db(fields=["status"])
            opened = self.applier.counters["amendment_opened"] > opened_before or rows_amended
            amended = task.status == TaskStatus.AMENDED and opened
            if (written and task.status in (TaskStatus.APPROVED, TaskStatus.DISTRIBUTING)) or amended:
                # Əvvəl bölünmüş sənəd (düzəliş) — kafedranın bütün müəllimlərinə təkrar bildiriş yox, yalnız
                # bu işdə bölgüsü yeni/dəyişən müəllimə (sahib 2026-10-17); ilk təsdiq hamıya bildirir.
                self.importer._confirm_and_enroll(task, loads_before=loads_before)
                self.counters["task_confirmed"] += 1
        return results

    def _join_outside(self, task, desired: dict) -> None:
        if not self.importer.apply:
            return
        for entries in desired.values():
            for teacher_id, _, _ in entries:
                if (task.chair_id, teacher_id) not in self._outside:
                    continue
                user = next((u for users in self._org_pool() for u in users if u.pk == teacher_id), None)
                user = user or get_user_model().objects.get(pk=teacher_id)  # açıq xəritə ilə gələn hesab
                if join_chair_as_teacher(
                    organization=self.org,
                    user=user,
                    chair=task.chair,
                    actor_user=self.importer.actor_user,
                    reason=_JOIN_REASON,
                ):
                    self.counters["chair_membership_added"] += 1
                self._outside.discard((task.chair_id, teacher_id))

    def all_counters(self) -> Counter:
        counters = Counter(self.counters) + self.applier.counters + self.importer.counters
        for cell in self.cells:
            if cell.status in (PLANNED, ROW_CREATED, ROW_PLANNED) and cell.assignment:
                counters[f"result_{cell.assignment.split(':', 1)[0]}"] += 1
        return +counters


__all__ = ["REPORT_HEADER", "Cell", "TimetableTaskAssigner", "period_season"]
