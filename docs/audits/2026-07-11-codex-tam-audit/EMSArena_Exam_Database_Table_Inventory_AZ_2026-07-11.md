# EMSArena imtahan sistemi — database cədvəl və field inventarı

**Snapshot:** `7c538163`  
**Model cədvəlləri:** 35  
**Auto/explicit M2M through cədvəlləri:** 10

## Model cədvəlləri

### `appeals_appeal` — `appeals.Appeal`

| Field | Tip | NULL | Əlaqə hədəfi |
|---|---|---:|---|
| `id` | `BigAutoField` | xeyr | `—` |
| `attempt` | `ForeignKey` | xeyr | `exams.ExamAttempt` |
| `exam` | `ForeignKey` | xeyr | `exams.Exam` |
| `student` | `ForeignKey` | xeyr | `auth.User` |
| `organization` | `ForeignKey` | xeyr | `organizations.Organization` |
| `org_unit` | `ForeignKey` | bəli | `organizations.OrgUnit` |
| `status` | `CharField` | xeyr | `—` |
| `reviewed_by` | `ForeignKey` | bəli | `auth.User` |
| `reviewed_at` | `DateTimeField` | bəli | `—` |
| `reviewer_note` | `TextField` | xeyr | `—` |
| `created_at` | `DateTimeField` | xeyr | `—` |
| `updated_at` | `DateTimeField` | xeyr | `—` |

- Constraint-lər: yoxdur
- Index-lər: `appeal_org_status_idx`, `appeal_exam_status_idx`, `appeal_student_created_idx`

### `appeals_appealitem` — `appeals.AppealItem`

| Field | Tip | NULL | Əlaqə hədəfi |
|---|---|---:|---|
| `id` | `BigAutoField` | xeyr | `—` |
| `appeal` | `ForeignKey` | xeyr | `appeals.Appeal` |
| `question` | `ForeignKey` | xeyr | `exams.ExamQuestion` |
| `answer` | `ForeignKey` | bəli | `exams.ExamAnswer` |
| `appeal_type` | `CharField` | xeyr | `—` |
| `comment` | `TextField` | xeyr | `—` |
| `status` | `CharField` | xeyr | `—` |
| `reviewer_response` | `TextField` | xeyr | `—` |
| `resolved_by` | `ForeignKey` | bəli | `auth.User` |
| `resolved_at` | `DateTimeField` | bəli | `—` |
| `created_at` | `DateTimeField` | xeyr | `—` |
| `updated_at` | `DateTimeField` | xeyr | `—` |

- Constraint-lər: `appeal_item_unique_question`
- Index-lər: `appeal_item_status_idx`

### `appeals_scoreadjustment` — `appeals.ScoreAdjustment`

| Field | Tip | NULL | Əlaqə hədəfi |
|---|---|---:|---|
| `id` | `BigAutoField` | xeyr | `—` |
| `appeal_item` | `OneToOneField` | xeyr | `appeals.AppealItem` |
| `attempt` | `ForeignKey` | xeyr | `exams.ExamAttempt` |
| `question` | `ForeignKey` | bəli | `exams.ExamQuestion` |
| `delta_points` | `DecimalField` | xeyr | `—` |
| `previous_is_correct` | `BooleanField` | bəli | `—` |
| `new_is_correct` | `BooleanField` | bəli | `—` |
| `previous_score` | `DecimalField` | bəli | `—` |
| `new_score` | `DecimalField` | bəli | `—` |
| `previous_answer_score` | `DecimalField` | bəli | `—` |
| `applied_by` | `ForeignKey` | bəli | `auth.User` |
| `applied_at` | `DateTimeField` | xeyr | `—` |
| `reverted` | `BooleanField` | xeyr | `—` |

- Constraint-lər: yoxdur
- Index-lər: `score_adj_attempt_idx`

### `exams_aiconfiguration` — `exams.AIConfiguration`

| Field | Tip | NULL | Əlaqə hədəfi |
|---|---|---:|---|
| `id` | `BigAutoField` | xeyr | `—` |
| `enabled` | `BooleanField` | xeyr | `—` |
| `rate_limit` | `CharField` | xeyr | `—` |
| `summary_model` | `CharField` | xeyr | `—` |
| `grading_model` | `CharField` | xeyr | `—` |
| `assistant_model` | `CharField` | xeyr | `—` |
| `monthly_budget` | `DecimalField` | xeyr | `—` |
| `updated_at` | `DateTimeField` | xeyr | `—` |

- Constraint-lər: yoxdur
- Index-lər: Meta səviyyəsində ayrıca yoxdur

### `exams_bankquestion` — `exams.BankQuestion`

| Field | Tip | NULL | Əlaqə hədəfi |
|---|---|---:|---|
| `id` | `BigAutoField` | xeyr | `—` |
| `bank` | `ForeignKey` | xeyr | `exams.QuestionBank` |
| `text` | `TextField` | xeyr | `—` |
| `question_type` | `CharField` | xeyr | `—` |
| `answer_mode` | `CharField` | xeyr | `—` |
| `correct_answer` | `TextField` | xeyr | `—` |
| `difficulty` | `CharField` | xeyr | `—` |
| `language` | `CharField` | xeyr | `—` |
| `points` | `PositiveIntegerField` | xeyr | `—` |
| `tags` | `JSONField` | xeyr | `—` |
| `explanation` | `TextField` | xeyr | `—` |
| `fingerprint` | `CharField` | xeyr | `—` |
| `image` | `ImageField` | bəli | `—` |
| `video` | `FileField` | bəli | `—` |
| `is_active` | `BooleanField` | xeyr | `—` |
| `created_by` | `ForeignKey` | bəli | `auth.User` |
| `created_at` | `DateTimeField` | xeyr | `—` |
| `updated_at` | `DateTimeField` | xeyr | `—` |

- Constraint-lər: yoxdur
- Index-lər: `bankq_bank_active_idx`, `bankq_bank_lang_idx`, `bankq_bank_diff_idx`

### `exams_bankquestionoption` — `exams.BankQuestionOption`

| Field | Tip | NULL | Əlaqə hədəfi |
|---|---|---:|---|
| `id` | `BigAutoField` | xeyr | `—` |
| `question` | `ForeignKey` | xeyr | `exams.BankQuestion` |
| `label` | `CharField` | bəli | `—` |
| `text` | `TextField` | xeyr | `—` |
| `image` | `ImageField` | bəli | `—` |
| `is_correct` | `BooleanField` | xeyr | `—` |

- Constraint-lər: yoxdur
- Index-lər: Meta səviyyəsində ayrıca yoxdur

### `exams_codingexamquestion` — `exams.CodingExamQuestion`

| Field | Tip | NULL | Əlaqə hədəfi |
|---|---|---:|---|
| `id` | `BigAutoField` | xeyr | `—` |
| `question` | `OneToOneField` | xeyr | `exams.ExamQuestion` |
| `language` | `CharField` | xeyr | `—` |
| `title` | `CharField` | xeyr | `—` |
| `problem_statement` | `TextField` | xeyr | `—` |
| `input_description` | `TextField` | xeyr | `—` |
| `output_description` | `TextField` | xeyr | `—` |
| `example_input` | `TextField` | xeyr | `—` |
| `example_output` | `TextField` | xeyr | `—` |
| `time_limit_seconds` | `PositiveIntegerField` | xeyr | `—` |
| `memory_limit_mb` | `PositiveIntegerField` | xeyr | `—` |
| `max_score` | `PositiveIntegerField` | xeyr | `—` |
| `starter_code` | `TextField` | xeyr | `—` |
| `allow_file_creation` | `BooleanField` | xeyr | `—` |
| `allow_multiple_files` | `BooleanField` | xeyr | `—` |
| `enable_code_execution` | `BooleanField` | xeyr | `—` |
| `created_at` | `DateTimeField` | xeyr | `—` |
| `updated_at` | `DateTimeField` | xeyr | `—` |

- Constraint-lər: yoxdur
- Index-lər: Meta səviyyəsində ayrıca yoxdur

### `exams_codingfile` — `exams.CodingFile`

| Field | Tip | NULL | Əlaqə hədəfi |
|---|---|---:|---|
| `id` | `BigAutoField` | xeyr | `—` |
| `submission` | `ForeignKey` | xeyr | `exams.CodingSubmission` |
| `name` | `CharField` | xeyr | `—` |
| `content` | `TextField` | xeyr | `—` |
| `language` | `CharField` | xeyr | `—` |
| `is_main` | `BooleanField` | xeyr | `—` |
| `created_at` | `DateTimeField` | xeyr | `—` |
| `updated_at` | `DateTimeField` | xeyr | `—` |

- Constraint-lər: yoxdur
- Index-lər: Meta səviyyəsində ayrıca yoxdur

### `exams_codingsubmission` — `exams.CodingSubmission`

| Field | Tip | NULL | Əlaqə hədəfi |
|---|---|---:|---|
| `id` | `BigAutoField` | xeyr | `—` |
| `student` | `ForeignKey` | xeyr | `auth.User` |
| `exam` | `ForeignKey` | xeyr | `exams.Exam` |
| `attempt` | `ForeignKey` | bəli | `exams.ExamAttempt` |
| `question` | `ForeignKey` | xeyr | `exams.CodingExamQuestion` |
| `selected_language` | `CharField` | xeyr | `—` |
| `submitted_code` | `TextField` | xeyr | `—` |
| `files` | `JSONField` | xeyr | `—` |
| `output` | `TextField` | xeyr | `—` |
| `error_message` | `TextField` | xeyr | `—` |
| `execution_status` | `CharField` | xeyr | `—` |
| `score` | `DecimalField` | bəli | `—` |
| `test_results` | `JSONField` | xeyr | `—` |
| `execution_time_ms` | `PositiveIntegerField` | bəli | `—` |
| `memory_usage_kb` | `PositiveIntegerField` | bəli | `—` |
| `is_final` | `BooleanField` | xeyr | `—` |
| `submitted_at` | `DateTimeField` | xeyr | `—` |
| `updated_at` | `DateTimeField` | xeyr | `—` |

- Constraint-lər: yoxdur
- Index-lər: `exams_codin_student_2a03b5_idx`, `exams_codin_attempt_ba27be_idx`, `exams_codin_executi_9bb611_idx`

### `exams_codingtestcase` — `exams.CodingTestCase`

| Field | Tip | NULL | Əlaqə hədəfi |
|---|---|---:|---|
| `id` | `BigAutoField` | xeyr | `—` |
| `coding_question` | `ForeignKey` | xeyr | `exams.CodingExamQuestion` |
| `input_data` | `TextField` | xeyr | `—` |
| `expected_output` | `TextField` | xeyr | `—` |
| `visibility` | `CharField` | xeyr | `—` |
| `point_value` | `PositiveIntegerField` | xeyr | `—` |
| `order` | `PositiveIntegerField` | xeyr | `—` |
| `created_at` | `DateTimeField` | xeyr | `—` |

- Constraint-lər: yoxdur
- Index-lər: `exams_codin_coding__d6c308_idx`

### `exams_exam` — `exams.Exam`

| Field | Tip | NULL | Əlaqə hədəfi |
|---|---|---:|---|
| `id` | `BigAutoField` | xeyr | `—` |
| `author` | `ForeignKey` | xeyr | `auth.User` |
| `title` | `CharField` | xeyr | `—` |
| `description` | `TextField` | xeyr | `—` |
| `exam_type` | `CharField` | xeyr | `—` |
| `start_datetime` | `DateTimeField` | bəli | `—` |
| `end_datetime` | `DateTimeField` | bəli | `—` |
| `is_active` | `BooleanField` | xeyr | `—` |
| `results_hidden_from_students` | `BooleanField` | xeyr | `—` |
| `total_duration_minutes` | `PositiveIntegerField` | bəli | `—` |
| `default_question_time_seconds` | `PositiveIntegerField` | bəli | `—` |
| `max_attempts_per_user` | `PositiveIntegerField` | bəli | `—` |
| `random_question_count` | `PositiveIntegerField` | xeyr | `—` |
| `fair_question_distribution_enabled` | `BooleanField` | xeyr | `—` |
| `ai_difficulty_balance_enabled` | `BooleanField` | xeyr | `—` |
| `default_question_points` | `PositiveIntegerField` | xeyr | `—` |
| `course` | `ForeignKey` | bəli | `courses.Course` |
| `subject` | `ForeignKey` | bəli | `registrar.Subject` |
| `organization` | `ForeignKey` | xeyr | `organizations.Organization` |
| `exam_type_extended` | `CharField` | bəli | `—` |
| `mode` | `CharField` | xeyr | `—` |
| `proctoring_level` | `CharField` | xeyr | `—` |
| `settings` | `JSONField` | xeyr | `—` |
| `is_public` | `BooleanField` | xeyr | `—` |
| `access_code` | `CharField` | xeyr | `—` |
| `slug` | `SlugField` | xeyr | `—` |
| `created_at` | `DateTimeField` | xeyr | `—` |
| `enable_paint` | `BooleanField` | xeyr | `—` |
| `is_archived` | `BooleanField` | xeyr | `—` |
| `archived_at` | `DateTimeField` | bəli | `—` |
| `is_deleted` | `BooleanField` | xeyr | `—` |
| `deleted_at` | `DateTimeField` | bəli | `—` |
| `allowed_users` | `ManyToManyField` | xeyr | `auth.User` |
| `excluded_users` | `ManyToManyField` | xeyr | `auth.User` |
| `allowed_groups` | `ManyToManyField` | xeyr | `exams.StudentGroup` |

- Constraint-lər: yoxdur
- Index-lər: `exam_org_active_created_idx`, `exam_org_type_created_idx`, `exam_course_created_idx`, `exam_author_created_idx`, `exam_author_archived_idx`

### `exams_examanswer` — `exams.ExamAnswer`

| Field | Tip | NULL | Əlaqə hədəfi |
|---|---|---:|---|
| `id` | `BigAutoField` | xeyr | `—` |
| `attempt` | `ForeignKey` | xeyr | `exams.ExamAttempt` |
| `question` | `ForeignKey` | xeyr | `exams.ExamQuestion` |
| `text_answer` | `TextField` | xeyr | `—` |
| `is_correct` | `BooleanField` | xeyr | `—` |
| `teacher_score` | `PositiveIntegerField` | bəli | `—` |
| `teacher_feedback` | `TextField` | xeyr | `—` |
| `updated_at` | `DateTimeField` | xeyr | `—` |
| `has_paint` | `BooleanField` | xeyr | `—` |
| `paint_image` | `ImageField` | bəli | `—` |
| `paint_updated_at` | `DateTimeField` | bəli | `—` |
| `paint_data_url` | `TextField` | bəli | `—` |
| `question_snapshot` | `JSONField` | xeyr | `—` |
| `selected_options` | `ManyToManyField` | xeyr | `exams.ExamQuestionOption` |

- Constraint-lər: yoxdur
- Index-lər: Meta səviyyəsində ayrıca yoxdur

### `exams_examanswerfile` — `exams.ExamAnswerFile`

| Field | Tip | NULL | Əlaqə hədəfi |
|---|---|---:|---|
| `id` | `BigAutoField` | xeyr | `—` |
| `answer` | `ForeignKey` | xeyr | `exams.ExamAnswer` |
| `file` | `FileField` | xeyr | `—` |
| `uploaded_at` | `DateTimeField` | xeyr | `—` |

- Constraint-lər: yoxdur
- Index-lər: Meta səviyyəsində ayrıca yoxdur

### `exams_examattempt` — `exams.ExamAttempt`

| Field | Tip | NULL | Əlaqə hədəfi |
|---|---|---:|---|
| `id` | `BigAutoField` | xeyr | `—` |
| `checked_by_teacher` | `BooleanField` | xeyr | `—` |
| `teacher_checked_at` | `DateTimeField` | bəli | `—` |
| `user` | `ForeignKey` | xeyr | `auth.User` |
| `exam` | `ForeignKey` | xeyr | `exams.Exam` |
| `language` | `CharField` | bəli | `—` |
| `language_variant` | `ForeignKey` | bəli | `exams.ExamLanguageVariant` |
| `attempt_number` | `PositiveIntegerField` | xeyr | `—` |
| `is_trial` | `BooleanField` | xeyr | `—` |
| `room` | `ForeignKey` | bəli | `exams.ExamRoom` |
| `room_computer` | `ForeignKey` | bəli | `exams.ExamRoomComputer` |
| `marked_question_ids` | `JSONField` | xeyr | `—` |
| `status` | `CharField` | xeyr | `—` |
| `started_at` | `DateTimeField` | xeyr | `—` |
| `finished_at` | `DateTimeField` | bəli | `—` |
| `duration_seconds` | `PositiveIntegerField` | bəli | `—` |
| `correct_count` | `PositiveIntegerField` | xeyr | `—` |
| `wrong_count` | `PositiveIntegerField` | xeyr | `—` |
| `teacher_score` | `PositiveIntegerField` | bəli | `—` |
| `teacher_feedback` | `TextField` | xeyr | `—` |
| `supervision_status` | `CharField` | xeyr | `—` |
| `supervision_violation_count` | `PositiveIntegerField` | xeyr | `—` |
| `supervision_extra_chances` | `PositiveIntegerField` | xeyr | `—` |
| `supervision_resumed_at` | `DateTimeField` | bəli | `—` |
| `supervision_locked_at` | `DateTimeField` | bəli | `—` |
| `supervision_manual_lock` | `BooleanField` | xeyr | `—` |

- Constraint-lər: `uniq_active_attempt_per_user_exam`, `uniq_attempt_number_per_user_exam`
- Index-lər: `exams_exama_user_id_6ce609_idx`, `exams_exama_user_id_bf4f2e_idx`

### `exams_examlanguagevariant` — `exams.ExamLanguageVariant`

| Field | Tip | NULL | Əlaqə hədəfi |
|---|---|---:|---|
| `id` | `BigAutoField` | xeyr | `—` |
| `exam` | `ForeignKey` | xeyr | `exams.Exam` |
| `language` | `CharField` | xeyr | `—` |
| `display_name` | `CharField` | xeyr | `—` |
| `is_active` | `BooleanField` | xeyr | `—` |
| `question_count_override` | `PositiveIntegerField` | bəli | `—` |
| `created_at` | `DateTimeField` | xeyr | `—` |
| `updated_at` | `DateTimeField` | xeyr | `—` |

- Constraint-lər: `exam_language_variant_unique`
- Index-lər: `exam_lang_variant_active_idx`

### `exams_examquestion` — `exams.ExamQuestion`

| Field | Tip | NULL | Əlaqə hədəfi |
|---|---|---:|---|
| `id` | `BigAutoField` | xeyr | `—` |
| `points` | `PositiveIntegerField` | xeyr | `—` |
| `fingerprint` | `CharField` | xeyr | `—` |
| `exam` | `ForeignKey` | xeyr | `exams.Exam` |
| `block` | `ForeignKey` | bəli | `exams.QuestionBlock` |
| `bank` | `ForeignKey` | bəli | `exams.QuestionBank` |
| `source_bank_question` | `ForeignKey` | bəli | `exams.BankQuestion` |
| `language` | `CharField` | xeyr | `—` |
| `language_variant` | `ForeignKey` | bəli | `exams.ExamLanguageVariant` |
| `difficulty` | `CharField` | xeyr | `—` |
| `difficulty_source` | `CharField` | xeyr | `—` |
| `difficulty_checked_at` | `DateTimeField` | bəli | `—` |
| `tags` | `JSONField` | xeyr | `—` |
| `explanation` | `TextField` | xeyr | `—` |
| `usage_count` | `PositiveIntegerField` | xeyr | `—` |
| `text` | `TextField` | xeyr | `—` |
| `correct_answer` | `TextField` | xeyr | `—` |
| `order` | `PositiveIntegerField` | xeyr | `—` |
| `answer_mode` | `CharField` | xeyr | `—` |
| `time_limit_seconds` | `PositiveIntegerField` | bəli | `—` |
| `image` | `ImageField` | bəli | `—` |
| `video` | `FileField` | bəli | `—` |
| `enable_paint` | `BooleanField` | xeyr | `—` |
| `disable_paint` | `BooleanField` | xeyr | `—` |
| `is_active` | `BooleanField` | xeyr | `—` |
| `created_at` | `DateTimeField` | xeyr | `—` |

- Constraint-lər: yoxdur
- Index-lər: Meta səviyyəsində ayrıca yoxdur

### `exams_examquestionoption` — `exams.ExamQuestionOption`

| Field | Tip | NULL | Əlaqə hədəfi |
|---|---|---:|---|
| `id` | `BigAutoField` | xeyr | `—` |
| `label` | `CharField` | bəli | `—` |
| `question` | `ForeignKey` | xeyr | `exams.ExamQuestion` |
| `text` | `TextField` | xeyr | `—` |
| `image` | `ImageField` | bəli | `—` |
| `is_correct` | `BooleanField` | xeyr | `—` |

- Constraint-lər: yoxdur
- Index-lər: Meta səviyyəsində ayrıca yoxdur

### `exams_examroom` — `exams.ExamRoom`

| Field | Tip | NULL | Əlaqə hədəfi |
|---|---|---:|---|
| `id` | `BigAutoField` | xeyr | `—` |
| `organization` | `ForeignKey` | xeyr | `organizations.Organization` |
| `name` | `CharField` | xeyr | `—` |
| `code` | `CharField` | xeyr | `—` |
| `building` | `CharField` | xeyr | `—` |
| `floor` | `CharField` | xeyr | `—` |
| `capacity` | `PositiveIntegerField` | xeyr | `—` |
| `computer_count` | `PositiveIntegerField` | xeyr | `—` |
| `notes` | `TextField` | xeyr | `—` |
| `is_active` | `BooleanField` | xeyr | `—` |
| `created_by` | `ForeignKey` | bəli | `auth.User` |
| `created_at` | `DateTimeField` | xeyr | `—` |
| `updated_at` | `DateTimeField` | xeyr | `—` |
| `invigilators` | `ManyToManyField` | xeyr | `auth.User` |

- Constraint-lər: `uniq_exam_room_code_per_org`
- Index-lər: `examroom_org_active_name_idx`

### `exams_examroomcomputer` — `exams.ExamRoomComputer`

| Field | Tip | NULL | Əlaqə hədəfi |
|---|---|---:|---|
| `id` | `BigAutoField` | xeyr | `—` |
| `organization` | `ForeignKey` | xeyr | `organizations.Organization` |
| `room` | `ForeignKey` | xeyr | `exams.ExamRoom` |
| `label` | `CharField` | xeyr | `—` |
| `seat_number` | `PositiveIntegerField` | bəli | `—` |
| `mac_address` | `CharField` | xeyr | `—` |
| `ip_address` | `GenericIPAddressField` | bəli | `—` |
| `is_active` | `BooleanField` | xeyr | `—` |
| `notes` | `CharField` | xeyr | `—` |
| `created_by` | `ForeignKey` | bəli | `auth.User` |
| `created_at` | `DateTimeField` | xeyr | `—` |
| `updated_at` | `DateTimeField` | xeyr | `—` |

- Constraint-lər: `uniq_room_computer_mac`, `uniq_room_computer_label`, `uniq_room_computer_seat`
- Index-lər: `roomcomp_room_active_idx`

### `exams_examroomsession` — `exams.ExamRoomSession`

| Field | Tip | NULL | Əlaqə hədəfi |
|---|---|---:|---|
| `id` | `BigAutoField` | xeyr | `—` |
| `organization` | `ForeignKey` | xeyr | `organizations.Organization` |
| `room` | `ForeignKey` | xeyr | `exams.ExamRoom` |
| `invigilator` | `ForeignKey` | bəli | `auth.User` |
| `scheduled_start` | `DateTimeField` | xeyr | `—` |
| `scheduled_end` | `DateTimeField` | xeyr | `—` |
| `state` | `CharField` | xeyr | `—` |
| `entry_opened_at` | `DateTimeField` | bəli | `—` |
| `started_at` | `DateTimeField` | bəli | `—` |
| `started_by` | `ForeignKey` | bəli | `auth.User` |
| `start_connected_count` | `PositiveIntegerField` | xeyr | `—` |
| `ended_at` | `DateTimeField` | bəli | `—` |
| `ended_by` | `ForeignKey` | bəli | `auth.User` |
| `notes` | `TextField` | xeyr | `—` |
| `created_by` | `ForeignKey` | bəli | `auth.User` |
| `created_at` | `DateTimeField` | xeyr | `—` |
| `updated_at` | `DateTimeField` | xeyr | `—` |
| `staff` | `ManyToManyField` | xeyr | `auth.User` |

- Constraint-lər: `room_session_end_after_start`
- Index-lər: `roomsess_org_state_sched_idx`, `roomsess_room_sched_idx`, `roomsess_invig_state_idx`

### `exams_examstudentpin` — `exams.ExamStudentPin`

| Field | Tip | NULL | Əlaqə hədəfi |
|---|---|---:|---|
| `id` | `BigAutoField` | xeyr | `—` |
| `exam` | `ForeignKey` | xeyr | `exams.Exam` |
| `student` | `ForeignKey` | xeyr | `auth.User` |
| `pin_hash` | `CharField` | xeyr | `—` |
| `pin_cipher` | `TextField` | xeyr | `—` |
| `created_at` | `DateTimeField` | xeyr | `—` |
| `updated_at` | `DateTimeField` | xeyr | `—` |

- Constraint-lər: `uniq_exam_student_pin`
- Index-lər: `exam_student_pin_idx`

### `exams_examsupervisionconfig` — `exams.ExamSupervisionConfig`

| Field | Tip | NULL | Əlaqə hədəfi |
|---|---|---:|---|
| `id` | `BigAutoField` | xeyr | `—` |
| `exam` | `OneToOneField` | xeyr | `exams.Exam` |
| `enabled` | `BooleanField` | xeyr | `—` |
| `template` | `CharField` | xeyr | `—` |
| `force_fullscreen` | `BooleanField` | xeyr | `—` |
| `grace_period_seconds` | `PositiveIntegerField` | xeyr | `—` |
| `resume_window_seconds` | `PositiveIntegerField` | xeyr | `—` |
| `max_fullscreen_violations` | `PositiveIntegerField` | xeyr | `—` |
| `detect_tab_switch` | `BooleanField` | xeyr | `—` |
| `block_copy_paste` | `BooleanField` | xeyr | `—` |
| `disable_right_click` | `BooleanField` | xeyr | `—` |
| `disable_text_selection` | `BooleanField` | xeyr | `—` |
| `restrict_keyboard_shortcuts` | `BooleanField` | xeyr | `—` |
| `violation_action` | `CharField` | xeyr | `—` |
| `recovery_policy` | `CharField` | xeyr | `—` |
| `created_at` | `DateTimeField` | xeyr | `—` |
| `updated_at` | `DateTimeField` | xeyr | `—` |

- Constraint-lər: yoxdur
- Index-lər: Meta səviyyəsində ayrıca yoxdur

### `exams_finalexamticket` — `exams.FinalExamTicket`

| Field | Tip | NULL | Əlaqə hədəfi |
|---|---|---:|---|
| `id` | `BigAutoField` | xeyr | `—` |
| `organization` | `ForeignKey` | xeyr | `organizations.Organization` |
| `exam` | `ForeignKey` | xeyr | `exams.Exam` |
| `session` | `ForeignKey` | bəli | `exams.ExamRoomSession` |
| `student` | `ForeignKey` | xeyr | `auth.User` |
| `attempt` | `ForeignKey` | bəli | `exams.ExamAttempt` |
| `seat_number` | `PositiveIntegerField` | bəli | `—` |
| `language` | `CharField` | xeyr | `—` |
| `status` | `CharField` | xeyr | `—` |
| `pin_hash` | `CharField` | xeyr | `—` |
| `pin_cipher` | `TextField` | xeyr | `—` |
| `pin_issued_at` | `DateTimeField` | bəli | `—` |
| `pin_expires_at` | `DateTimeField` | bəli | `—` |
| `pin_revoked_at` | `DateTimeField` | bəli | `—` |
| `pin_failed_attempts` | `PositiveIntegerField` | xeyr | `—` |
| `pin_locked_until` | `DateTimeField` | bəli | `—` |
| `pin_generated_by` | `ForeignKey` | bəli | `auth.User` |
| `reminder_stage` | `PositiveSmallIntegerField` | xeyr | `—` |
| `entry_validated_at` | `DateTimeField` | bəli | `—` |
| `rules_accepted_at` | `DateTimeField` | bəli | `—` |
| `waiting_since` | `DateTimeField` | bəli | `—` |
| `ready_at` | `DateTimeField` | bəli | `—` |
| `started_at` | `DateTimeField` | bəli | `—` |
| `completed_at` | `DateTimeField` | bəli | `—` |
| `removed_at` | `DateTimeField` | bəli | `—` |
| `removed_by` | `ForeignKey` | bəli | `auth.User` |
| `removal_action` | `CharField` | xeyr | `—` |
| `removal_reason` | `TextField` | xeyr | `—` |
| `reconnect_count` | `PositiveIntegerField` | xeyr | `—` |
| `last_seen_at` | `DateTimeField` | bəli | `—` |
| `created_at` | `DateTimeField` | xeyr | `—` |
| `updated_at` | `DateTimeField` | xeyr | `—` |

- Constraint-lər: `uniq_ticket_per_exam_student`, `uniq_seat_per_session`
- Index-lər: `finticket_session_status_idx`, `finticket_student_status_idx`, `finticket_org_created_idx`

### `exams_proctoringlog` — `exams.ProctoringLog`

| Field | Tip | NULL | Əlaqə hədəfi |
|---|---|---:|---|
| `id` | `BigAutoField` | xeyr | `—` |
| `exam_attempt` | `ForeignKey` | xeyr | `exams.ExamAttempt` |
| `event_type` | `CharField` | xeyr | `—` |
| `timestamp` | `DateTimeField` | xeyr | `—` |
| `details` | `JSONField` | xeyr | `—` |

- Constraint-lər: yoxdur
- Index-lər: `exams_proct_exam_at_76f1af_idx`, `exams_proct_event_t_d8a785_idx`

### `exams_questionbank` — `exams.QuestionBank`

| Field | Tip | NULL | Əlaqə hədəfi |
|---|---|---:|---|
| `id` | `BigAutoField` | xeyr | `—` |
| `name` | `CharField` | xeyr | `—` |
| `description` | `TextField` | xeyr | `—` |
| `subject` | `CharField` | xeyr | `—` |
| `topic` | `CharField` | xeyr | `—` |
| `language` | `CharField` | xeyr | `—` |
| `default_question_type` | `CharField` | xeyr | `—` |
| `organization` | `ForeignKey` | bəli | `organizations.Organization` |
| `org_unit` | `ForeignKey` | bəli | `organizations.OrgUnit` |
| `organization_type` | `CharField` | xeyr | `—` |
| `is_shared` | `BooleanField` | xeyr | `—` |
| `is_active` | `BooleanField` | xeyr | `—` |
| `created_by` | `ForeignKey` | xeyr | `auth.User` |
| `created_at` | `DateTimeField` | xeyr | `—` |
| `updated_at` | `DateTimeField` | xeyr | `—` |

- Constraint-lər: yoxdur
- Index-lər: `exams_quest_created_b2b8da_idx`, `exams_quest_is_acti_1cb61b_idx`

### `exams_questionblock` — `exams.QuestionBlock`

| Field | Tip | NULL | Əlaqə hədəfi |
|---|---|---:|---|
| `id` | `BigAutoField` | xeyr | `—` |
| `exam` | `ForeignKey` | xeyr | `exams.Exam` |
| `name` | `CharField` | xeyr | `—` |
| `order` | `PositiveIntegerField` | xeyr | `—` |
| `time_limit_minutes` | `PositiveIntegerField` | bəli | `—` |
| `enable_paint` | `BooleanField` | bəli | `—` |

- Constraint-lər: yoxdur
- Index-lər: Meta səviyyəsində ayrıca yoxdur

### `exams_questionsubmission` — `exams.QuestionSubmission`

| Field | Tip | NULL | Əlaqə hədəfi |
|---|---|---:|---|
| `id` | `BigAutoField` | xeyr | `—` |
| `organization` | `ForeignKey` | xeyr | `organizations.Organization` |
| `teacher` | `ForeignKey` | xeyr | `auth.User` |
| `title` | `CharField` | xeyr | `—` |
| `subject` | `CharField` | xeyr | `—` |
| `student_group` | `ForeignKey` | bəli | `exams.StudentGroup` |
| `group_label` | `CharField` | xeyr | `—` |
| `language` | `CharField` | xeyr | `—` |
| `raw_text` | `TextField` | xeyr | `—` |
| `teacher_note` | `TextField` | xeyr | `—` |
| `parsed_snapshot` | `JSONField` | xeyr | `—` |
| `question_count` | `PositiveIntegerField` | xeyr | `—` |
| `error_count` | `PositiveIntegerField` | xeyr | `—` |
| `warning_count` | `PositiveIntegerField` | xeyr | `—` |
| `status` | `CharField` | xeyr | `—` |
| `resubmission_count` | `PositiveIntegerField` | xeyr | `—` |
| `reviewer` | `ForeignKey` | bəli | `auth.User` |
| `reviewed_at` | `DateTimeField` | bəli | `—` |
| `reviewer_note` | `TextField` | xeyr | `—` |
| `accepted_bank` | `ForeignKey` | bəli | `exams.QuestionBank` |
| `created_at` | `DateTimeField` | xeyr | `—` |
| `updated_at` | `DateTimeField` | xeyr | `—` |
| `student_groups` | `ManyToManyField` | xeyr | `exams.StudentGroup` |

- Constraint-lər: yoxdur
- Index-lər: `qsub_org_status_idx`, `qsub_teacher_created_idx`

### `exams_studentexamattemptgrant` — `exams.StudentExamAttemptGrant`

| Field | Tip | NULL | Əlaqə hədəfi |
|---|---|---:|---|
| `id` | `BigAutoField` | xeyr | `—` |
| `exam` | `ForeignKey` | xeyr | `exams.Exam` |
| `student` | `ForeignKey` | xeyr | `auth.User` |
| `extra_attempts` | `PositiveIntegerField` | xeyr | `—` |
| `granted_by` | `ForeignKey` | bəli | `auth.User` |
| `created_at` | `DateTimeField` | xeyr | `—` |
| `updated_at` | `DateTimeField` | xeyr | `—` |

- Constraint-lər: `uniq_exam_student_attempt_grant`
- Index-lər: Meta səviyyəsində ayrıca yoxdur

### `exams_studentgroup` — `exams.StudentGroup`

| Field | Tip | NULL | Əlaqə hədəfi |
|---|---|---:|---|
| `id` | `BigAutoField` | xeyr | `—` |
| `teacher` | `ForeignKey` | xeyr | `auth.User` |
| `organization` | `ForeignKey` | bəli | `organizations.Organization` |
| `name` | `CharField` | xeyr | `—` |
| `org_unit` | `ForeignKey` | bəli | `organizations.OrgUnit` |
| `created_at` | `DateTimeField` | xeyr | `—` |
| `students` | `ManyToManyField` | xeyr | `auth.User` |
| `teachers` | `ManyToManyField` | xeyr | `auth.User` |
| `subjects` | `ManyToManyField` | xeyr | `registrar.Subject` |

- Constraint-lər: yoxdur
- Index-lər: Meta səviyyəsində ayrıca yoxdur

### `exams_supervisionincident` — `exams.SupervisionIncident`

| Field | Tip | NULL | Əlaqə hədəfi |
|---|---|---:|---|
| `id` | `BigAutoField` | xeyr | `—` |
| `organization` | `ForeignKey` | xeyr | `organizations.Organization` |
| `exam` | `ForeignKey` | xeyr | `exams.Exam` |
| `attempt` | `ForeignKey` | xeyr | `exams.ExamAttempt` |
| `student` | `ForeignKey` | xeyr | `auth.User` |
| `event_type` | `CharField` | xeyr | `—` |
| `severity` | `CharField` | xeyr | `—` |
| `timestamp` | `DateTimeField` | xeyr | `—` |
| `metadata` | `JSONField` | xeyr | `—` |
| `violation_count_at_time` | `PositiveIntegerField` | xeyr | `—` |
| `teacher_action` | `CharField` | xeyr | `—` |

- Constraint-lər: yoxdur
- Index-lər: `exams_super_attempt_6c8795_idx`, `exams_super_organiz_413f14_idx`, `exams_super_exam_id_b3121a_idx`, `exams_super_student_34affa_idx`, `exams_super_event_t_f8c193_idx`, `exams_super_severit_e94589_idx`

### `exams_textextractionjob` — `exams.TextExtractionJob`

| Field | Tip | NULL | Əlaqə hədəfi |
|---|---|---:|---|
| `id` | `UUIDField` | xeyr | `—` |
| `organization` | `ForeignKey` | bəli | `organizations.Organization` |
| `user` | `ForeignKey` | xeyr | `auth.User` |
| `kind` | `CharField` | xeyr | `—` |
| `payload` | `JSONField` | xeyr | `—` |
| `result_meta` | `JSONField` | xeyr | `—` |
| `source_name` | `CharField` | xeyr | `—` |
| `file` | `FileField` | bəli | `—` |
| `result_file` | `FileField` | bəli | `—` |
| `status` | `CharField` | xeyr | `—` |
| `text` | `TextField` | xeyr | `—` |
| `error` | `TextField` | xeyr | `—` |
| `created_at` | `DateTimeField` | xeyr | `—` |
| `started_at` | `DateTimeField` | bəli | `—` |
| `finished_at` | `DateTimeField` | bəli | `—` |

- Constraint-lər: yoxdur
- Index-lər: `exams_extjob_user_created`

### `live_exam_liveanswer` — `live_exam.LiveAnswer`

| Field | Tip | NULL | Əlaqə hədəfi |
|---|---|---:|---|
| `id` | `BigAutoField` | xeyr | `—` |
| `session` | `ForeignKey` | xeyr | `live_exam.LiveSession` |
| `player` | `ForeignKey` | xeyr | `live_exam.LivePlayer` |
| `question_id` | `IntegerField` | xeyr | `—` |
| `choice_id` | `IntegerField` | bəli | `—` |
| `choice_ids` | `JSONField` | xeyr | `—` |
| `is_correct` | `BooleanField` | xeyr | `—` |
| `answer_ms` | `IntegerField` | xeyr | `—` |
| `awarded_points` | `IntegerField` | xeyr | `—` |
| `created_at` | `DateTimeField` | xeyr | `—` |

- Constraint-lər: `uniq_answer_per_player_question`
- Index-lər: `liveans_session_question_idx`

### `live_exam_liveplayer` — `live_exam.LivePlayer`

| Field | Tip | NULL | Əlaqə hədəfi |
|---|---|---:|---|
| `id` | `BigAutoField` | xeyr | `—` |
| `session` | `ForeignKey` | xeyr | `live_exam.LiveSession` |
| `nickname` | `CharField` | xeyr | `—` |
| `avatar_key` | `CharField` | xeyr | `—` |
| `accessory_key` | `CharField` | xeyr | `—` |
| `client_id` | `CharField` | xeyr | `—` |
| `score` | `IntegerField` | xeyr | `—` |
| `streak` | `PositiveIntegerField` | xeyr | `—` |
| `is_connected` | `BooleanField` | xeyr | `—` |
| `last_seen` | `DateTimeField` | xeyr | `—` |
| `created_at` | `DateTimeField` | xeyr | `—` |

- Constraint-lər: `uniq_player_per_session_client`
- Index-lər: Meta səviyyəsində ayrıca yoxdur

### `live_exam_livesession` — `live_exam.LiveSession`

| Field | Tip | NULL | Əlaqə hədəfi |
|---|---|---:|---|
| `id` | `BigAutoField` | xeyr | `—` |
| `exam` | `ForeignKey` | xeyr | `exams.Exam` |
| `host_user` | `ForeignKey` | xeyr | `auth.User` |
| `pin` | `CharField` | xeyr | `—` |
| `state` | `CharField` | xeyr | `—` |
| `is_locked` | `BooleanField` | xeyr | `—` |
| `current_index` | `PositiveIntegerField` | xeyr | `—` |
| `question_started_at` | `DateTimeField` | bəli | `—` |
| `question_ends_at` | `DateTimeField` | bəli | `—` |
| `created_at` | `DateTimeField` | xeyr | `—` |
| `current_question_id` | `IntegerField` | bəli | `—` |
| `question_seconds` | `PositiveIntegerField` | xeyr | `—` |
| `question_limit` | `PositiveIntegerField` | xeyr | `—` |
| `selected_question_ids` | `JSONField` | xeyr | `—` |
| `host_settings` | `JSONField` | xeyr | `—` |

- Constraint-lər: yoxdur
- Index-lər: Meta səviyyəsində ayrıca yoxdur

### `trial_exams_trialexamrequest` — `trial_exams.TrialExamRequest`

| Field | Tip | NULL | Əlaqə hədəfi |
|---|---|---:|---|
| `id` | `BigAutoField` | xeyr | `—` |
| `user` | `ForeignKey` | bəli | `auth.User` |
| `full_name` | `CharField` | xeyr | `—` |
| `email` | `EmailField` | xeyr | `—` |
| `subject_name` | `CharField` | xeyr | `—` |
| `note` | `TextField` | xeyr | `—` |
| `questions_file` | `FileField` | xeyr | `—` |
| `original_filename` | `CharField` | xeyr | `—` |
| `status` | `CharField` | xeyr | `—` |
| `ip_address` | `GenericIPAddressField` | bəli | `—` |
| `user_agent` | `CharField` | xeyr | `—` |
| `is_handled` | `BooleanField` | xeyr | `—` |
| `created_at` | `DateTimeField` | xeyr | `—` |
| `handled_at` | `DateTimeField` | bəli | `—` |
| `reply_body` | `TextField` | xeyr | `—` |
| `reply_from` | `CharField` | xeyr | `—` |
| `reply_delivery_status` | `CharField` | xeyr | `—` |
| `reply_delivery_error` | `CharField` | xeyr | `—` |
| `reply_sent_at` | `DateTimeField` | bəli | `—` |
| `reply_sent_by` | `ForeignKey` | bəli | `auth.User` |

- Constraint-lər: yoxdur
- Index-lər: `trial_exams_created_6f7f34_idx`, `trial_exams_status_0806d1_idx`, `trial_exams_is_hand_263044_idx`

## M2M through cədvəlləri

| Cədvəl | Mənbə model.field | Hədəf model | Auto-created |
|---|---|---|---:|
| `exams_exam_allowed_groups` | `exams.Exam.allowed_groups` | `exams.StudentGroup` | bəli |
| `exams_exam_allowed_users` | `exams.Exam.allowed_users` | `auth.User` | bəli |
| `exams_exam_excluded_users` | `exams.Exam.excluded_users` | `auth.User` | bəli |
| `exams_examanswer_selected_options` | `exams.ExamAnswer.selected_options` | `exams.ExamQuestionOption` | bəli |
| `exams_examroom_invigilators` | `exams.ExamRoom.invigilators` | `auth.User` | bəli |
| `exams_examroomsession_staff` | `exams.ExamRoomSession.staff` | `auth.User` | bəli |
| `exams_questionsubmission_student_groups` | `exams.QuestionSubmission.student_groups` | `exams.StudentGroup` | bəli |
| `exams_studentgroup_students` | `exams.StudentGroup.students` | `auth.User` | bəli |
| `exams_studentgroup_subjects` | `exams.StudentGroup.subjects` | `registrar.Subject` | bəli |
| `exams_studentgroup_teachers` | `exams.StudentGroup.teachers` | `auth.User` | bəli |
