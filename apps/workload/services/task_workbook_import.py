"""TAPŞIRIQ kitabçası → kataloq tutuşdurma + yazı (`import_teaching_task_workbook`).

Sahibin qərarı 2026-09-19: fənn/qrup/ixtisas yoxdursa yaradılır; müəllim tapılmırsa
yarım məlumatla yaradılır, qeyri-müəyyəndirsə vakant qalır; bölgü təsdiqi →
``CourseOffering`` + tələbə qeydiyyatı. Oxunma qaydaları `task_workbook_parsing`-dədir.

2026-10-12: seçmə blokunda seçim QALIN şriftlə (`task_workbook_choice`); işarəsiz blok
sətri yaradılmır; mövcud sətirlər mətn dəyişsə də tapılır (`task_row_matching`); müəllim
dəyişikliyi ``--reassign`` ilə düzəliş axınından (`task_load_reassign`); ``--no-create-teachers``
ilə heç bir hesab yaradılmır (`task_workbook_teachers`).
"""

from __future__ import annotations

import difflib
import re
import secrets
from collections import Counter

from django.db import IntegrityError, transaction

from apps.organizations.models import AcademicPeriod, OrgUnit
from apps.registrar.models import CourseOffering, StudentAcademicRecord, Subject
from apps.registrar.public import enroll_student_in_subject
from apps.workload.constants import ACTIVITY_TOTAL_FIELD, TEACHING_ACTIVITIES, RowKind, TaskStatus
from apps.workload.models import TeacherAssignment, TeachingTask, TeachingTaskRow
from apps.workload.services.assignments import assign_teacher, remaining_hours
from apps.workload.services.distribution import confirm_distribution
from apps.workload.services.imports import normalize
from apps.workload.services.scoping import resolve_actor
from apps.workload.services.task_load_reassign import (
    ASSIGNED,
    REASSIGNED,
    UNCHANGED,
    WOULD_ASSIGN,
    RowPlanApplier,
)
from apps.workload.services.task_row_matching import GROUPS_CHANGED, SUBJECT_CHANGED, RowMatcher
from apps.workload.services.task_workbook_choice import CHOSEN_NONE
from apps.workload.services.task_workbook_parsing import (
    _ITEM_RE,
    _QKU_CODE_RE,
    _SPLIT_RE,
    GROUP_CODE_SPECIALTY,
    PERIODS,
    SHEET_TO_CHAIR,
    SPECIALTY_ALIASES,
    _int,
    _key,
    _special_row_kind,
    block_chosen_subject,
    clean_subject_name,
    group_year_from_name,
    is_block,
    slug_name,
    split_tokens,
    with_choice,
)
from apps.workload.services.task_workbook_teachers import TeacherResolverMixin
from apps.workload.services.tasks import resolve_specialty_and_faculty
from core.constants import OrgUnitType


class Importer(TeacherResolverMixin):
    def __init__(
        self,
        *,
        organization,
        year: str,
        actor_user,
        apply: bool,
        stdout,
        create_teachers: bool = True,
        reassign: bool = False,
    ):
        self.org = organization
        self.year = year
        self.actor_user = actor_user
        self.actor = resolve_actor(actor_user, organization)
        self.apply = apply
        self.stdout = stdout
        self.create_teachers = create_teachers
        self.applier = RowPlanApplier(
            organization=organization,
            actor=self.actor,
            apply=apply,
            reassign=reassign,
            note=f"Rəsmi TAPŞIRIQ kitabçası {year} — müəllim bölgüsü sənədə uyğunlaşdırıldı",
        )
        self.report_rows: list[dict] = []
        self.counters: Counter = Counter()
        self.subject_index = {normalize(s.name): s for s in Subject.objects.filter(organization=organization)}
        self.subject_names = list(self.subject_index.keys())
        self.group_index: dict[str, OrgUnit] = {}
        for unit in OrgUnit.objects.filter(organization=organization, unit_type=OrgUnitType.GROUP, is_active=True):
            self.group_index.setdefault(_key(unit.name), unit)
        self.specialty_index = {
            normalize(u.name): u
            for u in OrgUnit.objects.filter(organization=organization, unit_type=OrgUnitType.SPECIALTY, is_active=True)
        }
        self.chairs = {
            normalize(u.name): u
            for u in OrgUnit.objects.filter(organization=organization, unit_type=OrgUnitType.CHAIR, is_active=True)
        }
        codes = [
            int(m.group(1))
            for c in Subject.objects.filter(organization=organization).values_list("code", flat=True)
            for m in [_QKU_CODE_RE.match(c or "")]
            if m
        ]
        self.next_code = (max(codes) if codes else 0) + 1
        self.periods: dict[str, AcademicPeriod] = {}
        self.teacher_cache: dict[tuple, tuple] = {}
        self.created_specialties: list[str] = []
        self.created_groups: list[str] = []
        self.created_subjects: list[str] = []
        self.created_teachers: list[str] = []
        self.ambiguous_teachers: list[str] = []

    # ── köməkçilər ────────────────────────────────────────────────────────
    def note(self, **fields) -> dict:
        self.report_rows.append(fields)
        return fields

    def ensure_periods(self):
        for season, (name, start, end) in PERIODS.items():
            period = AcademicPeriod.objects.filter(organization=self.org, name=name, academic_year=self.year).first()
            if period is None:
                self.counters["period_created"] += 1
                if self.apply:
                    period = AcademicPeriod.objects.create(
                        organization=self.org,
                        name=name,
                        period_type="semester",
                        academic_year=self.year,
                        start_date=start,
                        end_date=end,
                        is_current=(season == "fall"),
                        is_active=True,
                    )
            elif season == "fall" and not period.is_current and self.apply:
                period.is_current = True
                period.save(update_fields=["is_current", "updated_at"])
            self.periods[season] = period

    def chair_for_sheet(self, title: str):
        slug = slug_name(title)
        for prefix, chair_name in SHEET_TO_CHAIR.items():
            if slug.startswith(slug_name(prefix)):
                return self.chairs.get(normalize(chair_name))
        return None

    def resolve_specialty(self, text: str, group_token: str, chair=None):
        text_norm = normalize(text)
        if text_norm:
            if text_norm in self.specialty_index:
                return self.specialty_index[text_norm]
            for alias, name in SPECIALTY_ALIASES.items():
                if text_norm.startswith(normalize(alias)) or normalize(alias) in text_norm:
                    unit = self.specialty_index.get(normalize(name))
                    if unit is not None:
                        return unit
            close = difflib.get_close_matches(text_norm, list(self.specialty_index), n=1, cutoff=0.85)
            if close:
                return self.specialty_index[close[0]]
        code = re.sub(r"^[\d/]+\s*", "", group_token)
        code = re.sub(r"\s*(az|ing|rus|AZ|ING|RUS|İNG|-?\d)$", "", code).strip()
        name = GROUP_CODE_SPECIALTY.get(code)
        unit = self.specialty_index.get(normalize(name)) if name else None
        if unit is not None or chair is None:
            return unit
        # Kataloqda olmayan ixtisas (məs. «Biotexnologiya», «Yer quruluşu və kadastr») —
        # sahibin qərarı: yaradılır (kafedranın fakültəsi altında), hesabatda görünür.
        full_name = ""
        for alias, alias_name in SPECIALTY_ALIASES.items():
            if text_norm and (text_norm.startswith(normalize(alias)) or normalize(alias) in text_norm):
                full_name = alias_name
                break
        if not full_name:
            return None
        faculty = chair.parent if chair.parent is not None and chair.parent.unit_type == OrgUnitType.FACULTY else None
        if faculty is None:
            return None
        unit = OrgUnit(organization=self.org, parent=faculty, unit_type=OrgUnitType.SPECIALTY, name=full_name)
        if self.apply:
            unit.save()
        self.specialty_index[normalize(full_name)] = unit
        self.counters["specialty_created"] += 1
        self.created_specialties.append(full_name)
        return unit

    def resolve_subject(self, raw: str, chair, credits: str, special_kind: str = "", chosen=None) -> tuple:
        """→ (Subject|None, action, resolved_name). Xüsusi sətir (təcrübə/buraxılış) fənn YARATMIR.

        ``chosen`` — zəngin mətndən (qalın/«+»/override) əvvəlcədən seçilmiş bənd."""
        candidates = [raw]
        block = is_block(raw)
        if chosen is None:
            chosen = block_chosen_subject(raw) if block else ""
        if chosen:
            candidates.insert(0, chosen)
        single = clean_subject_name(raw)
        candidates += [single, re.sub(r"\s*\(.*?\)\s*", " ", single).strip(), _ITEM_RE.sub("", single)]
        for candidate in candidates:
            key = normalize(candidate)
            if key and key in self.subject_index:
                return self.subject_index[key], "matched", self.subject_index[key].name
        for candidate in candidates[:2]:
            key = normalize(candidate)
            close = difflib.get_close_matches(key, self.subject_names, n=1, cutoff=0.9)
            if (
                close
                and close[0][:5] == key[:5]
                and (key[-1:].isdigit() == close[0][-1:].isdigit())
                and (not key[-1:].isdigit() or key[-1:] == close[0][-1:])
            ):
                return self.subject_index[close[0]], "fuzzy", self.subject_index[close[0]].name
        if block and not chosen:
            return None, "block_unresolved", ""
        if special_kind:
            return None, "special_row", ""
        name = chosen or single
        ects = _int(credits) or 5
        subject = Subject(
            organization=self.org, code=f"QKU-{self.next_code}", name=name, ects=min(max(ects, 1), 30), chair_unit=chair
        )
        self.next_code += 1
        if self.apply:
            subject.save()
        self.subject_index[normalize(name)] = subject
        self.subject_names.append(normalize(name))
        self.counters["subject_created"] += 1
        self.created_subjects.append(name)
        return subject, "created", name

    def resolve_group(self, token: str, specialty) -> list[tuple]:
        """→ [(OrgUnit, action), ...] — «533 T» kimi ad alt-qruplara («533T1», «533T2») açıla bilər."""
        bare = re.sub(r"\s+(az|AZ|Az)$", "", token)
        sector_only = re.sub(r"^(\S+)\s+\S+\s+(ing|rus|ING|RUS|İNG)$", r"\1 \2", token)  # «435 R ing» → «435 ing»
        for variant in (token, f"{token} az", bare, token.replace(" ", ""), f"{bare}-1", sector_only, f"3/{token}"):
            unit = self.group_index.get(_key(variant))
            if unit is not None:
                return [(unit, "matched")]
        base_key = _key(bare)
        subgroups = [
            unit
            for key, unit in self.group_index.items()
            if key.startswith(base_key) and re.fullmatch(r"\d(az)?", key[len(base_key) :])
        ]
        if subgroups:
            return [(unit, "matched_subgroup") for unit in sorted(subgroups, key=lambda u: u.name)]
        if specialty is None:
            return [(None, "no_specialty")]
        if not specialty.pk:  # dry-run-da yaradılmış ixtisas — qrup da yalnız planlanır
            self.counters["group_created"] += 1
            self.created_groups.append(token)
            return [(None, "created")]
        # Tələbə idxalı (ATİS) qrupu qəbul ili + dil bölməsi ilə seçir — ayarlar buradan.
        sector = (
            "en" if re.search(r"\b(ing|ING|İNG)\b", token) else "ru" if re.search(r"\b(rus|RUS)\b", token) else "az"
        )
        if sector == "az" and "ingilis" in slug_name(getattr(self, "_current_spec_text", "")):
            sector = "en"
        unit = OrgUnit(
            organization=self.org,
            parent=specialty,
            unit_type=OrgUnitType.GROUP,
            name=token,
            settings={"language_sector": sector, "admission_year": group_year_from_name(token, int(self.year[:4]))},
        )
        if self.apply:
            try:
                with transaction.atomic():
                    unit.save()
            except IntegrityError:
                unit.slug = f"{slug_name(token)}-{secrets.token_hex(2)}"
                unit.save()
        self.group_index[_key(token)] = unit
        self.counters["group_created"] += 1
        self.created_groups.append(token)
        return [(unit, "created")]

    # ── əsas axın ─────────────────────────────────────────────────────────
    def _task_for(self, chair):
        task = TeachingTask.objects.filter(organization=self.org, chair=chair, academic_year=self.year).first()
        if task is None:
            self.counters["task_created"] += 1
            if self.apply:
                task = TeachingTask.objects.create(
                    organization=self.org,
                    chair=chair,
                    academic_year=self.year,
                    created_by=self.actor_user,
                    status=TaskStatus.DRAFT,
                )
        return task

    def _resolve_groups(self, record, chair) -> tuple[list, list]:
        tokens = split_tokens(record["groups_text"])
        spec_tokens = [t for t in _SPLIT_RE.split(record["specialty_text"]) if t.strip()]
        groups, group_actions = [], []
        for position, token in enumerate(tokens):
            # İxtisas sütunu qrup sayından azdırsa artıq qruplar üçün ƏVVƏLCƏ qrup
            # kodunun hərfləri («236 M» → Meşəçilik), sonra ilk ixtisas mətni.
            if position < len(spec_tokens):
                spec_text = spec_tokens[position]
            elif self.resolve_specialty("", token, None) is not None:
                spec_text = ""
            else:
                spec_text = spec_tokens[0] if spec_tokens else ""
            specialty = self.resolve_specialty(spec_text, token, chair)
            self._current_spec_text = spec_text
            for unit, action in self.resolve_group(token, specialty):
                group_actions.append(f"{unit.name if unit is not None else token}:{action}")
                if unit is not None and unit.pk:
                    groups.append(unit)
        return groups, group_actions

    def import_sheet(self, title: str, records: list[dict]):
        chair = self.chair_for_sheet(title)
        if chair is None:
            self.stdout.write(f"  ! «{title}» vərəqi üçün kafedra tapılmadı — ötürüldü")
            self.counters["sheet_skipped"] += 1
            return
        if not records:
            self.stdout.write(f"  · «{title}» ({chair.name}): sətir yoxdur — ötürüldü")
            return
        task = self._task_for(chair)
        existing_rows = task.rows.prefetch_related("groups") if task is not None and task.pk else []
        matcher = RowMatcher(existing_rows)
        rows_to_plan: list[tuple] = []
        for record in records:
            record = with_choice(record)
            entry = self.note(
                sheet=title,
                line=record["line"],
                season=record["season"],
                groups_raw=record["groups_text"].replace("\n", " | "),
                subject_raw=clean_subject_name(record["subject_text"]),
                chosen_subject=record["chosen_subject"],
                chosen_by=record["chosen_by"],
                teacher_raw=record["teacher_text"],
            )
            if record["chosen_by"] == CHOSEN_NONE:
                # Seçim işarəsi yoxdur: sətir yaradılmır/təyin olunmur (mövcud sətir toxunulmaz qalır).
                row, how = matcher.match(
                    season=record["season"], subject_text=record["subject_text"], groups_text=record["groups_text"]
                )
                entry.update(row=f"no_choice_marker:{how}", assignment="skipped")
                self.counters["row_no_choice_marker"] += 1
                continue
            self._import_record(record, entry, chair, task, matcher, rows_to_plan)
        planned = self._plan_rows(task, rows_to_plan)
        for row in matcher.unmatched():
            self.counters["row_not_in_file"] += 1
            self.note(
                sheet=title, season=row.season, groups_raw=row.groups_text, subject_raw=row.subject_label,
                row="not_in_file", assignment="untouched",
            )  # fmt: skip
        if self.apply and task is not None:
            task.refresh_from_db(fields=["status"])
            amended = task.status == TaskStatus.AMENDED and self.applier.counters["amendment_opened"]
            if (planned and task.status in (TaskStatus.APPROVED, TaskStatus.DISTRIBUTING)) or amended:
                self._confirm_and_enroll(task)
        self.stdout.write(f"  · vərəq → kafedra: {len(records)} sətir, bölgü planı {len(rows_to_plan)} sətirdə")

    def _import_record(self, record, entry, chair, task, matcher, rows_to_plan) -> None:
        special_kind = _special_row_kind(record)
        subject, subject_action, subject_name = self.resolve_subject(
            record["subject_text"], chair, record["credits"], special_kind, chosen=record["chosen_subject"]
        )
        groups, group_actions = self._resolve_groups(record, chair)
        teacher_tokens = [t for t in re.split(r"\s*[-–]\s*", record["teacher_text"]) if t.strip()]
        teachers = [(token, *self.resolve_teacher(token, chair)) for token in teacher_tokens]
        entry.update(
            subject_action=subject_action,
            subject_resolved=subject_name,
            groups=" ; ".join(group_actions),
            teachers=" ; ".join(f"{t}:{a}:{u.username if u is not None else ''}" for t, u, a in teachers),
        )
        row, how = matcher.match(
            season=record["season"],
            subject_text=record["subject_text"],
            groups_text=record["groups_text"],
            subject=subject,
            group_ids=[g.pk for g in groups],
        )
        if how in (SUBJECT_CHANGED, GROUPS_CHANGED):
            # Bənd seçimi / qrup tərkibi dəyişib — dublikat yaratmırıq, mövcud sətrə toxunmuruq;
            # hesabatda əl ilə düzəliş (amendment) üçün.
            self.counters[f"row_{how}"] += 1
            entry.update(row=how, assignment="skipped")
            return
        if row is None:
            self.counters["row_created"] += 1
            row = self._create_row(record, task, special_kind, subject, groups) if self.apply else None
            entry["row"] = "new"
        else:
            self.counters[f"row_matched_{how}"] += 1
            entry["row"] = f"matched:{how}"
            if row.subject_id is None and subject is not None:
                # Sentyabrda seçimi bilinməyən blok sətri — fənn indi məlumdur (boş sahə doldurulur).
                entry["row"] += ":" + self.applier.fill_subject(row, subject)
        if teachers:
            rows_to_plan.append((row, teachers, entry))

    def _create_row(self, record, task, special_kind, subject, groups):
        specialty_unit, faculty = (groups[0].parent, None) if groups else (None, None)
        if specialty_unit is not None:
            specialty_unit, faculty = resolve_specialty_and_faculty(self.org, specialty_unit.pk)
        row = TeachingTaskRow(
            organization=self.org,
            task=task,
            season=record["season"],
            row_kind=special_kind or RowKind.TEACHING,
            period=self.periods[record["season"]],
            subject=subject if subject is not None and subject.pk else None,
            subject_text=record["subject_text"][:255],
            specialty=specialty_unit,
            specialty_text=record["specialty_text"][:255],
            faculty=faculty,
            groups_text=record["groups_text"][:255],
            student_count=record["student_count"],
            student_count_text=record["student_count_text"][:100],
            union_count=record["union_count"],
            subgroup_count=record["subgroup_count"],
            lecture_plan=record.get("lecture_plan", 0),
            lecture_total=record["lecture_total"],
            seminar_plan=record.get("seminar_plan", 0),
            seminar_total=record["seminar_total"],
            lab_plan=record.get("lab_plan", 0),
            lab_total=record["lab_total"],
            consult_hours=record.get("consult_hours", 0),
            exam_hours=record.get("exam_hours", 0),
            thesis_hours=record.get("thesis_hours", 0),
            postgrad_hours=record.get("postgrad_hours", 0),
            practice_research_hours=record.get("practice_research_hours", 0),
            practice_production_hours=record.get("practice_production_hours", 0),
            credits=record["credits"][:20],
            credits_value=_int(record["credits"]),
        )
        row.total_hours = record["total_hours"] or row.computed_total_hours
        row.save()
        if groups:
            row.groups.set(groups)
        return row

    def _approve_official_workbook(self, task):
        """Audit 2026-09-28 W1: göndərilməmiş qaralama artıq bölünmür.

        TAPŞIRIQ kitabçası universitetin TƏSDİQLƏNMİŞ rəsmi sənədidir (sahib
        2026-09-19) — operator əmri onu AÇIQ şəkildə, audit izi ilə «təsdiqlənmiş»
        kimi qeyd edir; bölgü yalnız bundan sonra açılır.
        """
        from core.audit import log_action
        from core.constants import AuditAction

        old_status = task.status
        task.status = TaskStatus.APPROVED
        task.save(update_fields=["status", "updated_at"])
        log_action(
            AuditAction.UPDATE,
            user=self.actor_user,
            organization=self.org,
            obj=task,
            old_values={"status": old_status},
            new_values={"status": task.status},
            reason="workload.task_approved_by_official_workbook_import",
            resource_type="workload.TeachingTask",
            resource_id=str(task.pk),
            resource_repr=f"{task.chair_id} · {task.academic_year}",
        )

    def _plan_rows(self, task, rows_to_plan) -> int:
        """Sətirlərin müəllim bölgüsü :class:`~.task_load_reassign.RowPlanApplier` ilə.

        Bölgüsüz sətir — ilk təyinat (köhnə davranış); bölgülü sətir — fayldakı müəllim
        fərqlidirsə yalnız ``--reassign`` ilə dəyişir (əks halda ``teacher_differs``).
        Həll olunmamış ad işarəsi mövcud bölgünü DƏYİŞMİR.
        """
        if self.apply and rows_to_plan and task is not None and task.status == TaskStatus.DRAFT:
            self._approve_official_workbook(task)
        written = 0
        for row, teachers, entry in rows_to_plan:
            if row is None:  # dry-run-da yeni sətir
                self.counters["assignment_planned"] += 1
                entry["assignment"] = WOULD_ASSIGN
                continue
            users = self._with_current_teachers(row, teachers)
            unresolved = None in users
            fresh = not TeacherAssignment.objects.filter(row=row).exists()
            desired = {}
            for index, activity in enumerate(TEACHING_ACTIVITIES):
                hours = int(getattr(row, ACTIVITY_TOTAL_FIELD[activity], 0) or 0)
                if not hours:
                    continue
                # «A-B» cütü: mühazirə birinciyə, seminar/lab ikinciyə; tək müəllim hamısını alır.
                user = users[0] if index == 0 else users[-1]
                if user is None:
                    if fresh:
                        desired[str(activity)] = [(None, hours, False)]
                    continue
                desired[str(activity)] = [(user.pk, hours, False)]
            action, detail = self.applier.apply_plan(row, desired)
            if unresolved and action == UNCHANGED:
                action = "teacher_unresolved"
            entry["assignment"] = f"{action}:{detail}" if detail else action
            written += action in (ASSIGNED, REASSIGNED)
        return written

    @staticmethod
    def _with_current_teachers(row, teachers) -> list:
        """Həll olunmamış ad işarəsi (eyni adlı iki müəllim / başqa kafedrada) sətrin CARİ
        müəllimi ilə eyni addırsa — cari müəllim saxlanılır (dəyişiklik yoxdur)."""
        users = [u if u is not None and u.pk else None for _, u, _ in teachers]
        if None not in users:
            return users
        current = [a.teacher for a in TeacherAssignment.objects.filter(row=row).select_related("teacher")]
        current.sort(key=lambda teacher: teacher is None)
        for position, (token, _, _) in enumerate(teachers):
            if users[position] is not None:
                continue
            first = slug_name(token.replace("I", "İ").split()[0]) if token.split() else ""
            same = {t.pk: t for t in current if t is not None and slug_name(t.first_name) == first}
            if len(same) == 1:
                users[position] = next(iter(same.values()))
        return users

    def _confirm_and_enroll(self, task):
        # Bölgüsüz qalan dərs sətirləri «Vakant» ilə doldurulur ki, təsdiq keçsin
        # (jurnal sahibi sonra «Fənn təhvili»/düzəlişlə təyin olunur).
        for row in task.rows.all():
            for activity in TEACHING_ACTIVITIES:
                left = remaining_hours(row, str(activity))
                if left > 0:
                    assign_teacher(
                        row=row, actor=self.actor, activity=str(activity), teacher_id=None, hours=left, note="Vakant"
                    )
                    self.counters["assignment_vacant"] += 1
        result = confirm_distribution(task=task, actor=self.actor, allow_vacant=True)
        self.counters["offering_created"] += result["sync"]["created"]
        self.counters["offering_updated"] += result["sync"]["updated"]
        self.counters["offering_instructor_blocked"] += result["sync"]["instructor_blocked"]
        for offering in CourseOffering.objects.filter(pk__in=result["sync"]["offering_ids"]).select_related("group"):
            records = StudentAcademicRecord.objects.filter(
                organization=self.org, group=offering.group, is_active=True, status="enrolled"
            ).select_related("student")
            for record in records:
                _, created = enroll_student_in_subject(
                    record=record, subject=offering.subject, period=offering.period, kind="mandatory"
                )
                self.counters["enrollment_created" if created else "enrollment_exists"] += 1
