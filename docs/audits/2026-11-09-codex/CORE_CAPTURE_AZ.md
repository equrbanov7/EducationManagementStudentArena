# Bounded «core» capture — 2026-11-09

Tam 78 cədvəllik `reaudit` snapshot-u iki dəfə `snapshot_total_byte_budget_exceeded`
(512 MiB) ilə dayandı. 3 noyabr prod kopyasında ölçmə həddi dolduranları göstərdi:
`registrar.LessonMark` (4,4 mln sətir, bütün dövrlər), `legacy_import.LegacyEntityMap`
(778 min; lesson/enrollment/mark hədəfli xəritələr), `registrar.LegacyGradeFact` (171 min ×
38 sahə) və `audit.AuditLog`. Cells/sillabus planlaşdırıcıları bunların yalnız kiçik,
cari-dövr hissəsini oxuyur.

## Nə dəyişdi

- `apps/legacy_import/services/reaudit_snapshot/schemas_core.json` — 25 cədvəllik açıq alt
  müqavilə: identity (`auth.User`, `accounts.UserProfile`), struktur (`AcademicPeriod`,
  `OrgUnit`, `Subject`, `CourseOffering`), xanalar (`Enrollment` — yalnız cari dövr,
  `Lesson`, `LessonMark`, `AssessmentComponent`), düzəlişlər (`JournalCorrection`,
  `LessonCorrection`, `CorrectionReversal`), yük (`workload.*`), sillabus başlıqları
  (`Syllabus`, `SyllabusVersion`, `SyllabusShare`, `LanguageLevelCohort`), xəritə
  (`LegacyEntityMap[Version]` — yalnız identity/offering yolları, `LegacyMigrationRun`) və
  `audit.AuditLog` — yalnız native copy/fill receipt növləri (`legacy_cells_fill`,
  `subgroup_journal_merge`, `subgroup_parent_retire`). Sahə siyahıları tam müqavilə ilə
  eynidir; yalnız `Enrollment.period_path`, AuditLog `resource_type__in` filtri və xəritə
  `route_scope` fərqlənir (`test_reaudit_snapshot_core_scope.py` bunu bərkidir).
- `export_reaudit_state_20261109 --scope {full,core}`; manifest `scope`, scope-un öz
  `schema_sha256`-ı, hər cədvəl üçün `bytes` və `total_bytes`. Budcə (512 MiB), RLS, actor,
  READ ONLY tranzaksiya və şifrələmə dəyişməyib.
- `prod-audit.yml` → `capture_scope` inputu; `scripts/ops/reaudit_snapshot.py` scope-u native
  komandaya ötürür, `transport.json`-a yazır və manifest scope-unu yoxlayır.
- `scripts/ops/decode_reaudit_snapshot.py` core manifestdə core sxem digest-ini və tam cədvəl
  dəstini tələb edir (`core_schema_changed` / `core_table_set_changed`); buraxılmış cədvəl
  boş sayılmır — planlaşdırıcı `full_capture_table_missing` ilə dayanır.
- `build_audit_cells_plan_20261109 --owner-present-policy {applicable_blank_without_grade_hold,disabled}`:
  mənbə balları/təsdiqli iştirak əvvəl (`disabled`), owner-present boş xanalar ayrıca plan və
  receipt ilə ikinci keçid.

## İcra qaydası

Core capture → lokal decode → `build_audit_cells_plan_20261109` → şifrəli bundle/release →
`reaudit-remediation.yml operation=cells` dry → backup+apply → receipt → təkrar dry.
Tam 78 cədvəllik capture tarixi final/duplicate audit üçün ayrıca qalır; onun büdcə payını
indi manifestdəki `bytes` sahəsi göstərir.
