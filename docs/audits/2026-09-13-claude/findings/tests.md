# AUDIT — Avtomatik testlər · coverage · akademik E2E axınlar (slug `tests`)

Tarix: 2026-09-13 · HEAD: 7c5dc612 (Develop) · Auditor: read-only · Sandbox DB: `ems_audit_tests` (:55432) · Klon: :55433 (SELECT-only) · Dev-clone server :8011

Status legendası: PASS / FAIL / PARTIAL / NOT TESTED / NOT APPLICABLE

## 0. Xülasə
1. Tam PostgreSQL dəsti (sandbox, `-n 6`, coverage ilə): **8 618 passed · 15 skipped · 1 failed (mühit: paralel agentin migrasiya faylı) · 15 dəq 31 san**; apps+core statement **78.76 %** / branch **66.54 %**; kritik dəst (28 405 stmt) **85.88 % / 72.69 %**.
2. Skip inventarı: 16 skip, hamısı mühit/dizayn; **xətanı gizlədən skip yoxdur**; 4 test heç bir mühitdə işləmir (tesseract, rehearsal markeri).
3. 12 HTTP E2E probe (6 axın, istehsal rol kataloqu, real trigger-lər): **12/12 PASS** — 2-si tapıntını sənədləşdirir.
4. **P1 F-T1:** kafedra müdiri göndərilməmiş TŞ qaralamasını dekan təsdiqi olmadan bölüb açılış yaradır (`workflow.py:72-90`).
5. **P2 F-T2:** xaric edilmiş tələbə cari/köhnə qrupa bərpa oluna bilmir (`movements.py:293` `same_group` növ istisnasız).
6. Dev-clone: 11 rol × 1 059 sorğu — 500 yalnız klon sxem sürüşməsindən (`registrar 0070` vs kod `0073+`), konsol/CSP xətası 0.
7. Coverage boşluqları: imtahan kopyalama 0 %, qiymətləndirmə mixin 22 %, `journal_sync` 34 %, media siyasətlərinin 8 yoxlayıcısı 0 %, final mərkəzi 3 icazə qapısı 0 %.
8. Gigiyena: venv-də `pytest-cov`/`pytest-timeout` yoxdur; 4 migrasiya test faylı ≈ 25 CPU-dəq; fixture dublikasiyası (280 fayl öz org-unu qurur); `freezegun` yoxdur.
9. Proses: paralel agentlər eyni nömrəli migrasiya yaratdı → 20 dəq `Conflicting migrations` bloku.
10. Ballar: Tests 74 · Workload 68 · Schedule 80 · Syllabus 91 · Journal 84 · Student Mgmt 73. Say: **P0 0 · P1 1 · P2 6 · P3 7**.

Artefaktlar: `full_run.log`, `coverage.json`, `coverage_table.md`, `skip_sites.txt`, `flaky_sleep.txt`, `clone_crawl.txt`, `url_map.txt`, `probes/test_e2e_flows.py` (+ `probes/e2e_results.txt`).
Probe çalışdırma: `DATABASE_URL="postgres://emsarena_agent:emsarena_agent_password@127.0.0.1:55432/ems_audit_tests" USE_REDIS=False venv/bin/python -m pytest <bu qovluq>/probes/test_e2e_flows.py --ds=config.settings.test --rootdir=/Users/elvin/Developer/EMSArena -q --reuse-db -p no:cacheprovider -o addopts=""`

## 1. Coverage by criticality (PostgreSQL sandbox `ems_audit_tests`)

**Necə ölçüldü.** Tam dəst `apps core tests --ignore=tests/e2e`, `-n 6 --dist loadfile --create-db`, `--cov=apps --cov=core --cov-branch` (venv-də `pytest-cov`/`coverage` **yox idi** — `requirements/test.txt`-də pinlənsə də quraşdırılmayıb; izolyasiya olunmuş `--target` ilə yükləndi, venv-ə toxunulmadı). Log: `full_run.log`, JSON: `coverage.json`, cədvəl skripti: bu bölmə.

**Nəticə (2026-09-13, HEAD 7c5dc612 + işçi ağac):** `8618 passed · 15 skipped · 1 failed · 1382 subtests passed · 15 dəq 31 san`. Tək uğursuzluq `test_rubric_component_migration::test_reverse_stops_for_duplicate_cross_component_evidence` — teardown-da `NodeNotFoundError('registrar','0074_finalgrade_exam_score_range')`: **paralel işləyən düzəliş agenti dəstin ortasında migrasiya faylı əlavə etdi** (ətraf mühit, kod xətası deyil; bax §6 F-T5). Codex-in 224/219 «skipped» rəqəmi ilə fərq: pytest 9.1 alt-testləri (`subTest`) ayrıca sayır; `-rs` ilə real skip yerləri 15-dir (§2).

**Ümumi (apps+core, PostgreSQL, migrasiyalı):** statement **78.76 %**, branch **66.54 %** (96 102 stmt / 28 350 branch). Codex-in SQLite ölçüsü (82.99 / 67.83) ilə müqayisədə statement daha aşağıdır, çünki PostgreSQL-only kod yolları (RLS, trigger körpüləri, `legacy_import` MariaDB) ölçüyə daxildir və MariaDB inteqrasiya testləri skip olur.

**Kritik dəst (28 405 stmt): statement 85.88 % · branch 72.69 %.** Aşağıdakı cədvəldə qalın rəqəm < 80 %.

| Modul | Stmt % | Branch % | Stmts | Missing | Örtülməmiş funksiyalar (kritik) |
|---|---|---|---|---|---|
| `apps/accounts/services/view_as.py` | 81.9 | 73.0 | 208 | 31 | actor_can_use_view_as |
| `apps/appeals/services/creation.py` | 92.1 | 95.0 | 69 | 6 |  |
| `apps/appeals/services/decisions.py` | 87.3 | 77.8 | 184 | 20 |  |
| `apps/appeals/services/permissions.py` | 85.0 | 75.0 | 28 | 3 |  |
| `apps/appeals/services/scoring.py` | **79.0** | 67.9 | 149 | 25 | appeal_result_hidden_from_student |
| `apps/appeals/services/state_machine.py` | **43.8** | 0.0 | 12 | 5 | can_transition |
| `apps/appeals/services/window.py` | 100.0 | 100.0 | 28 | 0 |  |
| `apps/exams/domain/access_policy.py` | 86.0 | 83.3 | 169 | 21 | _user_can_manage_groups, ExamAccessPolicyMixin.requires_code_for |
| `apps/exams/domain/ai_config.py` | 91.7 | 50.0 | 34 | 2 |  |
| `apps/exams/domain/attempts.py` | 89.6 | 77.5 | 209 | 17 | ExamAttempt.is_resume_window_expired |
| `apps/exams/domain/coding.py` | 95.5 | 100.0 | 110 | 5 |  |
| `apps/exams/domain/exam_definition.py` | 98.4 | 94.4 | 107 | 1 |  |
| `apps/exams/domain/fields.py` | **76.5** | 50.0 | 13 | 2 |  |
| `apps/exams/domain/final_center.py` | 97.6 | 100.0 | 160 | 4 |  |
| `apps/exams/domain/grade_events.py` | 100.0 | 100.0 | 13 | 0 |  |
| `apps/exams/domain/grading.py` | **22.2** | 0.0 | 21 | 15 | AttemptGradingMixin.mark_checked, AnswerGradingMixin.auto_evaluate |
| `apps/exams/domain/import_jobs.py` | 97.1 | 100.0 | 35 | 1 |  |
| `apps/exams/domain/language.py` | **74.2** | 0.0 | 29 | 6 | ExamLanguageVariant.effective_question_count |
| `apps/exams/domain/question_bank/bank_question.py` | 92.3 | 100.0 | 52 | 4 |  |
| `apps/exams/domain/question_bank/exam_question.py` | 83.2 | 66.7 | 155 | 22 | ExamQuestion.correct_ratio, ExamQuestion.mark_ai_difficulty |
| `apps/exams/domain/student_access.py` | 95.6 | 100.0 | 41 | 2 |  |
| `apps/exams/domain/submission_events.py` | 97.1 | 100.0 | 34 | 1 |  |
| `apps/exams/domain/submission_inbox.py` | 98.7 | 100.0 | 77 | 1 |  |
| `apps/exams/domain/supervision.py` | 88.5 | 100.0 | 61 | 7 |  |
| `apps/exams/services/access_code_crypto.py` | 100.0 | 100.0 | 22 | 0 |  |
| `apps/exams/services/access_policy.py` | **64.5** | 52.4 | 79 | 23 | ensure_can_manage_exam_rooms |
| `apps/exams/services/ai_grading.py` | **73.0** | 57.5 | 235 | 51 |  |
| `apps/exams/services/ai_question_generation.py` | **62.8** | 50.0 | 198 | 63 | _call_gemini_text |
| `apps/exams/services/ai_summary.py` | **37.7** | 19.0 | 157 | 90 | _get_summary_model_chain, _stats_cache_key, _execute_summary, generate_people_analytics_summary, _build_people_prompt |
| `apps/exams/services/attempt_budget.py` | 100.0 | 100.0 | 17 | 0 |  |
| `apps/exams/services/attempts.py` | **76.8** | 69.4 | 242 | 51 |  |
| `apps/exams/services/bank_analysis.py` | 94.6 | 90.0 | 155 | 6 |  |
| `apps/exams/services/bank_fingerprint.py` | **0.0** | 100.0 | 10 | 10 | sqlite_exam_fingerprint,  |
| `apps/exams/services/bulk_workbench.py` | **55.7** | 49.3 | 260 | 106 | bank_written_text_map, exam_written_text_map, parse_written_bulk, analyze_written_bulk |
| `apps/exams/services/coding_definition.py` | **57.5** | 38.9 | 62 | 23 | _question_title, ensure_coding_question_for_exam_question |
| `apps/exams/services/coding_polyfills.py` | 100.0 | 100.0 | 3 | 0 |  |
| `apps/exams/services/coding_runtime/_shared.py` | **76.7** | 60.0 | 33 | 6 |  |
| `apps/exams/services/coding_runtime/constants.py` | 100.0 | 100.0 | 9 | 0 |  |
| `apps/exams/services/coding_runtime/execution.py` | **33.3** | 23.6 | 204 | 129 | _ensure_docker_image, _piston_files_payload, _execute_via_piston |
| `apps/exams/services/coding_runtime/files.py` | 85.1 | 76.5 | 178 | 18 | default_starter_code |
| `apps/exams/services/coding_runtime/grading.py` | **33.9** | 16.7 | 44 | 26 |  |
| `apps/exams/services/coding_runtime/submission.py` | 96.9 | 50.0 | 30 | 0 |  |
| `apps/exams/services/coding_throttle.py` | **73.1** | 41.7 | 81 | 18 |  |
| `apps/exams/services/difficulty.py` | **35.9** | 28.0 | 134 | 82 | _normalise_difficulty, _question_payload, _parse_difficulty_payload, classify_question_difficulties_with_ai, _set_ai_balance_status, warm_ai_question_difficulties_for_exam |
| `apps/exams/services/duplication.py` | **0.0** | 0.0 | 42 | 42 | _clone_supervision_config, duplicate_exam,  |
| `apps/exams/services/exam_center_gate.py` | **72.0** | 85.4 | 145 | 47 | resolve_client_mac |
| `apps/exams/services/exam_definition.py` | **11.8** | 0.0 | 13 | 11 | effective_random_question_count |
| `apps/exams/services/final_center/cabinet.py` | 89.5 | 75.0 | 15 | 1 |  |
| `apps/exams/services/final_center/entry.py` | 88.2 | 79.4 | 194 | 17 |  |
| `apps/exams/services/final_center/events.py` | 85.2 | 50.0 | 25 | 3 |  |
| `apps/exams/services/final_center/history.py` | **68.1** | 53.8 | 68 | 18 |  |
| `apps/exams/services/final_center/monitor.py` | 96.6 | 92.0 | 98 | 1 |  |
| `apps/exams/services/final_center/permissions.py` | **75.2** | 65.8 | 79 | 16 | ensure_can_manage_final_center, ensure_can_supervise_session, ensure_ticket_owner |
| `apps/exams/services/final_center/pins.py` | 86.2 | 69.2 | 90 | 8 | wipe_ticket_pin_cipher |
| `apps/exams/services/final_center/presence.py` | **77.4** | 50.0 | 27 | 5 | touch_ticket_last_seen |
| `apps/exams/services/final_center/reminders.py` | 89.1 | 85.7 | 50 | 5 |  |
| `apps/exams/services/final_center/reports.py` | **64.7** | 50.0 | 55 | 15 |  |
| `apps/exams/services/final_center/room_admin.py` | **72.8** | 65.2 | 112 | 27 |  |
| `apps/exams/services/final_center/sessions.py` | 93.3 | 86.4 | 97 | 5 |  |
| `apps/exams/services/final_center/tickets.py` | **69.1** | 57.1 | 201 | 52 | assign_students, _notify_assignment, set_ready, readmit_student |
| `apps/exams/services/final_center/xlsx_build.py` | **53.7** | 17.6 | 115 | 41 |  |
| `apps/exams/services/final_center/xlsx_report.py` | **67.1** | 44.7 | 117 | 30 | _AcademicIndex._ancestors |
| `apps/exams/services/grading.py` | 94.4 | 85.7 | 40 | 1 |  |
| `apps/exams/services/import_media.py` | **79.1** | 65.3 | 377 | 59 |  |
| `apps/exams/services/import_preview.py` | **17.0** | 0.0 | 41 | 32 | render_stashed_question_preview |
| `apps/exams/services/import_retention.py` | 84.0 | 76.9 | 68 | 9 |  |
| `apps/exams/services/journal_sync.py` | **33.9** | 14.3 | 129 | 77 | _skip, registrar_block_reasons |
| `apps/exams/services/language_parity.py` | 97.4 | 100.0 | 29 | 1 |  |
| `apps/exams/services/language_variants.py` | **74.5** | 66.7 | 138 | 31 | scoped_active_questions, available_language_options_for_exams, auto_language_for_attempt, set_variant_active |
| `apps/exams/services/lifecycle.py` | 96.8 | 92.9 | 49 | 1 |  |
| `apps/exams/services/manual_grading.py` | **57.6** | 26.2 | 135 | 44 |  |
| `apps/exams/services/parsing/_core.py` | 86.5 | 78.9 | 289 | 28 |  |
| `apps/exams/services/parsing/extraction/_deps.py` | **50.0** | 100.0 | 8 | 4 |  |
| `apps/exams/services/parsing/extraction/constants.py` | 100.0 | 100.0 | 19 | 0 |  |
| `apps/exams/services/parsing/extraction/highlight.py` | **72.3** | 60.7 | 139 | 32 |  |
| `apps/exams/services/parsing/extraction/normalize.py` | 88.8 | 76.9 | 72 | 5 |  |
| `apps/exams/services/parsing/extraction/ocr.py` | **37.1** | 43.5 | 140 | 91 | _ensure_tessdata_prefix, _ocr_image_text |
| `apps/exams/services/parsing/extraction/pipeline.py` | 82.6 | 81.2 | 89 | 15 |  |
| `apps/exams/services/parsing/extraction/safety.py` | **66.5** | 57.7 | 118 | 35 | _field_tree_has_actions |
| `apps/exams/services/pdf_layout/answers.py` | 95.3 | 87.5 | 48 | 1 |  |
| `apps/exams/services/pdf_layout/extraction.py` | 94.7 | 90.2 | 278 | 10 |  |
| `apps/exams/services/pdf_layout/limits.py` | **79.6** | 71.4 | 35 | 6 |  |
| `apps/exams/services/pdf_layout/manifest.py` | 83.2 | 0.0 | 99 | 10 | Question.option, Manifest.iter_segments |
| `apps/exams/services/pdf_layout/noise.py` | 100.0 | 100.0 | 6 | 0 |  |
| `apps/exams/services/pdf_layout/ocr.py` | 87.9 | 81.2 | 83 | 9 |  |
| `apps/exams/services/pdf_layout/ownership.py` | 98.5 | 96.4 | 103 | 1 |  |
| `apps/exams/services/pdf_layout/rendering.py` | 87.7 | 77.7 | 265 | 23 |  |
| `apps/exams/services/pdf_layout/slicing.py` | 100.0 | 100.0 | 164 | 0 |  |
| `apps/exams/services/pdf_layout/yellow.py` | 97.8 | 93.2 | 140 | 1 |  |
| `apps/exams/services/pdf_math.py` | **56.2** | 47.4 | 164 | 65 | _build_anchors, _owner_for_y, _regions_by_owner, _render_region, extract_math_images |
| `apps/exams/services/question_bank.py` | 100.0 | 100.0 | 7 | 0 |  |
| `apps/exams/services/question_bank_attach.py` | **69.6** | 52.3 | 104 | 24 | bank_questions_queryset |
| `apps/exams/services/question_chair_review.py` | 92.7 | 87.5 | 141 | 9 |  |
| `apps/exams/services/question_chair_units.py` | 83.7 | 76.0 | 91 | 11 | has_chair_review_access |
| `apps/exams/services/question_delivery.py` | 89.5 | 100.0 | 32 | 4 |  |
| `apps/exams/services/question_invariants.py` | 94.9 | 83.3 | 33 | 1 |  |
| `apps/exams/services/question_snapshot.py` | 92.9 | 75.0 | 24 | 1 |  |
| `apps/exams/services/question_submission.py` | 93.0 | 90.5 | 199 | 12 |  |
| `apps/exams/services/question_timer.py` | 94.7 | 93.8 | 59 | 3 |  |
| `apps/exams/services/question_word_export.py` | 95.9 | 90.9 | 51 | 1 |  |
| `apps/exams/services/randomizer.py` | **73.4** | 59.5 | 189 | 40 | available_question_count, _build_block_pick_plan |
| `apps/exams/services/result_calculation.py` | 98.5 | 100.0 | 107 | 2 |  |
| `apps/exams/services/result_release.py` | 100.0 | 100.0 | 3 | 0 |  |
| `apps/exams/services/retention.py` | 100.0 | 100.0 | 48 | 0 |  |
| `apps/exams/services/review_visibility.py` | 100.0 | 100.0 | 34 | 0 |  |
| `apps/exams/services/second_chance.py` | 93.5 | 87.5 | 77 | 4 |  |
| `apps/exams/services/student_list_batch.py` | 90.2 | 84.9 | 210 | 15 |  |
| `apps/exams/services/student_pins.py` | 91.1 | 80.0 | 105 | 6 |  |
| `apps/exams/services/supervision/_shared.py` | **42.7** | 33.3 | 71 | 39 |  |
| `apps/exams/services/supervision/actions.py` | **73.6** | 63.2 | 83 | 18 | mark_student_returned |
| `apps/exams/services/supervision/constants.py` | 100.0 | 100.0 | 3 | 0 |  |
| `apps/exams/services/supervision/incidents.py` | **73.7** | 61.1 | 58 | 13 |  |
| `apps/exams/services/supervision/interventions.py` | 97.1 | 95.5 | 46 | 1 |  |
| `apps/exams/services/supervision/monitor.py` | 82.4 | 75.0 | 26 | 4 | get_exam_question_total |
| `apps/exams/services/supervision/snapshot.py` | **79.1** | 71.1 | 120 | 22 |  |
| `apps/exams/services/teacher_dashboard.py` | 89.5 | 81.2 | 41 | 3 |  |
| `apps/exams/services/utils.py` | **44.6** | 31.2 | 49 | 25 | _save_paint_png_to_answer |
| `apps/exams/services/visual_import_security.py` | 86.2 | 75.0 | 21 | 2 |  |
| `apps/exams/services/visual_import_upload.py` | **79.7** | 83.3 | 57 | 12 |  |
| `apps/legacy_import/services/account_cutover.py` | 81.7 | 72.9 | 276 | 40 |  |
| `apps/legacy_import/services/batch_accounting.py` | 95.0 | 90.5 | 118 | 4 |  |
| `apps/legacy_import/services/cell_election.py` | 97.3 | 100.0 | 31 | 1 |  |
| `apps/legacy_import/services/excuse_field_contracts.py` | 100.0 | 100.0 | 5 | 0 |  |
| `apps/legacy_import/services/field_contracts.py` | 91.8 | 76.7 | 165 | 9 |  |
| `apps/legacy_import/services/ledger.py` | 87.2 | 79.3 | 245 | 25 |  |
| `apps/legacy_import/services/ledger_batch.py` | 80.5 | 70.8 | 211 | 32 |  |
| `apps/legacy_import/services/ledger_locks.py` | **66.7** | 50.0 | 47 | 14 | _process_scope_lock |
| `apps/legacy_import/services/legacy_demographics.py` | 95.0 | 90.6 | 87 | 3 |  |
| `apps/legacy_import/services/legacy_grade_artifact_contracts.py` | 100.0 | 100.0 | 32 | 0 |  |
| `apps/legacy_import/services/legacy_grade_field_contracts.py` | 100.0 | 100.0 | 5 | 0 |  |
| `apps/legacy_import/services/legacy_grade_formula.py` | 90.5 | 83.3 | 66 | 5 |  |
| `apps/legacy_import/services/legacy_text.py` | 97.8 | 96.2 | 65 | 1 |  |
| `apps/legacy_import/services/lesson_meta_field_contracts.py` | 100.0 | 100.0 | 6 | 0 |  |
| `apps/legacy_import/services/mariadb_gateway.py` | 83.2 | 75.0 | 127 | 18 |  |
| `apps/legacy_import/services/mariadb_source.py` | **69.2** | 56.8 | 350 | 93 |  |
| `apps/legacy_import/services/pk_inventory.py` | **71.6** | 65.4 | 269 | 70 |  |
| `apps/legacy_import/services/pk_inventory_contracts.py` | 81.1 | 63.0 | 163 | 21 |  |
| `apps/legacy_import/services/preflight.py` | 86.5 | 80.8 | 122 | 15 |  |
| `apps/legacy_import/services/rehearsal_authorizer.py` | 95.7 | 100.0 | 61 | 3 | _tenant_owned_bulk_validator.validate_bulk |
| `apps/legacy_import/services/rehearsal_catalog_phase.py` | 96.6 | 91.7 | 95 | 2 |  |
| `apps/legacy_import/services/rehearsal_catalog_source.py` | 99.1 | 97.2 | 318 | 1 |  |
| `apps/legacy_import/services/rehearsal_catalog_targets.py` | 97.9 | 97.6 | 149 | 3 |  |
| `apps/legacy_import/services/rehearsal_contracts.py` | 93.2 | 88.8 | 328 | 18 |  |
| `apps/legacy_import/services/rehearsal_email_trust.py` | 85.6 | 84.6 | 64 | 9 |  |
| `apps/legacy_import/services/rehearsal_excuse_documents.py` | 90.1 | 79.2 | 165 | 11 |  |
| `apps/legacy_import/services/rehearsal_excuse_documents_phase.py` | 100.0 | 100.0 | 71 | 0 |  |
| `apps/legacy_import/services/rehearsal_identity_phase.py` | 92.4 | 86.4 | 243 | 13 |  |
| `apps/legacy_import/services/rehearsal_identity_placeholder.py` | 83.9 | 68.8 | 46 | 5 |  |
| `apps/legacy_import/services/rehearsal_journal_batch.py` | 91.8 | 75.0 | 118 | 5 |  |
| `apps/legacy_import/services/rehearsal_journal_cells.py` | 95.1 | 92.5 | 83 | 3 |  |
| `apps/legacy_import/services/rehearsal_journal_components_phase.py` | 87.6 | 70.6 | 144 | 12 |  |
| `apps/legacy_import/services/rehearsal_journal_enrollments_phase.py` | 97.4 | 96.7 | 121 | 3 |  |
| `apps/legacy_import/services/rehearsal_journal_entry_scores_phase.py` | 99.4 | 96.9 | 148 | 0 |  |
| `apps/legacy_import/services/rehearsal_journal_entry_scores_source.py` | 94.6 | 81.2 | 96 | 3 |  |
| `apps/legacy_import/services/rehearsal_journal_finals_phase.py` | 85.6 | 70.0 | 148 | 15 |  |
| `apps/legacy_import/services/rehearsal_journal_lesson_kinds.py` | 96.4 | 93.8 | 79 | 2 |  |
| `apps/legacy_import/services/rehearsal_journal_lessons_phase.py` | 93.1 | 84.0 | 166 | 7 |  |
| `apps/legacy_import/services/rehearsal_journal_lessons_targets.py` | 96.8 | 100.0 | 60 | 2 |  |
| `apps/legacy_import/services/rehearsal_journal_lock_phase.py` | 94.6 | 85.7 | 97 | 4 |  |
| `apps/legacy_import/services/rehearsal_journal_marks_phase.py` | 98.8 | 96.9 | 136 | 1 |  |
| `apps/legacy_import/services/rehearsal_journal_marks_targets.py` | 99.3 | 97.1 | 116 | 0 |  |
| `apps/legacy_import/services/rehearsal_journal_offerings_phase.py` | 99.4 | 97.5 | 135 | 0 |  |
| `apps/legacy_import/services/rehearsal_journal_offerings_source.py` | 82.2 | 73.5 | 67 | 9 |  |
| `apps/legacy_import/services/rehearsal_journal_offerings_targets.py` | 96.9 | 100.0 | 63 | 2 |  |
| `apps/legacy_import/services/rehearsal_journal_periods_phase.py` | 93.3 | 85.3 | 145 | 7 |  |
| `apps/legacy_import/services/rehearsal_journal_points_source.py` | 80.0 | 65.7 | 170 | 24 |  |
| `apps/legacy_import/services/rehearsal_journal_reconcile_phase.py` | 98.7 | 95.8 | 125 | 1 |  |
| `apps/legacy_import/services/rehearsal_journal_reconcile_source.py` | 83.2 | 66.7 | 113 | 13 |  |
| `apps/legacy_import/services/rehearsal_journal_seal.py` | 95.8 | 100.0 | 62 | 3 |  |
| `apps/legacy_import/services/rehearsal_journal_selfwork_phase.py` | 98.6 | 96.2 | 117 | 1 |  |
| `apps/legacy_import/services/rehearsal_journal_selfwork_source.py` | 92.5 | 84.6 | 80 | 4 |  |
| `apps/legacy_import/services/rehearsal_journal_slices.py` | 94.6 | 87.5 | 76 | 3 |  |
| `apps/legacy_import/services/rehearsal_legacy_grade_artifacts.py` | **78.1** | 60.7 | 86 | 14 |  |
| `apps/legacy_import/services/rehearsal_legacy_grade_artifacts_phase.py` | 94.6 | 80.0 | 64 | 2 |  |
| `apps/legacy_import/services/rehearsal_legacy_grade_facts_phase.py` | 100.0 | 100.0 | 94 | 0 |  |
| `apps/legacy_import/services/rehearsal_legacy_grade_facts_source.py` | 92.9 | 85.4 | 178 | 9 |  |
| `apps/legacy_import/services/rehearsal_legacy_grade_facts_target.py` | **76.3** | 62.5 | 69 | 13 |  |
| `apps/legacy_import/services/rehearsal_lesson_meta_phase.py` | 95.9 | 89.1 | 147 | 3 |  |
| `apps/legacy_import/services/rehearsal_lesson_meta_source.py` | 84.4 | 73.3 | 66 | 7 |  |
| `apps/legacy_import/services/rehearsal_lesson_meta_targets.py` | 96.9 | 89.3 | 134 | 2 |  |
| `apps/legacy_import/services/rehearsal_lesson_recovery_conflicts.py` | 90.5 | 66.7 | 130 | 8 |  |
| `apps/legacy_import/services/rehearsal_lesson_recovery_evidence.py` | 87.9 | 61.1 | 131 | 11 |  |
| `apps/legacy_import/services/rehearsal_lesson_recovery_phase.py` | 90.6 | 79.5 | 201 | 14 |  |
| `apps/legacy_import/services/rehearsal_lesson_recovery_scan.py` | 88.0 | 61.1 | 82 | 5 |  |
| `apps/legacy_import/services/rehearsal_lesson_recovery_source.py` | 84.3 | 75.0 | 63 | 8 |  |
| `apps/legacy_import/services/rehearsal_lesson_recovery_targets.py` | 87.8 | 65.4 | 130 | 10 | same_score |
| `apps/legacy_import/services/rehearsal_lesson_rooms_phase.py` | 94.2 | 82.1 | 109 | 3 |  |
| `apps/legacy_import/services/rehearsal_orchestrator.py` | 89.6 | 75.0 | 136 | 10 |  |
| `apps/legacy_import/services/rehearsal_phase_a.py` | 81.9 | 59.1 | 83 | 10 |  |
| `apps/legacy_import/services/rehearsal_placement_phase.py` | 92.0 | 84.1 | 268 | 15 |  |
| `apps/legacy_import/services/rehearsal_reconciliation.py` | 89.4 | 83.3 | 83 | 7 |  |
| `apps/legacy_import/services/rehearsal_report.py` | 87.4 | 87.5 | 206 | 26 |  |
| `apps/legacy_import/services/rehearsal_sar_archive.py` | **73.9** | 40.0 | 59 | 12 |  |
| `apps/legacy_import/services/rehearsal_sar_phase.py` | 92.2 | 83.3 | 204 | 10 |  |
| `apps/legacy_import/services/rehearsal_sar_targets.py` | 97.2 | 92.9 | 149 | 3 |  |
| `apps/legacy_import/services/rehearsal_structure_phase.py` | 100.0 | 100.0 | 79 | 0 |  |
| `apps/legacy_import/services/rehearsal_structure_source.py` | 98.4 | 96.0 | 194 | 2 |  |
| `apps/legacy_import/services/rehearsal_structure_targets.py` | 98.6 | 97.8 | 174 | 2 |  |
| `apps/legacy_import/services/rehearsal_syllabus_documents.py` | 91.4 | 84.6 | 102 | 7 | SyllabusSourceSnapshot.issue_codes |
| `apps/legacy_import/services/rehearsal_syllabus_phase.py` | 95.5 | 91.3 | 133 | 4 |  |
| `apps/legacy_import/services/rehearsal_syllabus_source.py` | 88.3 | 78.3 | 151 | 13 |  |
| `apps/legacy_import/services/rehearsal_syllabus_targets.py` | 99.1 | 97.2 | 178 | 1 |  |
| `apps/legacy_import/services/rehearsal_target_guard.py` | 94.0 | 92.0 | 150 | 8 |  |
| `apps/legacy_import/services/rehearsal_worker_phase.py` | 92.0 | 82.5 | 136 | 7 |  |
| `apps/legacy_import/services/rehearsal_worker_targets.py` | 90.6 | 76.2 | 160 | 9 |  |
| `apps/legacy_import/services/repair_accounts.py` | **0.0** | 0.0 | 133 | 133 | _issue_codes, plan_missing, resolve_student_user_pks, student_fin_occurrences, role_for, create_account, _offering_index, reattach_journals,  |
| `apps/legacy_import/services/repair_archive.py` | 80.0 | 57.1 | 117 | 17 |  |
| `apps/legacy_import/services/repair_demographics.py` | **54.9** | 25.0 | 62 | 22 | apply_source_demographics |
| `apps/legacy_import/services/repair_periods.py` | 81.2 | 63.6 | 79 | 11 |  |
| `apps/legacy_import/services/repair_pseudo_groups.py` | 92.4 | 77.3 | 110 | 5 |  |
| `apps/legacy_import/services/repair_rooms.py` | 90.6 | 70.0 | 54 | 3 |  |
| `apps/legacy_import/services/repair_sar.py` | 91.9 | 86.7 | 106 | 7 |  |
| `apps/legacy_import/services/repair_support.py` | 82.8 | 70.0 | 92 | 12 |  |
| `apps/legacy_import/services/review.py` | 84.1 | 73.1 | 81 | 10 |  |
| `apps/legacy_import/services/source_attestation.py` | **76.0** | 73.1 | 95 | 22 |  |
| `apps/legacy_import/services/source_extraction.py` | 85.7 | 73.9 | 299 | 32 |  |
| `apps/legacy_import/services/syllabus_field_contracts.py` | 100.0 | 100.0 | 6 | 0 |  |
| `apps/legacy_import/services/syllabus_migration_contracts.py` | 100.0 | 100.0 | 23 | 0 |  |
| `apps/legacy_import/services/table_plan.py` | 88.2 | 72.7 | 97 | 8 |  |
| `apps/legacy_import/services/versioning.py` | 85.0 | 50.0 | 16 | 1 |  |
| `apps/organizations/scoping.py` | 89.7 | 86.4 | 138 | 12 |  |
| `apps/registrar/corrections.py` | 88.0 | 78.1 | 170 | 14 |  |
| `apps/registrar/exam_bridge.py` | **50.0** | 28.6 | 120 | 51 |  |
| `apps/registrar/exam_score_entry.py` | **74.0** | 66.2 | 186 | 43 | offerings_in_actor_scope, subjects_for_period |
| `apps/registrar/exam_score_import.py` | 82.7 | 74.1 | 311 | 44 |  |
| `apps/registrar/exam_score_import_safety.py` | **46.7** | 0.0 | 13 | 6 |  |
| `apps/registrar/exam_score_sheets.py` | **75.5** | 54.5 | 88 | 17 |  |
| `apps/registrar/finals.py` | 91.4 | 79.6 | 168 | 8 |  |
| `apps/registrar/gradebook.py` | 98.0 | 97.0 | 234 | 4 |  |
| `apps/registrar/gradebook_components.py` | **77.9** | 72.6 | 187 | 37 | get_component_grid, get_component_breakdown |
| `apps/registrar/gradebook_lessons.py` | 94.7 | 92.6 | 116 | 5 |  |
| `apps/registrar/item_corrections.py` | 80.2 | 62.5 | 156 | 21 | _cw_entry |
| `apps/registrar/journal_close.py` | 87.2 | 73.3 | 103 | 9 | resolve_unit |
| `apps/registrar/journal_close_notices.py` | 95.3 | 90.0 | 44 | 1 |  |
| `apps/registrar/journal_close_notifications.py` | 88.9 | 50.0 | 32 | 2 |  |
| `apps/registrar/transfer.py` | 89.9 | 83.3 | 55 | 4 |  |
| `apps/syllabus/services/copy_into.py` | **66.7** | 66.7 | 48 | 16 | copy_into_existing |
| `apps/syllabus/services/coverage.py` | 89.8 | 80.6 | 101 | 7 |  |
| `apps/syllabus/services/drafts.py` | 90.4 | 83.3 | 185 | 13 |  |
| `apps/syllabus/services/notifications.py` | 100.0 | 100.0 | 73 | 0 |  |
| `apps/syllabus/services/offerings.py` | 88.1 | 75.0 | 47 | 3 |  |
| `apps/syllabus/services/queries.py` | 85.7 | 83.3 | 91 | 12 | audit_entries |
| `apps/syllabus/services/scoping.py` | 86.1 | 76.5 | 74 | 7 |  |
| `apps/syllabus/services/section_shape.py` | 86.0 | 82.9 | 110 | 13 |  |
| `apps/syllabus/services/units.py` | 85.7 | 73.1 | 58 | 5 |  |
| `apps/syllabus/services/versioning.py` | 88.5 | 80.0 | 42 | 4 | classify |
| `apps/syllabus/services/workflow.py` | 100.0 | 100.0 | 107 | 0 |  |
| `apps/workload/services/amendments.py` | **73.2** | 57.1 | 42 | 9 |  |
| `apps/workload/services/assignments.py` | 88.6 | 75.0 | 90 | 7 |  |
| `apps/workload/services/curriculum_import.py` | **23.5** | 0.0 | 39 | 27 | _credits_for, curriculum_row_suggestions |
| `apps/workload/services/distribution.py` | **76.7** | 70.4 | 148 | 31 |  |
| `apps/workload/services/generation.py` | 80.6 | 70.0 | 99 | 16 | plan_preview |
| `apps/workload/services/imports.py` | 87.5 | 73.7 | 130 | 11 |  |
| `apps/workload/services/objections.py` | **67.9** | 50.0 | 88 | 24 | my_objections, resolve_objection |
| `apps/workload/services/overview.py` | 95.4 | 90.0 | 113 | 3 |  |
| `apps/workload/services/people.py` | **64.8** | 43.8 | 55 | 16 | teacher_pool |
| `apps/workload/services/queries.py` | **41.8** | 30.6 | 110 | 60 | task_rows, serialize_rows, teacher_load_panel, teacher_workload_summaries, chair_tasks |
| `apps/workload/services/reviews.py` | **75.9** | 63.3 | 82 | 16 | row_remarks |
| `apps/workload/services/scoping.py` | 83.1 | 71.9 | 86 | 11 | can_view_task |
| `apps/workload/services/tasks.py` | **69.4** | 61.9 | 174 | 47 | row_warnings, delete_row |
| `apps/workload/services/workflow.py` | 85.5 | 78.1 | 211 | 26 | submit_summary |
| `core/media_policies.py` | **61.7** | 54.1 | 213 | 74 | register_media_policy, check_guest_roster_document_access, check_workload_amendment_access, _notification_file_urls, check_notification_file_access |
| `core/media_views.py` | **64.2** | 58.0 | 250 | 84 | _check_exam_paint_access, _check_lab_file_access, _check_course_resource_access, _check_trial_exam_access |
| `core/permissions.py` | 92.3 | 85.7 | 76 | 4 |  |
| **CƏMİ (kritik dəst)** | **85.88** | **72.69** | 28405 | 4012 | |

Bütün apps+core: statement 78.76 % · branch 66.54 % (96102 stmts, 28350 branches)


**Kritik və ÖRTÜLMƏMİŞ (0 %) funksiyalar — prioritetlə:**
- `apps/exams/services/duplication.py` — **0 %** (`duplicate_exam`, `_clone_supervision_config`): imtahan kopyalama tam testsizdir.
- `apps/exams/domain/grading.py` — **22 %** (`AttemptGradingMixin.mark_checked`, `AnswerGradingMixin.auto_evaluate`): qiymətləndirmə mixin-ləri (avtomatik yoxlama) testsiz.
- `apps/exams/services/journal_sync.py` — **34 %** (`registrar_block_reasons`, `_skip`): imtahan→jurnal körpüsü (backend F-08 səssiz istisna ilə eyni modul).
- `apps/registrar/exam_bridge.py` — **50 %**, `exam_score_import_safety.py` — **47 %**, `exam_score_entry.py::offerings_in_actor_scope` — 0 %: imtahan balının jurnala keçidi zəif örtülüb.
- `apps/exams/services/final_center/permissions.py` — `ensure_can_manage_final_center`, `ensure_can_supervise_session`, `ensure_ticket_owner` **0 %**; `services/access_policy.py::ensure_can_manage_exam_rooms` 0 %: icazə qapıları birbaşa test olunmur (yalnız view-lar vasitəsilə qismən).
- `core/media_views.py` — 64 % (`_check_exam_paint_access`, `_check_lab_file_access`, `_check_course_resource_access`, `_check_trial_exam_access` 0 %); `core/media_policies.py` — 62 % (`check_guest_roster_document_access`, `check_workload_amendment_access`, `check_notification_file_access` 0 %): **media giriş siyasətlərinin yarısı testsiz** (Codex «media scope» testi yalnız bir siyasəti örtür).
- `apps/accounts/services/view_as.py::actor_can_use_view_as` — 0 % (RLS view-as düzəlişindən sonra qapı funksiyası testsiz).
- `apps/workload/services/queries.py` — 42 % (`task_rows`, `teacher_load_panel`, `teacher_workload_summaries`, `chair_tasks` 0 %), `tasks.py::delete_row` 0 %, `objections.py::resolve_objection` 0 %, `curriculum_import.py` 24 %.
- `apps/appeals/services/state_machine.py` — 44 % (`can_transition` 0 %) — backend F-11 ilə uyğun: ölü kod.
- `apps/legacy_import/services/repair_accounts.py` — **0 %** (133 stmt), `repair_demographics.py` 55 %: təmir skriptləri tamamilə testsiz.
- `apps/syllabus/services/copy_into.py::copy_into_existing` 0 %.

## 2. Skip / xfail inventarı (PostgreSQL tam dəst, `-rs`)

Statik inventar: 66 skip/xfail sahəsi (`skip_sites.txt`), bunların 45-i `vendor != "postgresql"` özü-skip (PostgreSQL-də işləyir). **xfail: 0.** PostgreSQL çalışmasında faktiki skip: **16 test / 15 yer**.

| # | Test yeri | Səbəb (testdən) | Sinif | Qiymət |
|---|---|---|---|---|
| 1 | `apps/exams/tests/test_services.py:1706` | Tesseract OCR yoxdur | ətraf mühit | **FAIL (daimi skip)** — CI workflow-larında `tesseract` quraşdırılmır (grep: 0 nəticə) → 3 OCR testi heç vaxt işləmir; `parsing/extraction/ocr.py` 37 % (F-T6) |
| 2–3 | `apps/exams/tests/test_pdf_layout.py:834,847` | Tesseract OCR runtime yoxdur | ətraf mühit | eyni |
| 4 | `apps/legacy_import/tests/test_models.py:256` | «yalnız SQLite limitini sənədləşdirir» | dizayn | OK |
| 5 | `apps/accounts/tests/test_identity_access.py:353` | PG-də SECURITY DEFINER daxilində audit yazılır; `test_identity_access_postgres` örtür | dizayn (əvəzedici test var) | OK — əvəzedici test PASS |
| 6 | `apps/legacy_import/tests/test_ledger_service.py:519` | «process fallback yalnız qeyri-PG üçün» | dizayn | OK |
| 7 | `apps/legacy_import/tests/test_rehearsal_postgres.py:399` | DB-də `emsarena.rehearsal_target` markeri yoxdur | ətraf mühit | **FAIL (daimi skip)** — `.github/workflows/*.yml`-də `ALTER DATABASE … SET emsarena.rehearsal_target` yoxdur → `test_target_guard_reads_real_disposable_marker` heç bir mühitdə işləmir (F-T6) |
| 8 | `apps/legacy_import/tests/test_batch_accounting.py:301` | PG trigger raw UPDATE-i bloklayır; `test_rehearsal_postgres` örtür | dizayn | OK |
| 9–10 | `tests/test_proxy_trust_configuration.py:96,216` | LibreSSL-də `openssl -checkhost` yoxdur | ətraf mühit (macOS) | OK — Linux CI-də işləyir |
| 11–12 | `apps/legacy_import/tests/test_rehearsal_source_integration.py:144` (×2) | disposable MariaDB guard aktiv deyil | ətraf mühit | OK — `mariadb` marker, ayrıca CI işi |
| 13 | `apps/legacy_import/tests/test_mariadb_source_integration.py:35` | eyni | ətraf mühit | OK |
| 14 | `apps/legacy_import/tests/test_pk_inventory_integration.py:32` | eyni | ətraf mühit | OK |
| 15 | `apps/legacy_import/tests/test_source_attestation_integration.py:30` | eyni | ətraf mühit | OK |

**Xətanı gizlədən skip: tapılmadı.** Şərti skip-lər (`test_decorators.py:250,267` «rol tapılmadı») PG çalışmasında işə düşmədi. `core/tests/test_rls_gate_integrity.py:91` «bağlantı rolu NOBYPASSRLS-dirsə skip» — sandbox `emsarena_agent` superuser olduğundan test **işlədi** (bypass yoxlandı); istehsal-bənzər NOBYPASSRLS rolunda o skip olur — dizayn.

**Flaky şübhəliləri (statik grep):**
- `sleep(`: yalnız `core/tests/test_middleware.py:352` (`time.sleep(0.05)`, rate-limit pəncərəsi) — aşağı risk.
- `freezegun`/`time_machine`: **layihədə yoxdur**; `timezone.now()` patch-i yalnız 1 yerdə. 71 test faylı `date.today()/timezone.now()` ilə nisbi tarix qurur (`test_profile_views.py` 71 çağırış, `test_final_center_flow.py` 20, `test_journal_rules.py` 8). Jurnal testləri «bu gün» dərsinə bağlıdır (`gradebook.save_marks enforce_day`) — gecəyarısı UTC↔Baku keçidində (`lesson.date == today`) yarımgecə çalışmalarında flaky ola bilər; sübut: probe-um da `date.today()` ilə dərs yaratmalı oldu. Tövsiyə: `time_machine` əlavə edilib jurnal/semestr testləri dondurulsun.
- `random`/`uuid4` toxumsuz: 21 istifadə (əsasən unikal ad üçün) — determinizmə təsir etmir; `random.seed`: 0.
- Şəbəkə: testlərdə real `requests`/`urlopen` çağırışı **yoxdur** (hamısı mock).
- Real DB URL/.env: heç bir test `.env` oxumur; `5432` yalnız `test_rehearsal_target_guard.py` parametrlərində (qoruma testi) — OK.

## 3. Akademik E2E axınlar

**Metod.** (a) Sandbox HTTP probe `probes/test_e2e_flows.py` — 12 test, Django test client, REAL URL-lər, **istehsal rol kataloqu** (`default_roles.py`, org yaradılanda avtomatik seed; əl ilə icazə siyahısı yoxdur), PostgreSQL trigger-lər aktiv (migrasiyalı DB). Nəticə: **12/12 PASS** (`probes/e2e_results.txt`; iki tapıntı probe-un içində «TAPINTI» kimi kodlaşdırılıb və gözlənilən *səhv* davranışı sənədləşdirir). (b) Dev-clone (:8011) brauzer keçidi — §3.7.

### 3.1 Workload (`WorkloadFlow`, 5 test)
| Addım | Aktor | Endpoint | Gözlənti | Nəticə |
|---|---|---|---|---|
| Tapşırıq yarat | müəllim / tələbə | `POST /ders-yuku/emel/ action=create_task` | 403 | **PASS** 403/403 |
| Tapşırıq yarat | tədris şöbəsi rəhbəri | eyni | 200 `{"id"}` | PASS |
| Sətir yaz | TŞ | `POST /ders-yuku/setir/yadda-saxla/` (JSON: subject_id, period_id, specialty_id, group_ids, saatlar) | 200 | PASS |
| Dublikat sətir (eyni fənn/ixtisas/semestr/qrup dəsti) | TŞ | eyni | rədd, sətir sayı 1 | **PASS** 403 `workload.duplicate_row`, DB-də 1 sətir (`save_row` atomik, `tasks.py:281`) |
| Göndər / təkrar göndər | TŞ | `action=submit` | 200 / 409 | PASS 200 / 409 |
| Göndərilmiş sənədi təsdiqdən əvvəl böl | kafedra müdiri | `POST /ders-yuku/bolgu/` | 403 | PASS 403 `workload.not_approved_yet` |
| Yad fakültə dilimini təsdiq | dekan B | `action=approve_slice` | 403 | PASS |
| Koordinator vizasız təsdiq | dekan A | eyni | rədd | PASS (≠200) |
| Viza | koordinator (öz ixtisası) | `action=review_all` | 200 marked≥1 | PASS |
| Təsdiq | dekan A | `action=approve_slice` | 200 | PASS |
| Yad kafedra sətrini böl | kafedra müdiri B | `POST /ders-yuku/bolgu/` | 403 | PASS |
| Saat həddi (31 > 30) | kafedra müdiri A | eyni | rədd | PASS 403 `workload.hours_exceeded` |
| Tam bölgü (mühazirə 30 → A, seminar 30 → A2) | kafedra A | eyni ×2 | 200 | PASS |
| Natamam bölgü ilə təsdiq | kafedra A | `POST /ders-yuku/bolgu/tesdiq/` | rədd | PASS 403 `workload.distribution_incomplete` (`test_w04`) |
| Təsdiq → `sync_offerings` | kafedra A | eyni, `allow_vacant=0` | 200, status distributed, created=1, instructor_blocked=0 | PASS; açılış `instructor=mühazirəçi`, `lesson_hours=60` |
| Müəllim öz yükünü görür / yad müəllim görmür | müəllim A / B | `GET /ders-yuku/mene/setirler/?year=` | fənn var / yoxdur | PASS |
| Jurnal siyahısında və detalda açılış | müəllim A | `GET /jurnal/`, `GET /jurnal/<id>/` | 200 + fənn adı | PASS |
| Sync idempotent | — | `sync_offerings` 2-ci dəfə | created=0, açılış sayı 1 | PASS (`uniq_offering_subject_period_group`) |
| Audit | — | `AuditLog resource_type=workload.TeachingTask` | var | PASS |
| **Göndərilməmiş TŞ qaralamasını kafedra bölür və təsdiqləyir** | kafedra B | `POST /ders-yuku/bolgu/` + `/bolgu/tesdiq/` | 403 gözlənilirdi | **FAIL — 200/200, status `distributed`, açılış yaradıldı; dekan təsdiqi və koordinator vizası TAM ötürüldü** (`test_w05`, F-T1) |

### 3.2 Schedule (`ScheduleFlow`, 2 test)
| Addım | Aktor | Endpoint | Nəticə |
|---|---|---|---|
| Dərs qoy | müəllim (öz açılışı) / tələbə | `POST /accounts/schedule-manage/action/ add` | PASS 403/403 |
| Yad fakültə açılışına dərs | koordinator A | eyni (B açılışı) | PASS 403 |
| Dərs qoy | koordinator A (öz ixtisası) | eyni | PASS 200 `slot` |
| Dublikat slot | koordinator A | eyni | PASS 400 `errors.time_slot` |
| Eyni qrup, eyni vaxt, başqa fənn | koordinator A | eyni | PASS 400 `errors.conflict` |
| Eyni müəllim başqa qrupda eyni vaxt | RİM (org-wide) | eyni | PASS 400, `conflict.reason="müəllim"` |
| Eyni otaq (böyük/kiçik hərf fərqli) başqa qrup | RİM | eyni | PASS 400 conflict |
| Tərs saat / weekday=8 | koordinator | eyni | PASS 400/400 |
| Qismən üst-üstə düşmə (09:00–10:30 vs 08:30–10:00) | koordinator | `start_time/end_time` | PASS 400 |
| Tək/cüt həftə eyni xana | koordinator | `week_type=odd` + `even` | PASS 200/200 |
| Tələbə öz qrup cədvəlini görür (read-only) | tələbə A | `GET /jurnal/cedvel/?period=` | PASS 200, `role=student`, `schedule_can_manage=False` |
| Müəllim öz cədvəli | müəllim A | eyni | PASS `role=teacher` |
| B qrupu tələbəsi A dərsini görmür | tələbə B | eyni | PASS |
| ICS ixracı | tələbə | `GET /jurnal/cedvel/export.ics` | PASS 200 `text/calendar` |
| Sil | müəllim / koordinator | `action=delete` | PASS 403 / 200 soft-delete (`is_deleted=True`) |
| Keçmiş semestr | RİM | `add` (end_date < bu gün) | PASS 400 `errors.period` |
| **Dərc/qaralama statusu** | — | `ScheduleSlot` modeli | **NOT APPLICABLE — belə sahə yoxdur**: slot yaradılan an tələbəyə görünür; «period başlamayıb» yoxlaması da yoxdur (yalnız `end_date`), DB səviyyəsində üst-üstə düşmə məhdudiyyəti (exclusion constraint) yoxdur — qoruma yalnız servis qatındadır (F-T7, P3) |

### 3.3 Syllabus (`SyllabusFlow`, 1 uzun test)
| Addım | Aktor | Endpoint | Nəticə |
|---|---|---|---|
| Qaralama yarat (yad açılış) | müəllim B | `POST /accounts/profile/syllabus/action/ create` | PASS 404 |
| Qaralama yarat | tələbə | eyni | PASS 403 |
| Qaralama yarat | müəllim A | eyni | PASS 200; `chair_unit` müəllimin kafedrasından törədi (qrup→ixtisas→kafedra fallback) |
| Natamam göndərmə | müəllim A | `submit` | PASS 409 `transition.incomplete` |
| 9 bölməni doldur | müəllim A | `POST …/version/<v>/section/` ×9 | PASS 200, completion 100 % (biznes qaydaları: `MIN_GOAL_CHARS=60` və s. server tərəfdən tətbiq olunur — probe-un qısa «goal»-u rədd edildi) |
| Yad müəllim bölmə yazır | müəllim B | eyni | PASS 403/404 |
| Göndər | müəllim A | `submit` | PASS 200 `submitted` |
| İcazəsiz təsdiq | müəllim A / dekan A / kafedra müdiri B | `POST …/version/<v>/decision/ approve` | PASS 404 / 403 `transition.permission_denied` / 404; status dəyişmədi |
| Göndərilmiş versiyanı redaktə | müəllim A | section save | PASS 403 `version.locked` |
| Baxışı aç | kafedra müdiri A | `POST …/review/` | PASS 200 → `review` |
| Səbəbsiz düzəliş | kafedra A | `revise reason="qısa"` | PASS 400 |
| Düzəliş (səbəb + bölmə şərhi) | kafedra A | `revise` | PASS 200 → `revision` |
| Düzəliş edib yenidən göndər | müəllim A | section save + `submit` | PASS 200/200 |
| Tələbə təsdiqdən əvvəl | tələbə A | `GET /jurnal/<off>/sillabus.json` | PASS 404 |
| Təsdiq | kafedra A | `approve` | PASS 200 `approved` |
| Tələbə təsdiqlənmişi görür / yazılmamış tələbə | tələbə A / B | `sillabus.json`, `/accounts/syllabus/<id>/` | PASS 200 mode=student, status=approved / 404 |
| Təsdiqlənmişi səssiz redaktə | müəllim A | section save | PASS 403 `version.locked` |
| Təsdiqdən sonra yenidən qərar | kafedra A | `revise` | PASS 409 |
| Rəy tarixçəsi | — | `SyllabusReview` | PASS: submitted×2, opened, revision (səbəb saxlanılıb), approved |

### 3.4 Journal (`JournalFlow`, 1 uzun test)
| Addım | Aktor | Endpoint | Nəticə |
|---|---|---|---|
| Jurnal aç | müəllim A / müəllim B / tələbə | `GET /jurnal/<off>/` | PASS 200 / 404 / 404 |
| Dərs əlavə (bu gün) | müəllim B / tələbə / müəllim A | `POST … action=add_lesson` | PASS 404 / 404 / 302 + `Lesson` |
| Dublikat dərs (eyni tarix+saat) / semestr sonundan sonra | müəllim A | eyni | PASS — sayı dəyişmir |
| Bal 11 / −1 | müəllim A | `score__<lesson>__<enr>` | PASS — yazılmır (0–10 tam ədəd) |
| Bal 8 + iştirak | müəllim A | eyni | PASS 302, `LessonMark.score=8`, `AuditLog registrar.grade.mark` |
| Yad müəllim / tələbə bal yazır | B / tələbə | eyni | PASS 404/404, bal 8 qalır |
| Tələbə öz jurnalı (read-only) | tələbə A | `GET /accounts/profile/?section=my-journal` | PASS 200 |
| Jurnal bağlama | müəllim / RİM | `POST /accounts/jurnal-baglama/ close scope=organization` | PASS 403 / 302, `journal_is_locked=True`, `AuditLog registrar.journal_close` |
| Bağlı jurnala bal / dərs | müəllim A | save marks / add_lesson | PASS — heç nə yazılmır |
| Düzəliş (journal.correct yoxdur) | müəllim A | `POST /jurnal/duzelis/<off>/tetbiq/` | PASS 404 |
| Düzəliş sənədsiz / qeydsiz | RİM | eyni | PASS 400 / 400 |
| Düzəliş (səbəb+qeyd+PDF) | RİM | eyni (XHR) | PASS 200, bal 8→9, `JournalCorrection(reason=technical, document)`, `AuditLog registrar.grade.correction` |
| Yenidən açılış (səbəbli) → müəllim düzəldilmiş xananı əzir? | RİM / müəllim A | reopen + save marks | PASS — bal 9 qalır (düzəliş edilmiş xana müəllimə bağlıdır) |
| Qeyd | | | Düzəliş `note` üçün minimum uzunluq yoxdur (boş olmayan kifayətdir); PDF `%PDF` sehrli baytı yoxlanmır — yalnız uzantı/MIME (P3, F-T8) |

### 3.5 Student centre (`StudentCentreFlow`, 2 test — `TransactionTestCase`, çünki `uniq_group_transfer_record_transaction` (record, txid) TestCase-in tək tranzaksiyasında süni toqquşur)
| Addım | Aktor | Endpoint | Nəticə |
|---|---|---|---|
| Qrup köçürmə | müəllim / tələbə | `POST /accounts/student-registry/action/ kind=group_transfer` | PASS 403/403 |
| Qısa səbəb (<20) / eyni qrup | tələbə xidmətləri | eyni | PASS 400 `reason_too_short` / 409 `same_group` |
| ORM ilə çılpaq `group` yazısı | — | `StudentAcademicRecord.update(group=)` | PASS `IntegrityError` (trigger `registrar_student_group_transfer_guard`) |
| Sənədli köçürmə (əmr №, tarix, ≥20 simvol səbəb) | tələbə xidmətləri | eyni | PASS 200; `record.group` yeniləndi; `StudentMovement(from→to)`; `AuditLog accounts.people.movement`/`registrar.group_transfer` |
| Yad fakültə dekanı A tələbəsini köçürür | dekan B | eyni | PASS 403/404 |
| Kart + hərəkət tarixçəsi | tələbə xidmətləri / tələbə | `GET /accounts/student-registry/card/<rec>/` | PASS 200 (1 hərəkət) / 403-404 |
| Akademik qeyd | dekan A | `GET /accounts/profile/academic-records/student/?student=` | PASS 200 `has_access=True` |
| Transkript PDF | RİM / tələbə B | `GET /jurnal/telebe/<rec>/transkript.pdf` | PASS 200 `application/pdf` / 403-404 |
| Xaric etmə | tələbə xidmətləri | `kind=expulsion` | PASS 200 → `expelled`; sonra `group_transfer` rədd; hesab silinmir; 2 hərəkət |
| **Bərpa köhnə qrupa** | tələbə xidmətləri | `kind=reinstatement target_group=<köhnə>` | 409 `movement_rejected` «tarixi qeydiyyat var; inzibati yoxlama» — dizayn qoruması (dropped enrollment), amma UI-da həll yolu yoxdur |
| **Bərpa cari qrupa** | tələbə xidmətləri | `target_group=<record.group>` | **FAIL — 409 `same_group`** (`registrar/movements.py:293` növ istisnası yoxdur): xaric edilmiş tələbə nə köhnə, nə cari qrupa bərpa oluna bilmir, yalnız 3-cü qrupa (F-T2, P2) |
| Bərpa 3-cü qrupa | tələbə xidmətləri | eyni | PASS 200 → `enrolled` |
| Tələbə yaratma (intake CSV) | müəllim / RİM | `POST /accounts/student-intake/apply/` | PASS 403 / 200 created=1, qrup düzgün; **`birth_date` faktiki məcburidir** (boş → `birth_date_invalid`), `intake/spec.py` isə onu məcburi siyahıda göstərmir — mesaj «tanınmadı» yanıldıcıdır (P3, F-T9) |
| Silmə | — | — | NOT APPLICABLE: tələbə mərkəzində «sil» yoxdur; hard delete yalnız superadmin, `StudentMovement.record` PROTECT |
### 3.6 Applications (`ApplicationsFlow`)
| Addım | Aktor | Endpoint | Nəticə |
|---|---|---|---|
| Kataloq | — | `seed_catalog(org)` | Qeyd: yeni org üçün növ/vahid AVTOMATİK seed olunmur (yalnız migrasiya 0003 + komanda) — yeni universitet yaradanda müraciət modulu boşdur (P3, F-T10) |
| Qısa mətn | tələbə A | `POST /muracietler/api/create/ body="x"` | PASS 400 |
| Transkript sorğusu | tələbə A | `kind=transkript` | PASS 200 `status.key=submitted`, `current_unit=telebe`, `MR-000001` |
| Başqa tələbə detal / müəllim həll edir | tələbə B / müəllim | `GET/POST /muracietler/api/<id>/…` | PASS 404 / 404 (mövcudluq sızmır) |
| Siyahı | tələbə xidmətləri | `GET /muracietler/api/list/` | PASS `counts.inbox=1` (default tab `mine` — inbox üçün `?tab=inbox`) |
| Aç (avto `mark_seen`) | tələbə xidmətləri | `GET …/<id>/` | PASS → `in_review` |
| Həll et | tələbə xidmətləri | `action=resolve text≥10` | PASS → `resolved` |
| Tələbə cavabı görür, bağlayır | tələbə A | `GET` + `action=close` | PASS |
| Bağlı müraciətə handler əməli | tələbə xidmətləri | `resolve` | PASS 400/403 |

### 3.7 Dev-clone brauzer/HTTP keçidi (:8011, `clone_crawl.txt`)
**HTTP crawl (11 QA rolu, hər rolun profil naviqasiyasından çıxarılan BÜTÜN bölmələr + fragment API + modul URL-ləri; 1 059 sorğu):**
| Rol | Bölmə sayı | Kodlar | Problem |
|---|---|---|---|
| qa.teacher | 20 | 200×52, 403×5 | — |
| qa.student | 17 | 200×46, 403×5 | — |
| qa.program_coordinator | 26 | 200×66, 403×3 | — |
| qa.chair_head | 43 | 200×97, 403×6 | — |
| qa.dean | 43 | 200×98, 403×5 | — |
| qa.teaching_office_head | 25 | 200×56, 403×4 | (parol yox idi — QA hesabına `<QA parolu>` təyin edildi) |
| qa.ikt_rehber | 61 | 200×128, 403×11 | — |
| qa.student_services | 21 | 200×48, 403×4 | (parol təyin edildi) |
| qa.rector | 55 | 200×119, 403×7, **500×1** | `GET /accounts/profile/?section=exam-score-entry` → 500 `relation "registrar_examscoresheet" does not exist` — **klon sxem sürüşməsi**: klon `registrar 0070 / exams 0065`-dədir, kod `registrar 0073 (+0074/0075 işçi ağac) / exams 0066` (F-T4). Eyni səbəbdən `exams 0066` unikal indeksi klonda yoxdur — imtahan cəhdi yarış testləri klonda etibarsızdır. |

403-lər: yalnız modul endpoint-ləri (məs. tələbə üçün `/ders-yuku/kafedralar/`, müəllim üçün `/accounts/people/students/list/`) — düzgün. Heç bir səhifə > 5 s olmadı; heç bir cavabda traceback sızması yoxdur (500 səhifəsi generikdir).

**Brauzer konsolu (qa.rector, 8 JS-ağır səhifə):** `schedule-manage`, `workload-distribution`, `workload-center`, `syllabus-list`, `student-registry`, `applications`, `journal-close`, `/jurnal/` — **konsol xətası / CSP blokajı: 0**.

**Yazı əməlləri klonda aparılmadı** (yalnız QA hesab parolu) — bütün yazı yolları sandbox probe-larında (real kod, real trigger-lər) sınandı.

## 4. Test-suite gigiyenası

| # | Yoxlama | Nəticə | Sübut |
|---|---|---|---|
| H1 | `requirements/test.txt` ↔ venv | **FAIL** — `pytest-cov==6.1.0` və `pytest-timeout==2.4.0` venv-də **yoxdur** (`pip show` MISSING). Lokal coverage ölçülə bilmir; `@pytest.mark.timeout` (5 yer) lokal heç vaxt tətbiq olunmur → CI-də timeout-la kəsilən test lokalda «keçir» | `pip show`; `pyproject.toml:49-54` şərhi bunu bilir |
| H2 | pytest konfiq xəbərdarlıqları | PASS — `setup.cfg` dublikatı silinib (Codex §7), `--co` təmiz | `setup.cfg` şərhi |
| H3 | Yavaş testlər (>10 s) | **PARTIAL** — 34 test > 10 s; ilk 5: `test_access_code_migration…restores_plaintext` **262.7 s**, `test_rubric_component_migration…invalid_points` 203.9 s, `test_reference_identity_migration…round_trip` 183.9 s, `…mismatched_component_total` 127.6 s, `test_reference_identity_migration…survives_forward` 104.3 s. Səbəb: `MigrationExecutor` geri/irəli miqrasiya (286 node) hər testdə. Bu 4 fayl (`test_rubric_component_migration`, `test_reference_identity_migration`, `test_access_code_migration`, `legacy_import/test_*_migration_postgres`) dəstin ≈ 25 dəqiqə CPU-sunu yeyir. Həmçinin 6 sinif `setup` 114–115 s (`test_services.py::ExamAttemptManagementServicesTest`, `test_journal_views.py::JournalViewTest`, …) — `--dist loadfile` ilə eyni worker-də DB yaradılışını gözləyir | `full_run.log` «slowest 40» |
| H4 | Şəbəkəyə çıxan testlər | PASS — yoxdur | grep |
| H5 | Real DB URL / `.env`-dən asılı testlər | PASS — yoxdur; `test_rehearsal_target_guard.py` məhz qorumanı sınayır | grep |
| H6 | RLS testlərində `postgres` markeri | PASS (1 istisna) — 22 RLS/PG faylı markerlidir; `apps/accounts/tests/test_view_as_session_end.py` yalnız `_skip_if_not_pg()` ilə özü-skip edir, marker yoxdur → `pytest -m postgres` onu seçmir (P3) | grep |
| H7 | Dublikat fixture-lar | **PARTIAL** — `tests/conftest.py` 15 fixture (`teacher_user`, `student_user`…) və `apps/trial_exams/tests/conftest.py`; qalan 532 fayl **hər biri öz** `Organization.objects.create(...)` qurur (280 fayl), `_make_org` 11 kopya, `_make_organization` 4, `_create_org` 3, `activate_member` 3 fərqli imza (`workload/tests/factories.py`, `syllabus/tests/factories.py`, `people_fixture.py`). `factory_boy` yoxdur. 162 sinif `setUp`-da org yaradır (hər testdə) — `setUpTestData`-ya keçid bu sinifləri 3–10× sürətləndirər | grep |
| H8 | Flaky şübhəliləri | bax §2 — `freezegun`/`time_machine` yoxdur; jurnal testləri `date.today()`-ə bağlıdır | grep |
| H9 | Sandbox/CI ilə klon sxem sürüşməsi | **FAIL** — bax F-T4 | `django_migrations` |
| H10 | Paralel migrasiya adları | **FAIL (proses)** — bu audit zamanı işçi ağacda iki `0074_*` yarpaq (`0074_finalgrade_exam_score_range` + `0074_rls_guest_roster_document`, hər ikisi untracked) eyni anda mövcud idi → `CommandError: Conflicting migrations` — tam dəst və hər `--reuse-db` çalışması bloklandı; 20 dəq sonra 0075-ə adlandırıldı. CI-də `makemigrations --check --dry-run` + `migrate --plan` addımı var, amma lokal pre-commit/agent qaydası yoxdur (F-T5) | `git status`, `full_run.log:188` |
| H11 | Test sayı / fayl | 534 test faylı, 8 618 test + 1 382 subtest; `apps/accounts/tests/test_profile_views.py` və s. böyük fayllar | `find` |

## 5. Əlavə edilməli testlər (prioritetlə, təklif olunan fayl adları)

| Pri | Sahə | Test (fayl → nə yoxlayır) | Əsas |
|---|---|---|---|
| P1 | Workload | `apps/workload/tests/test_distribution_gate_office_draft.py` — TŞ-nin yaratdığı, göndərilməmiş qaralamanı kafedra müdiri bölə/təsdiqləyə bilməməlidir (HTTP `/ders-yuku/bolgu/` + `/bolgu/tesdiq/` → 403) | F-T1; mövcud `test_legacy_chair_created_draft_still_distributes` yalnız kafedra-yaratmış halı örtür |
| P1 | Workload → Jurnal | `apps/workload/tests/test_chain_http_default_roles.py` — bu auditin `WorkloadFlow.test_w03` zənciri: istehsal rol kataloqu ilə HTTP boyunca TŞ→viza→dekan→bölgü→`sync_offerings`→`/jurnal/` görünməsi | mövcud zəncir testləri əl ilə icazə siyahısı işlədir; kataloq reqressiyası tutulmur |
| P1 | Exam engine | `apps/exams/tests/test_duplication.py` — `duplicate_exam` (sual/variant/nəzarət konfiqi klonlanır, orijinal toxunulmur, yad org 404); `apps/exams/tests/test_grading_mixins.py` — `mark_checked`/`auto_evaluate` | coverage 0 % / 22 % |
| P1 | Exam → Jurnal | `apps/exams/tests/test_journal_sync_block_reasons.py` — `registrar_block_reasons`, `_skip` yolları (bağlı jurnal, dropped enrollment, yad açılış) | 34 %; backend F-08 səssiz istisna |
| P1 | Media/permission | `core/tests/test_media_policies_matrix.py` — `check_guest_roster_document_access`, `check_workload_amendment_access`, `check_notification_file_access`, `_check_exam_paint_access`, `_check_lab_file_access`, `_check_course_resource_access`, `_check_trial_exam_access`: sahib/yad org/yad rol × 200/403/404 | 0 % funksiyalar; tenant sızması riski |
| P1 | Final centre permissions | `apps/exams/tests/test_final_center_permission_gates.py` — `ensure_can_manage_final_center`, `ensure_can_supervise_session`, `ensure_ticket_owner`, `ensure_can_manage_exam_rooms` birbaşa (rol × unit) | 0 % |
| P2 | Student centre | `apps/accounts/tests/test_student_reinstatement_same_group.py` — xaric edilmiş tələbə cari/köhnə qrupa bərpa oluna bilməlidir | F-T2 |
| P2 | Schedule | `apps/accounts/tests/test_schedule_manage_cross_org.py` — yad org `offering_id`/`slot_id`/`group_id` ilə `check/action/editor` → 403/404; müəllim toqquşması HTTP `schedule_manage_check` üzərindən; `period.start_date` gələcəkdirsə (semestr başlamayıb) | agent hesabatında boşluq: cross-org HTTP testi yoxdur |
| P2 | Syllabus | `apps/accounts/tests/test_syllabus_http_chain.py` — bu auditin `SyllabusFlow.test_s01` (HTTP create→section→submit→revise→resubmit→approve→tələbə); müəllimin `decision`-a POST-u; təsdiqlənmiş versiyaya `section_save` 403 | HTTP-səviyyə zəncir testi yoxdur |
| P2 | Journal | `apps/registrar/tests/test_journal_close_then_write_http.py` — RİM bağlama → müəllim HTTP save_marks/add_lesson heç nə yazmır; reopen səbəbsiz 4xx; `time_machine` ilə `MARK_EDIT_WINDOW` sərhədi (2 s 00 dəq 00 san) | backend probe-ları servis qatındadır; tarixə bağlı testlər dondurulmayıb |
| P2 | Auth | `apps/accounts/tests/test_view_as_gate.py` — `actor_can_use_view_as` (0 %) rol × org matrisi | RLS view-as düzəlişindən sonra qapı testsiz |
| P2 | Migration integrity | `tests/test_migration_graph_single_leaf.py` — hər app üçün tək yarpaq (`MigrationLoader.detect_conflicts()` boş) — sürətli, xdist-dən əvvəl işləyən | F-T5 |
| P2 | Workload | `apps/workload/tests/test_queries_panels.py` — `task_rows`, `teacher_load_panel`, `teacher_workload_summaries`, `chair_tasks`; `test_objections.py::resolve_objection`; `delete_row` | 42 % / 0 % |
| P3 | Tenant isolation | `tests/integration/test_tenant_isolation_academic.py` — `ScheduleSlot`, `Syllabus`, `StudentMovement`, `Application` üçün org-B aktoru ilə HTTP 404 (mövcud `test_tenant_isolation.py` bu 4 modeli örtmür — yoxlanmalı) | |
| P3 | Applications | `apps/applications/tests/test_new_org_catalog.py` — yeni org-da `catalog` boşdursa `create` 400 «növ yoxdur» + `seed_catalog` sonrası işləyir | F-T10 |

## 6. Tapıntılar (P0–P3) və minimal düzəlişlər

| ID | Sev | Tapıntı | Sübut | Minimal düzəliş |
|---|---|---|---|---|
| F-T1 | **P1** | **Dekan təsdiqi ötürülür:** TŞ-nin yaratdığı, hələ göndərilməmiş (`submitted_at IS NULL`, status `draft`) tapşırığı kafedra müdiri `/ders-yuku/bolgu/` ilə bölüb `/ders-yuku/bolgu/tesdiq/` ilə `distributed` edir, `sync_offerings` açılış yaradır — koordinator vizası və dekan təsdiqi olmadan. `ensure_distribution_stage` (`apps/workload/services/workflow.py:72-90`) «kafedra özü yaratmışsa» istisnasını `submitted_at` ilə yoxlayır, `created_by`-ı yox; `confirm_distribution` (`distribution.py:266`) da `DRAFT`-ı qəbul edir | `probes/test_e2e_flows.py::WorkloadFlow::test_w05` PASS (=bypass təsdiqləndi) | `workflow.py:ensure_distribution_stage`: `if task.status == DRAFT and (task.submitted_at is not None or not _created_by_chair(task, actor))` — `_created_by_chair`: `task.created_by_id == actor.user.pk` və ya yaradanın həmin kafedrada `workload.distribute` daşıması; alternativ: `get_or_create_task`-da yaradan `workload.submit` daşıyırsa `TeachingTask.office_owned=True` (migrasiya) və `DRAFT` istisnasını `not office_owned` ilə məhdudlaşdır. Test: §5 sətir 1 |
| F-T2 | P2 | **Xaric edilmiş tələbə bərpa oluna bilmir:** `reinstatement` üçün `target_group` məcburidir, amma `validate()` (`apps/registrar/movements.py:293`) `same_group` (409) yoxlamasını növdən asılı olmadan tətbiq edir → cari (köhnəlmiş) qrupa bərpa 409 `same_group`; köhnə qrupa isə `transfer.py:125` «tarixi qeydiyyat var» 409. Yalnız üçüncü qrupa bərpa mümkündür | `StudentCentreFlow::test_st01` (409 `same_group`, 409 `movement_rejected`) | `movements.py:293`: `if new_group is not None and record.group_id and new_group.pk == record.group_id and rule.kind != MovementKind.REINSTATEMENT` (bərpada eyni qrup = «qrupu saxla», `_apply_group` onsuz da no-op qaytarır); köhnə qrupa bərpada dropped enrollment-lər üçün UI-da «tarixçəni bərpa et» yolu və ya mesajda konkret addım |
| F-T3 | P3 | venv-də `pytest-cov`/`pytest-timeout` yoxdur (`requirements/test.txt`-də pinlənib) → lokal coverage və `@pytest.mark.timeout` işləmir | `pip show` | `pip install -r requirements/test.txt`; `scripts/`-də venv sinxron yoxlaması (`pip check` / `pip-sync`) |
| F-T4 | P2 (mühit) | QA klon (`:55433`) sxemi koddan geridir: `registrar 0070`, `exams 0065` vs kod `0073(+0075)`, `0066` → `?section=exam-score-entry` **500** (`registrar_examscoresheet` yoxdur); `exams 0066` unikal indeksi klonda yox — imtahan cəhdi yarış sınaqları klonda mənasız | `preview_logs`, `django_migrations` | Klonda `manage.py migrate` (yalnız klon DB-də, `EMS_DB_ROLE_ENFORCE=error` ilə); `scripts/staging_inspect.sh serve`-ə `migrate --check` xəbərdarlığı |
| F-T5 | P2 (proses) | Paralel agentlər eyni nömrəli migrasiya yaratdı (`0074_*` ×2, untracked) → 20 dəq ərzində bütün `pytest`/`migrate` `Conflicting migrations` ilə bloklandı; tam dəstdə 1 test teardown-da `NodeNotFoundError` | `full_run.log:188`, `git status` | `tests/test_migration_graph_single_leaf.py` (§5) + agent qaydası: migrasiya yaratmazdan əvvəl `ls apps/<app>/migrations | tail -1`; `pre-commit`-də `makemigrations --check` |
| F-T6 | P3 | 4 test heç bir mühitdə işləmir: 3 Tesseract OCR testi (CI-də `tesseract` quraşdırılmır) və `test_target_guard_reads_real_disposable_marker` (CI DB-də `emsarena.rehearsal_target` GUC yoxdur) | `-rs`, workflow grep | `_unit-tests.yml`: `apt-get install -y tesseract-ocr tesseract-ocr-aze` və PG servisində `ALTER DATABASE test_db SET emsarena.rehearsal_target='disposable'`; ya da testləri `mariadb` kimi ayrıca marker altına alıb sənədləşdirmək |
| F-T7 | P3 | Cədvəl: dərc/qaralama statusu yoxdur (slot dərhal tələbəyə görünür); `period_window_error` yalnız `end_date`-i yoxlayır (başlamamış semestr üçün yazı açıqdır); `ScheduleSlot`-da DB səviyyəsində üst-üstə düşmə məhdudiyyəti yoxdur — iki paralel `add` eyni xananı yaza bilər (servis `find_conflict` yarışdan qorumur) | `ScheduleFlow::test_sc02`, `models/academic.py:491-556` | `ExclusionConstraint` (btree_gist) `organization, offering__group…` mümkün deyil (FK üzərindən) → ən azı `UniqueConstraint(offering, weekday, start_time, week_type)` + `select_for_update` ilə qrup/müəllim/otaq yoxlaması; `is_published` sahəsi məhsul qərarıdır |
| F-T8 | P3 | Jurnal düzəlişində `note` üçün minimum uzunluq yoxdur (1 simvol kifayətdir), yüklənən PDF-də `%PDF` sehrli baytı yoxlanmır (yalnız uzantı/MIME) — hərəkət əmrlərində (`MOVEMENT_REASON_MIN_LENGTH=20`) və workload-da (≥20) minimum var | `JournalFlow::test_j01`, `correction_views.py:61-72`, `models/corrections.py:131` | `corrections._validate`: `len(note) >= 20`; `FileUploadValidator`-a magic-bayt yoxlaması (layihə yaddaşında WCU PDF qaydası ilə eyni) |
| F-T9 | P3 | Tələbə intake: `birth_date` boş → `birth_date_invalid` «tanınmadı (gg.aa.iiii)» — sahə faktiki məcburidir, `intake/spec.py:39-51` məcburi siyahısında deyil, mesaj «boşdur» demir | `StudentCentreFlow::test_st02` | `validate.py`: boş → `birth_date_required` ayrı kod/mesaj; `spec.py` sənədini uyğunlaşdır |
| F-T10 | P3 | Yeni təşkilat üçün `ApplicationKind`/`ApplicationUnit` avtomatik seed olunmur (yalnız migrasiya `0003` + `seed_application_catalog` komandası) → yeni universitetdə müraciət modulu boş, `create` 400 | `apps/applications/services/catalog.py`, `organizations/signals.py` | `organizations/signals.py::create_default_roles`-a `seed_catalog(instance)` çağırışı (idempotent) |
| F-T11 | P2 | Kritik coverage boşluqları: `exams/services/duplication.py` 0 %, `exams/domain/grading.py` 22 %, `exams/services/journal_sync.py` 34 %, `registrar/exam_bridge.py` 50 %, `core/media_views.py`/`media_policies.py` 62–64 % (8 giriş yoxlayıcı 0 %), `final_center/permissions.py` 3 qapı 0 %, `view_as.actor_can_use_view_as` 0 %, `legacy_import/repair_accounts.py` 0 % | `coverage_table.md` | §5 P1 sətirləri |
| F-T12 | P2 | 4 migrasiya-geri/irəli test faylı ≈ 25 CPU-dəq (ən yavaşı 263 s) — tam dəstin 15,5 dəq divar vaxtının böyük hissəsi bir worker-də | `full_run.log` durations | Bu testləri `@pytest.mark.slow` + ayrıca CI işi (nightly) və ya sinifdə tək `migrate_to` ilə bir dəfə geri/irəli gedib bütün ssenariləri `subTest`-lə yoxlamaq |
| F-T13 | P3 | `apps/accounts/tests/test_view_as_session_end.py` PG-only, amma `@pytest.mark.postgres` markeri yoxdur (`-m postgres` seçmir) | grep | `pytestmark = pytest.mark.postgres` |
| F-T14 | P3 | `freezegun`/`time_machine` yoxdur; jurnal «bu gün» qaydası (`gradebook.save_marks enforce_day`) və 71-fayllıq `date.today()` istifadəsi gecəyarısı/TZ keçidində flaky riski | §2 | `time_machine` əlavə et; `JournalViewTest`, `test_journal_rules`, `test_final_center_flow` dondurulsun |

**Backend auditoru ilə təkrar etməmək üçün:** state-machine sınaqları (S1–S17), `save_marks` kilidi, apellyasiya ölü state-machine (F-11) burada təkrarlanmır — mənim probe-larım HTTP səthindən və istehsal rol kataloğu ilə gedir.

## 7. Ballar (0–100)

| Sahə | Bal | Əsaslandırma |
|---|---|---|
| **Automated Tests** | **74** | 8 618 test PASS, PG-də real skip cəmi 16 (hamısı mühit/dizayn, gizlədən yoxdur), RLS markerləri düzgün, şəbəkə/real-DB asılılığı yoxdur (+). Mənfi: kritik dəstdə 85.9 %/72.7 % amma imtahan kopyalama 0 %, qiymətləndirmə mixin-ləri 22 %, media siyasətlərinin yarısı testsiz, final mərkəzi icazə qapıları birbaşa testsiz (F-T11); venv `pytest-cov`/`timeout`-suz (F-T3); 4 test heç yerdə işləmir (F-T6); 25 CPU-dəq migrasiya testləri (F-T12); fixture dublikasiyası (280 fayl öz org-unu qurur); tarix dondurma yoxdur (F-T14); paralel migrasiya konflikti dəsti blokladı (F-T5) |
| **Teaching Workload** | **68** | Zəncir HTTP-də istehsal rolları ilə işləyir: dublikat sətir atomik rədd, saat həddi, natamam bölgü bloku, yad fakültə/kafedra 403, `sync_offerings` idempotent, jurnal görünür, audit var (+). **Mənfi: F-T1 — göndərilməmiş TŞ qaralamasını kafedra dekan təsdiqi olmadan bölüb açılış yaradır (P1)**; `queries.py` 42 %, `objections.resolve_objection`/`delete_row` testsiz |
| **Schedule System** | **80** | Qrup/müəllim/otaq/qismən/tək-cüt toqquşmaları, dublikat, tərs saat, keçmiş semestr, scope (koordinator yalnız öz ixtisası, müəllim 403), soft-delete, tələbə/müəllim görünüşü, ICS — hamısı PASS. Mənfi: dərc statusu yoxdur, `start_date` yoxlanmır, DB səviyyəsində toqquşma məhdudiyyəti yoxdur (F-T7), cross-org HTTP testi yoxdur |
| **Syllabus Workflow** | **91** | Tam zəncir HTTP-də PASS: natamam göndərmə 409, biznes qaydaları server tərəfdən (goal ≥ 60), göndərilmiş/təsdiqlənmiş versiya `version.locked` 403, icazəsiz təsdiq 403/404 (mövcudluq sızmır), səbəbsiz düzəliş 400, tələbə yalnız təsdiqlənmişi görür, yazılmamış tələbə 404, rəy tarixçəsi tam. Mənfi: HTTP zəncir testi repoda yoxdur (yalnız servis), `copy_into_existing` 0 % |
| **Electronic Journal** | **84** | Sahib-yalnız (yad müəllim/tələbə 404), 0–10 tam ədəd, gündəlik pəncərə, dublikat dərs, semestr sonu, RİM bağlama → yazı bloku, sənədli düzəliş (səbəb+qeyd+PDF) + 2 audit sətri, düzəldilmiş xana müəllimə bağlı — PASS. Mənfi: düzəliş qeydi 1 simvol, PDF magic yoxlanmır (F-T8), `journal_sync`/`exam_bridge` 34–50 % (imtahan→jurnal körpüsü zəif örtülüb), tarixə bağlı testlər dondurulmayıb |
| **Student Management** | **73** | Sənədli köçürmə (əmr, tarix, ≥20 simvol), DB trigger çılpaq yazını bloklayır, hərəkət tarixçəsi + audit, kart/akademik qeyd/transkript PDF, intake, xaric etmə → status və qorumalar — PASS. **Mənfi: F-T2 — xaric edilmiş tələbə cari/köhnə qrupa bərpa oluna bilmir (P2)**; intake `birth_date` mesajı (F-T9); `TransactionTestCase` tələb edən (record, txid) unikal açarı çoxaddımlı testləri çətinləşdirir |
