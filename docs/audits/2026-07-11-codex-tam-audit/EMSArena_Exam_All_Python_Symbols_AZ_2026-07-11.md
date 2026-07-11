# EMSArena imtahan sistemi — bütün Python class/function simvolları

**Snapshot:** `7c538163`  
**Audit tarixi:** 2026-07-11  
**Simvol sayı:** 2913

Bu mexaniki indeks `apps/exams`, `apps/appeals`, `apps/live_exam` və `apps/trial_exams` daxilindəki bütün `.py` fayllarında module-level, class method və nested `class`/`def`/`async def` deklarasiyalarını source sətri ilə göstərir. Deklarasiyalar kod identifikatoru olduğuna görə olduğu kimi saxlanılıb; davranış qiymətləndirməsi əsas audit və matris hesabatındadır.

| Fayl | Sətir | Deklarasiya |
|---|---:|---|
| `apps/appeals/apps.py` | 4 | `class AppealsConfig(AppConfig):` |
| `apps/appeals/apps.py` | 8 | `def ready(self):` |
| `apps/appeals/migrations/0001_initial.py` | 30 | `class Migration(migrations.Migration):` |
| `apps/appeals/migrations/0002_scoreadjustment_previous_answer_score.py` | 4 | `class Migration(migrations.Migration):` |
| `apps/appeals/migrations/0003_alter_appeal_status_alter_appealitem_appeal_type_and_more.py` | 6 | `class Migration(migrations.Migration):` |
| `apps/appeals/models.py` | 102 | `def __str__(self):` |
| `apps/appeals/models.py` | 106 | `class AppealItem(models.Model):` |
| `apps/appeals/models.py` | 167 | `class Meta:` |
| `apps/appeals/models.py` | 179 | `def __str__(self):` |
| `apps/appeals/models.py` | 183 | `class ScoreAdjustment(models.Model):` |
| `apps/appeals/models.py` | 235 | `class Meta:` |
| `apps/appeals/models.py` | 243 | `def __str__(self):` |
| `apps/appeals/models.py` | 28 | `class Appeal(models.Model):` |
| `apps/appeals/models.py` | 92 | `class Meta:` |
| `apps/appeals/selectors.py` | 19 | `def student_appeals_queryset(user):` |
| `apps/appeals/selectors.py` | 29 | `def filter_student_appeals(queryset, *, status="", exam_slug="", search=""):` |
| `apps/appeals/selectors.py` | 46 | `def paginate_student_appeals(queryset, page_number, *, per_page=MY_APPEALS_PAGE_SIZE):` |
| `apps/appeals/services/creation.py` | 130 | `def _exam_center_recipients(appeal):` |
| `apps/appeals/services/creation.py` | 153 | `def _notify_exam_center_new_appeal(appeal, *, item_count):` |
| `apps/appeals/services/creation.py` | 21 | `def _already_appealed_message(item):` |
| `apps/appeals/services/creation.py` | 29 | `def _clean_items(attempt, items):` |
| `apps/appeals/services/creation.py` | 90 | `def create_appeal(*, attempt, student, items, org_unit=None):` |
| `apps/appeals/services/decisions.py` | 197 | `def reject_appeal_item(item, *, reviewer, response_text="", request=None):` |
| `apps/appeals/services/decisions.py` | 209 | `def revert_item_adjustment(item):` |
| `apps/appeals/services/decisions.py` | 242 | `def recompute_appeal_status(appeal, *, reviewer=None):` |
| `apps/appeals/services/decisions.py` | 293 | `def _notify_student_appeal_resolved(appeal):` |
| `apps/appeals/services/decisions.py` | 38 | `def _mark_item_resolved(item, status, reviewer, response_text):` |
| `apps/appeals/services/decisions.py` | 47 | `def _audit_score_change(request, reviewer, attempt, *, appeal, adjustment):` |
| `apps/appeals/services/decisions.py` | 76 | `def accept_appeal_item(item, *, reviewer, response_text="", request=None, awarded_points=None):` |
| `apps/appeals/services/permissions.py` | 20 | `def _same_tenant(request, appeal):` |
| `apps/appeals/services/permissions.py` | 27 | `def can_create_appeal(request, attempt, *, at_time=None):` |
| `apps/appeals/services/permissions.py` | 38 | `def can_review_appeal(request, appeal):` |
| `apps/appeals/services/permissions.py` | 45 | `def can_decide_appeal(request, appeal):` |
| `apps/appeals/services/scoring.py` | 121 | `def appeal_score_state(attempt):` |
| `apps/appeals/services/scoring.py` | 130 | `def student_visible_appeal_score_state(attempt, *, at_time=None):` |
| `apps/appeals/services/scoring.py` | 139 | `def student_visible_appeal_status_by_qid(attempt, *, at_time=None):` |
| `apps/appeals/services/scoring.py` | 166 | `def _effective_test_score_with_bonus(attempt, *, answers=None, bonus):` |
| `apps/appeals/services/scoring.py` | 189 | `def effective_test_score(attempt, *, answers=None):` |
| `apps/appeals/services/scoring.py` | 202 | `def student_visible_effective_test_score(attempt, *, answers=None, at_time=None):` |
| `apps/appeals/services/scoring.py` | 208 | `def _bonus_map_from_sources(attempt_ids, *, adjustments_qs, fallback_items_qs):` |
| `apps/appeals/services/scoring.py` | 250 | `def appeal_bonus_map(attempt_ids):` |
| `apps/appeals/services/scoring.py` | 258 | `def student_visible_appeal_bonus_map(attempt_ids, *, at_time=None):` |
| `apps/appeals/services/scoring.py` | 266 | `def apply_bonus_to_test_result(result, bonus):` |
| `apps/appeals/services/scoring.py` | 299 | `def _question_already_correct(answer, question):` |
| `apps/appeals/services/scoring.py` | 310 | `def _fallback_accepted_bonus_items():` |
| `apps/appeals/services/scoring.py` | 322 | `def _accepted_item_bonus(item, *, attempt=None):` |
| `apps/appeals/services/scoring.py` | 32 | `def _accept_bonus_points():` |
| `apps/appeals/services/scoring.py` | 51 | `def _review_window_cutoff(at_time=None):` |
| `apps/appeals/services/scoring.py` | 55 | `def appeal_item_result_visible_to_student(item, *, at_time=None):` |
| `apps/appeals/services/scoring.py` | 64 | `def appeal_result_hidden_from_student(appeal, *, at_time=None):` |
| `apps/appeals/services/scoring.py` | 71 | `def _student_visible_adjustments(at_time=None):` |
| `apps/appeals/services/scoring.py` | 78 | `def _student_visible_fallback_items(at_time=None):` |
| `apps/appeals/services/scoring.py` | 83 | `def _score_state_from_sources(attempt, *, adjustments_qs, fallback_items_qs):` |
| `apps/appeals/services/state_machine.py` | 13 | `class InvalidAppealTransition(ValidationError):` |
| `apps/appeals/services/state_machine.py` | 17 | `def can_transition(current, target):` |
| `apps/appeals/services/state_machine.py` | 23 | `def assert_transition(current, target):` |
| `apps/appeals/services/window.py` | 17 | `def _finished_at(attempt):` |
| `apps/appeals/services/window.py` | 21 | `def appeal_deadline(attempt):` |
| `apps/appeals/services/window.py` | 38 | `def is_within_appeal_window(attempt, *, at_time=None):` |
| `apps/appeals/services/window.py` | 48 | `def remaining_window_seconds(attempt, *, at_time=None):` |
| `apps/appeals/tests/test_creation.py` | 104 | `class AppealCreateViewTests(TestCase):` |
| `apps/appeals/tests/test_creation.py` | 105 | `def setUp(self):` |
| `apps/appeals/tests/test_creation.py` | 151 | `def test_create_page_shows_student_and_correct_answer_and_search(self):` |
| `apps/appeals/tests/test_creation.py` | 165 | `def test_create_page_from_profile_results_hides_answer_details(self):` |
| `apps/appeals/tests/test_creation.py` | 182 | `def test_create_page_locks_questions_already_appealed(self):` |
| `apps/appeals/tests/test_creation.py` | 214 | `def test_create_page_has_no_marked_quick_select_button(self):` |
| `apps/appeals/tests/test_creation.py` | 224 | `def test_final_exam_hides_my_appeals_link_and_returns_to_entry_after_submit(self):` |
| `apps/appeals/tests/test_creation.py` | 23 | `def _assign_user_to_org(user, organization, profile_role, membership_role_name):` |
| `apps/appeals/tests/test_creation.py` | 248 | `def test_final_exam_from_profile_results_returns_to_my_appeals_after_submit(self):` |
| `apps/appeals/tests/test_creation.py` | 276 | `class AppealExamCenterRoutingTests(TestCase):` |
| `apps/appeals/tests/test_creation.py` | 277 | `def setUp(self):` |
| `apps/appeals/tests/test_creation.py` | 320 | `def _client_for(self, user):` |
| `apps/appeals/tests/test_creation.py` | 328 | `def test_teacher_cannot_manage_or_review_appeals(self):` |
| `apps/appeals/tests/test_creation.py` | 334 | `def test_standalone_appeal_urls_redirect_to_dashboard_sections(self):` |
| `apps/appeals/tests/test_creation.py` | 352 | `def test_exam_center_sees_all_org_appeals_and_can_review(self):` |
| `apps/appeals/tests/test_creation.py` | 367 | `def test_exam_center_profile_sidebar_shows_pending_appeal_badge(self):` |
| `apps/appeals/tests/test_creation.py` | 382 | `def test_profile_badges_api_updates_pending_appeals_after_decision(self):` |
| `apps/appeals/tests/test_creation.py` | 399 | `def test_review_ajax_accept_returns_score_delta_toast_and_list_edit_timer(self):` |
| `apps/appeals/tests/test_creation.py` | 40 | `class AppealCreationTests(TestCase):` |
| `apps/appeals/tests/test_creation.py` | 41 | `def setUp(self):` |
| `apps/appeals/tests/test_creation.py` | 425 | `def test_detail_score_update_notice_belongs_to_current_appeal(self):` |
| `apps/appeals/tests/test_creation.py` | 58 | `def _item(self, question, comment=VALID_COMMENT, appeal_type=APPEAL_TYPE_WRONG_ANSWER_KEY):` |
| `apps/appeals/tests/test_creation.py` | 61 | `def test_create_single_item_appeal(self):` |
| `apps/appeals/tests/test_creation.py` | 67 | `def test_create_multi_item_appeal(self):` |
| `apps/appeals/tests/test_creation.py` | 73 | `def test_empty_items_rejected(self):` |
| `apps/appeals/tests/test_creation.py` | 77 | `def test_short_comment_rejected(self):` |
| `apps/appeals/tests/test_creation.py` | 81 | `def test_duplicate_question_rejected(self):` |
| `apps/appeals/tests/test_creation.py` | 85 | `def test_question_already_appealed_for_attempt_rejected(self):` |
| `apps/appeals/tests/test_creation.py` | 91 | `def test_question_not_in_attempt_rejected(self):` |
| `apps/appeals/tests/test_creation.py` | 95 | `def test_invalid_appeal_type_rejected(self):` |
| `apps/appeals/tests/test_effective_display.py` | 101 | `def test_bonus_map_includes_accepted_item_without_adjustment(self):` |
| `apps/appeals/tests/test_effective_display.py` | 118 | `def test_attach_summaries_include_bonus(self):` |
| `apps/appeals/tests/test_effective_display.py` | 124 | `def test_student_visible_bonus_waits_for_reviewer_edit_window(self):` |
| `apps/appeals/tests/test_effective_display.py` | 140 | `def test_reject_reverts_bonus_everywhere(self):` |
| `apps/appeals/tests/test_effective_display.py` | 148 | `def test_notifications_on_create_and_resolve(self):` |
| `apps/appeals/tests/test_effective_display.py` | 37 | `class EffectiveDisplayTests(TestCase):` |
| `apps/appeals/tests/test_effective_display.py` | 38 | `def setUp(self):` |
| `apps/appeals/tests/test_effective_display.py` | 69 | `def _accepted_appeal(self):` |
| `apps/appeals/tests/test_effective_display.py` | 83 | `def test_bonus_map_and_apply(self):` |
| `apps/appeals/tests/test_scoring.py` | 106 | `def test_fallback_does_not_double_credit_already_credited_question(self):` |
| `apps/appeals/tests/test_scoring.py` | 123 | `def test_student_visible_status_by_qid(self):` |
| `apps/appeals/tests/test_scoring.py` | 158 | `def test_accept_is_idempotent_no_double_increment(self):` |
| `apps/appeals/tests/test_scoring.py` | 168 | `def test_reject_after_accept_reverts_bonus(self):` |
| `apps/appeals/tests/test_scoring.py` | 180 | `class WrittenExamScoringTests(_Base):` |
| `apps/appeals/tests/test_scoring.py` | 181 | `def setUp(self):` |
| `apps/appeals/tests/test_scoring.py` | 191 | `def test_accept_adds_one_point(self):` |
| `apps/appeals/tests/test_scoring.py` | 206 | `def test_reject_after_accept_restores_previous_answer_score(self):` |
| `apps/appeals/tests/test_scoring.py` | 216 | `def test_accept_recomputes_attempt_score_from_answers(self):` |
| `apps/appeals/tests/test_scoring.py` | 233 | `class AppealStatusAggregationTests(_Base):` |
| `apps/appeals/tests/test_scoring.py` | 234 | `def setUp(self):` |
| `apps/appeals/tests/test_scoring.py` | 242 | `def _question_with_answer(self, order):` |
| `apps/appeals/tests/test_scoring.py` | 248 | `def test_all_accepted_marks_appeal_accepted(self):` |
| `apps/appeals/tests/test_scoring.py` | 256 | `def test_mixed_marks_partially_accepted(self):` |
| `apps/appeals/tests/test_scoring.py` | 36 | `class _Base(TestCase):` |
| `apps/appeals/tests/test_scoring.py` | 37 | `def setUp(self):` |
| `apps/appeals/tests/test_scoring.py` | 44 | `def _appeal(self, attempt):` |
| `apps/appeals/tests/test_scoring.py` | 52 | `def _item(self, appeal, question, answer):` |
| `apps/appeals/tests/test_scoring.py` | 62 | `class TestExamScoringTests(_Base):` |
| `apps/appeals/tests/test_scoring.py` | 63 | `def setUp(self):` |
| `apps/appeals/tests/test_scoring.py` | 75 | `def test_accept_adds_one_point_bonus(self):` |
| `apps/appeals/tests/test_scoring.py` | 92 | `def test_same_question_not_credited_twice_across_items(self):` |
| `apps/appeals/tests/test_window.py` | 17 | `class AppealWindowTests(TestCase):` |
| `apps/appeals/tests/test_window.py` | 18 | `def setUp(self):` |
| `apps/appeals/tests/test_window.py` | 28 | `def _attempt(self, *, status="submitted", finished_delta=None):` |
| `apps/appeals/tests/test_window.py` | 35 | `def test_within_window_just_finished(self):` |
| `apps/appeals/tests/test_window.py` | 40 | `def test_within_window_two_days_ago(self):` |
| `apps/appeals/tests/test_window.py` | 44 | `def test_window_closes_after_third_calendar_day(self):` |
| `apps/appeals/tests/test_window.py` | 54 | `def test_after_window_four_days_ago(self):` |
| `apps/appeals/tests/test_window.py` | 59 | `def test_unfinished_attempt_not_appealable(self):` |
| `apps/appeals/views/shared/_helpers.py` | 4 | `def _marked_question_map(attempt):` |
| `apps/appeals/views/shared/detail.py` | 32 | `def _appeal_item_stats(items):` |
| `apps/appeals/views/shared/detail.py` | 46 | `def _format_decimal(value):` |
| `apps/appeals/views/shared/detail.py` | 56 | `def _appeal_positive_bonus(items):` |
| `apps/appeals/views/shared/detail.py` | 70 | `def appeal_detail(request, appeal_id):` |
| `apps/appeals/views/student/endpoints.py` | 152 | `def build_my_appeals_context(request, *, list_action, section=""):` |
| `apps/appeals/views/student/endpoints.py` | 188 | `def my_appeals(request):` |
| `apps/appeals/views/student/endpoints.py` | 36 | `def _is_profile_results_request(request):` |
| `apps/appeals/views/student/endpoints.py` | 43 | `def _result_url(exam, attempt, request=None):` |
| `apps/appeals/views/student/endpoints.py` | 54 | `def _is_final_exam(exam):` |
| `apps/appeals/views/student/endpoints.py` | 58 | `def _parse_items_from_post(request, delivered_question_ids):` |
| `apps/appeals/views/student/endpoints.py` | 80 | `def appeal_create(request, attempt_id):` |
| `apps/appeals/views/teacher/endpoints.py` | 185 | `def manage_appeals(request):` |
| `apps/appeals/views/teacher/endpoints.py` | 208 | `def review_appeal(request, appeal_id):` |
| `apps/appeals/views/teacher/endpoints.py` | 238 | `def _edit_locked(item):` |
| `apps/appeals/views/teacher/endpoints.py` | 40 | `def _format_seconds(seconds):` |
| `apps/appeals/views/teacher/endpoints.py` | 45 | `def _format_decimal(value):` |
| `apps/appeals/views/teacher/endpoints.py` | 50 | `def _can_open_appeal_management(request):` |
| `apps/appeals/views/teacher/endpoints.py` | 54 | `def count_pending_manage_appeals(request):` |
| `apps/appeals/views/teacher/endpoints.py` | 71 | `def _appeal_edit_seconds_left(appeal, now):` |
| `apps/appeals/views/teacher/endpoints.py` | 84 | `def _current_review_score(appeal, is_test):` |
| `apps/appeals/views/teacher/endpoints.py` | 94 | `def build_manage_appeals_context(request, *, list_action, section=""):` |
| `apps/exams/admin.py` | 100 | `class ExamAnswerAdmin(admin.ModelAdmin):` |
| `apps/exams/admin.py` | 107 | `class CodingExamQuestionAdmin(admin.ModelAdmin):` |
| `apps/exams/admin.py` | 113 | `def exam_title(self, obj):` |
| `apps/exams/admin.py` | 120 | `class CodingSubmissionAdmin(admin.ModelAdmin):` |
| `apps/exams/admin.py` | 129 | `class StudentGroupAdmin(admin.ModelAdmin):` |
| `apps/exams/admin.py` | 137 | `class QuestionBankAdmin(admin.ModelAdmin):` |
| `apps/exams/admin.py` | 167 | `def question_count(self, obj):` |
| `apps/exams/admin.py` | 174 | `class ProctoringLogAdmin(admin.ModelAdmin):` |
| `apps/exams/admin.py` | 192 | `def user_display(self, obj):` |
| `apps/exams/admin.py` | 197 | `def get_queryset(self, request):` |
| `apps/exams/admin.py` | 203 | `class ExamSupervisionConfigAdmin(admin.ModelAdmin):` |
| `apps/exams/admin.py` | 211 | `class SupervisionIncidentAdmin(admin.ModelAdmin):` |
| `apps/exams/admin.py` | 218 | `def student_display(self, obj):` |
| `apps/exams/admin.py` | 223 | `def exam_display(self, obj):` |
| `apps/exams/admin.py` | 228 | `def get_queryset(self, request):` |
| `apps/exams/admin.py` | 237 | `class ExamRoomAdmin(admin.ModelAdmin):` |
| `apps/exams/admin.py` | 244 | `class ExamRoomSessionAdmin(admin.ModelAdmin):` |
| `apps/exams/admin.py` | 250 | `def get_queryset(self, request):` |
| `apps/exams/admin.py` | 255 | `class FinalExamTicketAdmin(admin.ModelAdmin):` |
| `apps/exams/admin.py` | 263 | `def get_queryset(self, request):` |
| `apps/exams/admin.py` | 28 | `class ExamQuestionOptionInline(admin.TabularInline):` |
| `apps/exams/admin.py` | 34 | `class CodingTestCaseInline(admin.TabularInline):` |
| `apps/exams/admin.py` | 40 | `class CodingFileInline(admin.TabularInline):` |
| `apps/exams/admin.py` | 49 | `class ExamAdmin(admin.ModelAdmin):` |
| `apps/exams/admin.py` | 72 | `class ExamQuestionAdmin(admin.ModelAdmin):` |
| `apps/exams/admin.py` | 78 | `def short_text(self, obj):` |
| `apps/exams/admin.py` | 85 | `class ExamAttemptAdmin(admin.ModelAdmin):` |
| `apps/exams/apps.py` | 4 | `class ExamsConfig(AppConfig):` |
| `apps/exams/apps.py` | 8 | `def ready(self):` |
| `apps/exams/constants.py` | 111 | `def get_live_session_model():` |
| `apps/exams/constants.py` | 118 | `def get_live_active_states():` |
| `apps/exams/consumers.py` | 102 | `class FinalExamRoomConsumer(AsyncJsonWebsocketConsumer):` |
| `apps/exams/consumers.py` | 112 | `async def connect(self):` |
| `apps/exams/consumers.py` | 135 | `def _can_supervise(self, user, session_id) -> bool:` |
| `apps/exams/consumers.py` | 144 | `async def disconnect(self, close_code):` |
| `apps/exams/consumers.py` | 149 | `async def receive_json(self, content, **kwargs):` |
| `apps/exams/consumers.py` | 154 | `async def final_event(self, event):` |
| `apps/exams/consumers.py` | 163 | `class FinalExamWaitConsumer(AsyncJsonWebsocketConsumer):` |
| `apps/exams/consumers.py` | 176 | `async def connect(self):` |
| `apps/exams/consumers.py` | 205 | `def _authorize(self, user, ticket_id):` |
| `apps/exams/consumers.py` | 230 | `def _mark_connected_db(self, reconnect: bool):` |
| `apps/exams/consumers.py` | 24 | `class ExamSupervisionConsumer(AsyncJsonWebsocketConsumer):` |
| `apps/exams/consumers.py` | 250 | `async def _mark_connected(self, reconnect: bool):` |
| `apps/exams/consumers.py` | 253 | `async def disconnect(self, close_code):` |
| `apps/exams/consumers.py` | 260 | `def _mark_disconnected(self):` |
| `apps/exams/consumers.py` | 269 | `async def receive_json(self, content, **kwargs):` |
| `apps/exams/consumers.py` | 285 | `def _heartbeat(self):` |
| `apps/exams/consumers.py` | 295 | `def _set_ready(self, value: bool):` |
| `apps/exams/consumers.py` | 305 | `async def final_event(self, event):` |
| `apps/exams/consumers.py` | 32 | `async def connect(self):` |
| `apps/exams/consumers.py` | 61 | `def _can_observe_attempt(self, user, attempt_id) -> bool:` |
| `apps/exams/consumers.py` | 83 | `async def disconnect(self, close_code):` |
| `apps/exams/consumers.py` | 88 | `async def supervision_event(self, event):` |
| `apps/exams/domain/access_policy.py` | 111 | `def save(self, *args, **kwargs):` |
| `apps/exams/domain/access_policy.py` | 115 | `def has_student(self, user: User) -> bool:` |
| `apps/exams/domain/access_policy.py` | 118 | `def has_teacher(self, user: User) -> bool:` |
| `apps/exams/domain/access_policy.py` | 124 | `class ExamAccessPolicyMixin:` |
| `apps/exams/domain/access_policy.py` | 125 | `def _expire_stale_attempts_for(self, user: User) -> bool:` |
| `apps/exams/domain/access_policy.py` | 12 | `class StudentGroup(models.Model):` |
| `apps/exams/domain/access_policy.py` | 135 | `def _user_has_active_attempt(self, user: User) -> bool:` |
| `apps/exams/domain/access_policy.py` | 139 | `def _user_in_allowed_groups(self, user: User) -> bool:` |
| `apps/exams/domain/access_policy.py` | 142 | `def _user_is_excluded(self, user: User) -> bool:` |
| `apps/exams/domain/access_policy.py` | 145 | `def _user_in_assigned_course(self, user: User) -> bool:` |
| `apps/exams/domain/access_policy.py` | 150 | `def can_user_see(self, user: User) -> bool:` |
| `apps/exams/domain/access_policy.py` | 177 | `def can_user_start(self, user: User, code: str \| None = None) -> tuple[bool, str \| None]:` |
| `apps/exams/domain/access_policy.py` | 237 | `def requires_code_for(self, user: User) -> bool:` |
| `apps/exams/domain/access_policy.py` | 70 | `class Meta:` |
| `apps/exams/domain/access_policy.py` | 76 | `def __str__(self):` |
| `apps/exams/domain/access_policy.py` | 81 | `def clean(self):` |
| `apps/exams/domain/ai_config.py` | 103 | `def get_ai_config() -> AIConfiguration:` |
| `apps/exams/domain/ai_config.py` | 17 | `class AIConfiguration(models.Model):` |
| `apps/exams/domain/ai_config.py` | 78 | `class Meta:` |
| `apps/exams/domain/ai_config.py` | 83 | `def __str__(self):` |
| `apps/exams/domain/ai_config.py` | 86 | `def save(self, *args, **kwargs):` |
| `apps/exams/domain/ai_config.py` | 93 | `def load(cls) -> "AIConfiguration":` |
| `apps/exams/domain/attempts.py` | 162 | `class Meta:` |
| `apps/exams/domain/attempts.py` | 16 | `class ExamAttempt(AttemptGradingMixin, models.Model):` |
| `apps/exams/domain/attempts.py` | 186 | `def __str__(self):` |
| `apps/exams/domain/attempts.py` | 190 | `def is_finished(self):` |
| `apps/exams/domain/attempts.py` | 194 | `def deadline_at(self):` |
| `apps/exams/domain/attempts.py` | 203 | `def score_percent(self):` |
| `apps/exams/domain/attempts.py` | 214 | `def is_time_limit_reached(self, *, at_time=None):` |
| `apps/exams/domain/attempts.py` | 221 | `def is_resume_time_expired(self):` |
| `apps/exams/domain/attempts.py` | 224 | `def expire_if_time_limit_reached(self, *, at_time=None):` |
| `apps/exams/domain/attempts.py` | 231 | `def supervision_resume_deadline(self):` |
| `apps/exams/domain/attempts.py` | 254 | `def is_resume_window_expired(self):` |
| `apps/exams/domain/attempts.py` | 260 | `def expire_if_resume_window_expired(self, *, at_time=None):` |
| `apps/exams/domain/attempts.py` | 301 | `def mark_finished(self, status="submitted", extra_update_fields=None):` |
| `apps/exams/domain/attempts.py` | 319 | `def recalculate_score(self):` |
| `apps/exams/domain/attempts.py` | 332 | `class ExamAnswer(AnswerGradingMixin, models.Model):` |
| `apps/exams/domain/attempts.py` | 378 | `class Meta:` |
| `apps/exams/domain/attempts.py` | 383 | `def __str__(self):` |
| `apps/exams/domain/attempts.py` | 387 | `class ExamAnswerFile(models.Model):` |
| `apps/exams/domain/attempts.py` | 404 | `def filename(self):` |
| `apps/exams/domain/attempts.py` | 407 | `def __str__(self):` |
| `apps/exams/domain/attempts.py` | 411 | `class ProctoringLog(models.Model):` |
| `apps/exams/domain/attempts.py` | 448 | `class Meta:` |
| `apps/exams/domain/attempts.py` | 457 | `def __str__(self):` |
| `apps/exams/domain/coding.py` | 103 | `def __str__(self):` |
| `apps/exams/domain/coding.py` | 107 | `def exam(self):` |
| `apps/exams/domain/coding.py` | 111 | `def default_filename(self):` |
| `apps/exams/domain/coding.py` | 115 | `class CodingTestCase(models.Model):` |
| `apps/exams/domain/coding.py` | 154 | `class Meta:` |
| `apps/exams/domain/coding.py` | 162 | `def __str__(self):` |
| `apps/exams/domain/coding.py` | 166 | `class CodingSubmission(models.Model):` |
| `apps/exams/domain/coding.py` | 276 | `class Meta:` |
| `apps/exams/domain/coding.py` | 286 | `def __str__(self):` |
| `apps/exams/domain/coding.py` | 290 | `class CodingFile(models.Model):` |
| `apps/exams/domain/coding.py` | 317 | `class Meta:` |
| `apps/exams/domain/coding.py` | 323 | `def __str__(self):` |
| `apps/exams/domain/coding.py` | 8 | `class CodingExamQuestion(models.Model):` |
| `apps/exams/domain/coding.py` | 98 | `class Meta:` |
| `apps/exams/domain/exam_definition.py` | 22 | `class Exam(ExamAccessPolicyMixin, models.Model):` |
| `apps/exams/domain/exam_definition.py` | 245 | `class Meta:` |
| `apps/exams/domain/exam_definition.py` | 271 | `def __str__(self):` |
| `apps/exams/domain/exam_definition.py` | 274 | `def save(self, *args, **kwargs):` |
| `apps/exams/domain/exam_definition.py` | 289 | `def is_before_start(self) -> bool:` |
| `apps/exams/domain/exam_definition.py` | 294 | `def is_after_end(self) -> bool:` |
| `apps/exams/domain/exam_definition.py` | 299 | `def is_currently_active(self) -> bool:` |
| `apps/exams/domain/exam_definition.py` | 303 | `def lifecycle_status(self) -> str:` |
| `apps/exams/domain/exam_definition.py` | 323 | `def attempts_left_for(self, user: User) -> int \| None:` |
| `apps/exams/domain/exam_definition.py` | 336 | `class QuestionBlock(models.Model):` |
| `apps/exams/domain/exam_definition.py` | 364 | `class Meta:` |
| `apps/exams/domain/exam_definition.py` | 369 | `def __str__(self):` |
| `apps/exams/domain/final_center.py` | 166 | `class Meta:` |
| `apps/exams/domain/final_center.py` | 177 | `def __str__(self):` |
| `apps/exams/domain/final_center.py` | 181 | `class ExamRoomComputer(models.Model):` |
| `apps/exams/domain/final_center.py` | 247 | `class Meta:` |
| `apps/exams/domain/final_center.py` | 264 | `def __str__(self):` |
| `apps/exams/domain/final_center.py` | 268 | `def normalize_mac(raw: str) -> str:` |
| `apps/exams/domain/final_center.py` | 284 | `class ExamRoomSession(models.Model):` |
| `apps/exams/domain/final_center.py` | 392 | `class Meta:` |
| `apps/exams/domain/final_center.py` | 413 | `def __str__(self):` |
| `apps/exams/domain/final_center.py` | 417 | `def is_live(self) -> bool:` |
| `apps/exams/domain/final_center.py` | 421 | `def is_finished(self) -> bool:` |
| `apps/exams/domain/final_center.py` | 425 | `class FinalExamTicket(models.Model):` |
| `apps/exams/domain/final_center.py` | 559 | `class Meta:` |
| `apps/exams/domain/final_center.py` | 580 | `def __str__(self):` |
| `apps/exams/domain/final_center.py` | 584 | `def has_valid_pin(self) -> bool:` |
| `apps/exams/domain/final_center.py` | 594 | `def is_pin_locked(self) -> bool:` |
| `apps/exams/domain/final_center.py` | 99 | `class ExamRoom(models.Model):` |
| `apps/exams/domain/grading.py` | 14 | `class AnswerGradingMixin:` |
| `apps/exams/domain/grading.py` | 15 | `def auto_evaluate(self):` |
| `apps/exams/domain/grading.py` | 4 | `class AttemptGradingMixin:` |
| `apps/exams/domain/grading.py` | 5 | `def mark_checked(self):` |
| `apps/exams/domain/import_jobs.py` | 19 | `def extraction_job_upload_path(instance: "TextExtractionJob", filename: str) -> str:` |
| `apps/exams/domain/import_jobs.py` | 31 | `class TextExtractionJob(models.Model):` |
| `apps/exams/domain/import_jobs.py` | 83 | `class Meta:` |
| `apps/exams/domain/import_jobs.py` | 86 | `def __str__(self):` |
| `apps/exams/domain/language.py` | 19 | `class ExamLanguageVariant(models.Model):` |
| `apps/exams/domain/language.py` | 56 | `class Meta:` |
| `apps/exams/domain/language.py` | 70 | `def __str__(self):` |
| `apps/exams/domain/language.py` | 75 | `def effective_question_count(self):` |
| `apps/exams/domain/language.py` | 82 | `def question_count(self):` |
| `apps/exams/domain/question_bank/__init__.py` | 19 | `def question_media_path(instance, filename):` |
| `apps/exams/domain/question_bank/__init__.py` | 23 | `def bank_question_media_path(instance, filename):` |
| `apps/exams/domain/question_bank/__init__.py` | 27 | `def option_media_path(instance, filename):` |
| `apps/exams/domain/question_bank/__init__.py` | 33 | `def bank_option_media_path(instance, filename):` |
| `apps/exams/domain/question_bank/__init__.py` | 39 | `def validate_video_size(f):` |
| `apps/exams/domain/question_bank/bank_question.py` | 121 | `class Meta:` |
| `apps/exams/domain/question_bank/bank_question.py` | 131 | `def __str__(self):` |
| `apps/exams/domain/question_bank/bank_question.py` | 135 | `def correct_options(self):` |
| `apps/exams/domain/question_bank/bank_question.py` | 139 | `class BankQuestionOption(models.Model):` |
| `apps/exams/domain/question_bank/bank_question.py` | 164 | `class Meta:` |
| `apps/exams/domain/question_bank/bank_question.py` | 168 | `def __str__(self):` |
| `apps/exams/domain/question_bank/bank_question.py` | 25 | `class BankQuestion(models.Model):` |
| `apps/exams/domain/question_bank/exam_question.py` | 120 | `class Meta:` |
| `apps/exams/domain/question_bank/exam_question.py` | 129 | `def __str__(self):` |
| `apps/exams/domain/question_bank/exam_question.py` | 133 | `def question_count(self):` |
| `apps/exams/domain/question_bank/exam_question.py` | 137 | `class ExamQuestion(models.Model):` |
| `apps/exams/domain/question_bank/exam_question.py` | 21 | `class QuestionBank(models.Model):` |
| `apps/exams/domain/question_bank/exam_question.py` | 297 | `class Meta:` |
| `apps/exams/domain/question_bank/exam_question.py` | 302 | `def __str__(self):` |
| `apps/exams/domain/question_bank/exam_question.py` | 306 | `def effective_time_limit(self):` |
| `apps/exams/domain/question_bank/exam_question.py` | 314 | `def total_answers(self):` |
| `apps/exams/domain/question_bank/exam_question.py` | 318 | `def correct_answers_count(self):` |
| `apps/exams/domain/question_bank/exam_question.py` | 322 | `def wrong_answers_count(self):` |
| `apps/exams/domain/question_bank/exam_question.py` | 326 | `def correct_ratio(self):` |
| `apps/exams/domain/question_bank/exam_question.py` | 333 | `def inherited_paint_enabled(self):` |
| `apps/exams/domain/question_bank/exam_question.py` | 341 | `def paint_enabled_effective(self):` |
| `apps/exams/domain/question_bank/exam_question.py` | 349 | `def paint_priority_source(self):` |
| `apps/exams/domain/question_bank/exam_question.py` | 357 | `def set_paint_enabled(self, enabled):` |
| `apps/exams/domain/question_bank/exam_question.py` | 371 | `def mark_ai_difficulty(self, difficulty):` |
| `apps/exams/domain/question_bank/exam_question.py` | 379 | `class ExamQuestionOption(models.Model):` |
| `apps/exams/domain/question_bank/exam_question.py` | 411 | `class Meta:` |
| `apps/exams/domain/question_bank/exam_question.py` | 415 | `def __str__(self):` |
| `apps/exams/domain/student_access.py` | 20 | `class ExamStudentPin(models.Model):` |
| `apps/exams/domain/student_access.py` | 39 | `class Meta:` |
| `apps/exams/domain/student_access.py` | 49 | `def __str__(self):` |
| `apps/exams/domain/student_access.py` | 53 | `class StudentExamAttemptGrant(models.Model):` |
| `apps/exams/domain/student_access.py` | 81 | `class Meta:` |
| `apps/exams/domain/student_access.py` | 88 | `def __str__(self):` |
| `apps/exams/domain/submission_inbox.py` | 144 | `class Meta:` |
| `apps/exams/domain/submission_inbox.py` | 153 | `def __str__(self):` |
| `apps/exams/domain/submission_inbox.py` | 157 | `def is_pending(self):` |
| `apps/exams/domain/submission_inbox.py` | 161 | `def can_be_edited_by_teacher(self):` |
| `apps/exams/domain/submission_inbox.py` | 28 | `class QuestionSubmission(models.Model):` |
| `apps/exams/domain/supervision.py` | 134 | `class Meta:` |
| `apps/exams/domain/supervision.py` | 138 | `def __str__(self):` |
| `apps/exams/domain/supervision.py` | 142 | `def get_max_total_violations(self):` |
| `apps/exams/domain/supervision.py` | 146 | `def get_template_defaults(cls, template_name):` |
| `apps/exams/domain/supervision.py` | 15 | `class ExamSupervisionConfig(models.Model):` |
| `apps/exams/domain/supervision.py` | 192 | `class SupervisionIncident(models.Model):` |
| `apps/exams/domain/supervision.py` | 288 | `class Meta:` |
| `apps/exams/domain/supervision.py` | 301 | `def __str__(self):` |
| `apps/exams/domain/supervision.py` | 305 | `def is_violation(self):` |
| `apps/exams/export_registry.py` | 17 | `def _guard_org(obj_org_id, job_organization):` |
| `apps/exams/export_registry.py` | 24 | `def _build_exam_results_xlsx(*, user, organization, params):` |
| `apps/exams/export_registry.py` | 36 | `def _build_bank_word(*, user, organization, params):` |
| `apps/exams/export_registry.py` | 74 | `def run_export(name, *, user, organization, params):` |
| `apps/exams/features.py` | 10 | `def exam_supervision_enabled() -> bool:` |
| `apps/exams/features.py` | 14 | `def selectable_exam_type_choices(choices):` |
| `apps/exams/features.py` | 20 | `def without_disabled_practical_exams(queryset):` |
| `apps/exams/features.py` | 26 | `def practical_exam_disabled_message() -> str:` |
| `apps/exams/features.py` | 30 | `def supervision_disabled_message() -> str:` |
| `apps/exams/features.py` | 34 | `def disabled_supervision_status(attempt=None) -> dict:` |
| `apps/exams/features.py` | 6 | `def practical_exams_enabled() -> bool:` |
| `apps/exams/forms/bank_question.py` | 109 | `def _option_label(self, index):` |
| `apps/exams/forms/bank_question.py` | 112 | `def _ensure_option_fields_exist(self):` |
| `apps/exams/forms/bank_question.py` | 129 | `def _build_option_fields(self):` |
| `apps/exams/forms/bank_question.py` | 140 | `def _get_cleaned_options(self, cleaned_data):` |
| `apps/exams/forms/bank_question.py` | 150 | `def clean(self):` |
| `apps/exams/forms/bank_question.py` | 186 | `def create_options(self, question_instance):` |
| `apps/exams/forms/bank_question.py` | 196 | `def save_options(self, question_instance):` |
| `apps/exams/forms/bank_question.py` | 19 | `class BankQuestionCreateForm(forms.ModelForm):` |
| `apps/exams/forms/bank_question.py` | 24 | `class Meta:` |
| `apps/exams/forms/bank_question.py` | 70 | `def __init__(self, *args, question_type="test", default_language=None, **kwargs):` |
| `apps/exams/forms/bank_question.py` | 98 | `def _resolve_option_indexes(self, *, data=None, instance=None):` |
| `apps/exams/forms/coding.py` | 112 | `class Meta:` |
| `apps/exams/forms/coding.py` | 14 | `def parse_test_cases(raw_value, *, visibility):` |
| `apps/exams/forms/coding.py` | 163 | `def __init__(self, *args, **kwargs):` |
| `apps/exams/forms/coding.py` | 171 | `def clean_visible_test_cases(self):` |
| `apps/exams/forms/coding.py` | 177 | `def clean_hidden_test_cases(self):` |
| `apps/exams/forms/coding.py` | 183 | `def save_test_cases(self, coding_question):` |
| `apps/exams/forms/coding.py` | 54 | `def dump_test_cases(cases):` |
| `apps/exams/forms/coding.py` | 66 | `def sync_coding_test_cases(coding_question, *, visible_cases, hidden_cases):` |
| `apps/exams/forms/coding.py` | 86 | `class CodingExamQuestionForm(forms.ModelForm):` |
| `apps/exams/forms/exam.py` | 223 | `def __init__(self, *args, **kwargs):` |
| `apps/exams/forms/exam.py` | 29 | `class ExamForm(CodingExamFieldsMixin, forms.ModelForm):` |
| `apps/exams/forms/exam.py` | 37 | `class Meta:` |
| `apps/exams/forms/exam.py` | 385 | `def _load_coding_question_initial(self):` |
| `apps/exams/forms/exam.py` | 421 | `def _submitted_exam_type(self):` |
| `apps/exams/forms/exam.py` | 426 | `def clean_coding_visible_test_cases(self):` |
| `apps/exams/forms/exam.py` | 434 | `def clean_coding_hidden_test_cases(self):` |
| `apps/exams/forms/exam.py` | 442 | `def clean_exam_type_extended(self):` |
| `apps/exams/forms/exam.py` | 454 | `def clean_access_code(self):` |
| `apps/exams/forms/exam.py` | 464 | `def clean_random_question_count(self):` |
| `apps/exams/forms/exam.py` | 479 | `def _clean_enabled_toggle(self, field_name, *, default):` |
| `apps/exams/forms/exam.py` | 487 | `def clean_fair_question_distribution_enabled(self):` |
| `apps/exams/forms/exam.py` | 490 | `def clean_ai_difficulty_balance_enabled(self):` |
| `apps/exams/forms/exam.py` | 494 | `def _ensure_local_aware(value):` |
| `apps/exams/forms/exam.py` | 505 | `def clean_start_datetime(self):` |
| `apps/exams/forms/exam.py` | 508 | `def clean_end_datetime(self):` |
| `apps/exams/forms/exam.py` | 511 | `def clean(self):` |
| `apps/exams/forms/exam_coding_fields.py` | 11 | `class CodingExamFieldsMixin(forms.Form):` |
| `apps/exams/forms/final_center.py` | 107 | `def __init__(self, *args, organization=None, **kwargs):` |
| `apps/exams/forms/final_center.py` | 10 | `class ExamRoomForm(forms.ModelForm):` |
| `apps/exams/forms/final_center.py` | 120 | `def clean(self):` |
| `apps/exams/forms/final_center.py` | 128 | `def username_list(self):` |
| `apps/exams/forms/final_center.py` | 13 | `class Meta:` |
| `apps/exams/forms/final_center.py` | 20 | `def __init__(self, *args, organization=None, **kwargs):` |
| `apps/exams/forms/final_center.py` | 24 | `def clean_code(self):` |
| `apps/exams/forms/final_center.py` | 34 | `class ExamRoomSessionForm(forms.ModelForm):` |
| `apps/exams/forms/final_center.py` | 45 | `class Meta:` |
| `apps/exams/forms/final_center.py` | 54 | `def __init__(self, *args, organization=None, **kwargs):` |
| `apps/exams/forms/final_center.py` | 68 | `def clean(self):` |
| `apps/exams/forms/final_center.py` | 83 | `class AssignStudentsForm(forms.Form):` |
| `apps/exams/forms/group.py` | 134 | `def __init__(self, *args, **kwargs):` |
| `apps/exams/forms/group.py` | 23 | `class UserMetadataSelectMultiple(forms.SelectMultiple):` |
| `apps/exams/forms/group.py` | 249 | `def _user_option_label(self, user):` |
| `apps/exams/forms/group.py` | 255 | `def _is_teacher_profile(self, user):` |
| `apps/exams/forms/group.py` | 264 | `def clean(self):` |
| `apps/exams/forms/group.py` | 32 | `def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):` |
| `apps/exams/forms/group.py` | 334 | `def _post_clean(self):` |
| `apps/exams/forms/group.py` | 345 | `def save(self, commit=True):` |
| `apps/exams/forms/group.py` | 60 | `def _iter_prefetched_group_memberships(self, user):` |
| `apps/exams/forms/group.py` | 71 | `class StudentGroupForm(forms.ModelForm):` |
| `apps/exams/forms/group.py` | 96 | `class Meta:` |
| `apps/exams/forms/question.py` | 140 | `def __init__(self, *args, exam_type=None, subject_blocks=None, exam=None, **kwargs):` |
| `apps/exams/forms/question.py` | 15 | `class ExamQuestionCreateForm(forms.ModelForm):` |
| `apps/exams/forms/question.py` | 204 | `def _fallback_language(self):` |
| `apps/exams/forms/question.py` | 216 | `def _resolve_option_indexes(self, *, data=None, instance=None):` |
| `apps/exams/forms/question.py` | 229 | `def _option_label(self, index):` |
| `apps/exams/forms/question.py` | 245 | `def _ensure_option_fields_exist(self):` |
| `apps/exams/forms/question.py` | 267 | `def _build_option_fields(self):` |
| `apps/exams/forms/question.py` | 280 | `def _get_cleaned_options(self, cleaned_data):` |
| `apps/exams/forms/question.py` | 295 | `def clean_language(self):` |
| `apps/exams/forms/question.py` | 298 | `def clean(self):` |
| `apps/exams/forms/question.py` | 351 | `def create_options(self, question_instance: ExamQuestion):` |
| `apps/exams/forms/question.py` | 362 | `def save_options(self, question_instance: ExamQuestion):` |
| `apps/exams/forms/question.py` | 68 | `class Meta:` |
| `apps/exams/management/commands/_seed_helpers/courses.py` | 36 | `def _seed_course_content(self, course, teachers, students, group_name):` |
| `apps/exams/management/commands/_seed_helpers/courses.py` | 6 | `class CoursesSeedMixin:` |
| `apps/exams/management/commands/_seed_helpers/courses.py` | 9 | `def _ensure_course(self, organization, teacher):` |
| `apps/exams/management/commands/_seed_helpers/exams.py` | 135 | `def _seed_written_exam_questions(self, exam):` |
| `apps/exams/management/commands/_seed_helpers/exams.py` | 44 | `def _set_test_question_options(self, question, options):` |
| `apps/exams/management/commands/_seed_helpers/exams.py` | 54 | `def _seed_test_exam_questions(self, exam):` |
| `apps/exams/management/commands/_seed_helpers/exams.py` | 6 | `class ExamsSeedMixin:` |
| `apps/exams/management/commands/_seed_helpers/exams.py` | 9 | `def _ensure_exam(self, teacher, course, title, exam_type, enable_paint):` |
| `apps/exams/management/commands/_seed_helpers/users.py` | 135 | `def _ensure_membership(self, user, organization, role, assigned_by):` |
| `apps/exams/management/commands/_seed_helpers/users.py` | 13 | `class UsersSeedMixin:` |
| `apps/exams/management/commands/_seed_helpers/users.py` | 16 | `def _ensure_user(self, username, email, password):` |
| `apps/exams/management/commands/_seed_helpers/users.py` | 30 | `def _assign_profile(self, user, organization, role):` |
| `apps/exams/management/commands/_seed_helpers/users.py` | 39 | `def _ensure_organization(self, name, org_type, owner):` |
| `apps/exams/management/commands/_seed_helpers/users.py` | 69 | `def _resolve_role(self, organization, profile_role, owner_role=None):` |
| `apps/exams/management/commands/seed_demo_hierarchy.py` | 219 | `def _ensure_superuser(self, username, email, password):` |
| `apps/exams/management/commands/seed_demo_hierarchy.py` | 239 | `def _set_name(self, user, first, last):` |
| `apps/exams/management/commands/seed_demo_hierarchy.py` | 245 | `def _ensure_role(self, org, name, display_name, level, permissions):` |
| `apps/exams/management/commands/seed_demo_hierarchy.py` | 262 | `def _ensure_unit(self, org, name, unit_type, parent, code):` |
| `apps/exams/management/commands/seed_demo_hierarchy.py` | 284 | `def _ensure_membership_scoped(self, user, org, role, assigned_by, scope_unit):` |
| `apps/exams/management/commands/seed_demo_hierarchy.py` | 291 | `def _make_students(self, org, owner, student_role, prefix, count, password, kafedra):` |
| `apps/exams/management/commands/seed_demo_hierarchy.py` | 302 | `def _ensure_group(self, org, teacher, name, students, org_unit=None):` |
| `apps/exams/management/commands/seed_demo_hierarchy.py` | 311 | `def _ensure_final_exam(self, author, org):` |
| `apps/exams/management/commands/seed_demo_hierarchy.py` | 333 | `def _seed_questions(self, exam):` |
| `apps/exams/management/commands/seed_demo_hierarchy.py` | 351 | `def _ensure_room(self, org, creator):` |
| `apps/exams/management/commands/seed_demo_hierarchy.py` | 367 | `def _ensure_subject(self, org, code, name):` |
| `apps/exams/management/commands/seed_demo_hierarchy.py` | 374 | `def _ensure_local_computer(self, org, room, creator):` |
| `apps/exams/management/commands/seed_demo_hierarchy.py` | 403 | `def _report(` |
| `apps/exams/management/commands/seed_demo_hierarchy.py` | 72 | `class Command(UsersSeedMixin, BaseCommand):` |
| `apps/exams/management/commands/seed_demo_hierarchy.py` | 75 | `def add_arguments(self, parser):` |
| `apps/exams/management/commands/seed_demo_hierarchy.py` | 91 | `def handle(self, *args, **options):` |
| `apps/exams/management/commands/seed_final_exam_demo.py` | 116 | `def _ensure_final_exam(self, author, org):` |
| `apps/exams/management/commands/seed_final_exam_demo.py` | 150 | `def _seed_questions(self, exam):` |
| `apps/exams/management/commands/seed_final_exam_demo.py` | 193 | `def _make_students(self, org, owner, student_role, prefix, count, password):` |
| `apps/exams/management/commands/seed_final_exam_demo.py` | 203 | `def _ensure_group(self, org, teacher, name, students):` |
| `apps/exams/management/commands/seed_final_exam_demo.py` | 209 | `def _ensure_room(self, org, center):` |
| `apps/exams/management/commands/seed_final_exam_demo.py` | 225 | `def _ensure_local_computer(self, org, room, center):` |
| `apps/exams/management/commands/seed_final_exam_demo.py` | 241 | `def _report(self, password, org, center, invigilator, exam, session, main_group, sub_group, individual, students):` |
| `apps/exams/management/commands/seed_final_exam_demo.py` | 289 | `def _sector_label(self, student, main_group, sub_group, individual):` |
| `apps/exams/management/commands/seed_final_exam_demo.py` | 41 | `class Command(UsersSeedMixin, BaseCommand):` |
| `apps/exams/management/commands/seed_final_exam_demo.py` | 44 | `def add_arguments(self, parser):` |
| `apps/exams/management/commands/seed_final_exam_demo.py` | 50 | `def handle(self, *args, **options):` |
| `apps/exams/management/commands/seed_group_demo_data.py` | 19 | `class Command(UsersSeedMixin, CoursesSeedMixin, ExamsSeedMixin, BaseCommand):` |
| `apps/exams/management/commands/seed_group_demo_data.py` | 25 | `def add_arguments(self, parser):` |
| `apps/exams/management/commands/seed_group_demo_data.py` | 41 | `def handle(self, *args, **options):` |
| `apps/exams/migrations/0001_initial.py` | 13 | `class Migration(migrations.Migration):` |
| `apps/exams/migrations/0002_questionblock_enable_paint_examquestion_disable_paint.py` | 4 | `class Migration(migrations.Migration):` |
| `apps/exams/migrations/0003_aiconfiguration.py` | 7 | `class Migration(migrations.Migration):` |
| `apps/exams/migrations/0004_add_supervision_models.py` | 8 | `class Migration(migrations.Migration):` |
| `apps/exams/migrations/0005_alter_exam_exam_type_codingexamquestion_and_more.py` | 8 | `class Migration(migrations.Migration):` |
| `apps/exams/migrations/0006_exam_fair_distribution_ai_balance_and_question_difficulty_source.py` | 6 | `class Migration(migrations.Migration):` |
| `apps/exams/migrations/0007_alter_examquestionoption_text.py` | 4 | `class Migration(migrations.Migration):` |
| `apps/exams/migrations/0008_exam_results_hidden_from_students.py` | 4 | `class Migration(migrations.Migration):` |
| `apps/exams/migrations/0009_exam_indexes.py` | 18 | `class Migration(migrations.Migration):` |
| `apps/exams/migrations/0010_aiconfiguration_assistant_model.py` | 10 | `class Migration(migrations.Migration):` |
| `apps/exams/migrations/0011_examattempt_supervision_resumed_at_and_more.py` | 6 | `class Migration(migrations.Migration):` |
| `apps/exams/migrations/0012_examattempt_supervision_locked_at.py` | 6 | `class Migration(migrations.Migration):` |
| `apps/exams/migrations/0013_examattempt_supervision_manual_lock.py` | 6 | `class Migration(migrations.Migration):` |
| `apps/exams/migrations/0014_backfill_manual_lock_flag.py` | 10 | `def backfill_manual_lock(apps, schema_editor):` |
| `apps/exams/migrations/0014_backfill_manual_lock_flag.py` | 19 | `def noop_reverse(apps, schema_editor):` |
| `apps/exams/migrations/0014_backfill_manual_lock_flag.py` | 24 | `class Migration(migrations.Migration):` |
| `apps/exams/migrations/0015_exam_language_variant.py` | 12 | `class Migration(migrations.Migration):` |
| `apps/exams/migrations/0016_backfill_language_variants.py` | 12 | `def backfill_language_variants(apps, schema_editor):` |
| `apps/exams/migrations/0016_backfill_language_variants.py` | 29 | `def reverse_noop(apps, schema_editor):` |
| `apps/exams/migrations/0016_backfill_language_variants.py` | 35 | `class Migration(migrations.Migration):` |
| `apps/exams/migrations/0017_question_bank_library.py` | 16 | `class Migration(migrations.Migration):` |
| `apps/exams/migrations/0018_questionbank_default_question_type.py` | 4 | `class Migration(migrations.Migration):` |
| `apps/exams/migrations/0019_alter_questionbank_default_question_type.py` | 6 | `class Migration(migrations.Migration):` |
| `apps/exams/migrations/0020_examattempt_marked_question_ids.py` | 4 | `class Migration(migrations.Migration):` |
| `apps/exams/migrations/0021_examattempt_unique_constraints.py` | 18 | `def _dedupe_attempts(apps, schema_editor):` |
| `apps/exams/migrations/0021_examattempt_unique_constraints.py` | 59 | `class Migration(migrations.Migration):` |
| `apps/exams/migrations/0022_exam_archive_state.py` | 5 | `class Migration(migrations.Migration):` |
| `apps/exams/migrations/0023_option_image.py` | 5 | `class Migration(migrations.Migration):` |
| `apps/exams/migrations/0024_textextractionjob.py` | 12 | `class Migration(migrations.Migration):` |
| `apps/exams/migrations/0025_textextractionjob_kind_textextractionjob_payload_and_more.py` | 8 | `class Migration(migrations.Migration):` |
| `apps/exams/migrations/0026_textextractionjob_result_file_and_more.py` | 7 | `class Migration(migrations.Migration):` |
| `apps/exams/migrations/0027_questionsubmission.py` | 8 | `class Migration(migrations.Migration):` |
| `apps/exams/migrations/0028_questionsubmission_group_label_and_more.py` | 7 | `class Migration(migrations.Migration):` |
| `apps/exams/migrations/0029_questionsubmission_teacher_note.py` | 6 | `class Migration(migrations.Migration):` |
| `apps/exams/migrations/0030_examroom_examroomsession_finalexamticket_and_more.py` | 8 | `class Migration(migrations.Migration):` |
| `apps/exams/migrations/0031_alter_finalexamticket_language.py` | 6 | `class Migration(migrations.Migration):` |
| `apps/exams/migrations/0032_finalexamticket_reminder_stage.py` | 6 | `class Migration(migrations.Migration):` |
| `apps/exams/migrations/0033_remove_examroomsession_uniq_active_session_per_room.py` | 6 | `class Migration(migrations.Migration):` |
| `apps/exams/migrations/0034_studentgroup_subjects.py` | 6 | `class Migration(migrations.Migration):` |
| `apps/exams/migrations/0035_studentgroup_org_unit.py` | 7 | `class Migration(migrations.Migration):` |
| `apps/exams/migrations/0036_exam_subject_examstudentpin_studentexamattemptgrant.py` | 8 | `class Migration(migrations.Migration):` |
| `apps/exams/migrations/0037_examattempt_is_trial.py` | 6 | `class Migration(migrations.Migration):` |
| `apps/exams/migrations/0038_examroom_invigilators_examroomcomputer.py` | 8 | `class Migration(migrations.Migration):` |
| `apps/exams/migrations/0039_decouple_exam_from_room_session.py` | 8 | `class Migration(migrations.Migration):` |
| `apps/exams/migrations/0040_qsubmission_multi_groups 2.py` | 6 | `class Migration(migrations.Migration):` |
| `apps/exams/migrations/0040_qsubmission_multi_groups.py` | 6 | `class Migration(migrations.Migration):` |
| `apps/exams/migrations/0041_exam_excluded_users.py` | 7 | `class Migration(migrations.Migration):` |
| `apps/exams/migrations/0042_examattempt_room_examattempt_room_computer.py` | 7 | `class Migration(migrations.Migration):` |
| `apps/exams/migrations/0043_exam_deleted_at_exam_is_deleted.py` | 6 | `class Migration(migrations.Migration):` |
| `apps/exams/migrations/0044_examanswer_question_snapshot.py` | 4 | `class Migration(migrations.Migration):` |
| `apps/exams/navigation.py` | 15 | `def safe_same_origin_redirect_path(request, candidate_url):` |
| `apps/exams/navigation.py` | 30 | `def current_return_to(request):` |
| `apps/exams/navigation.py` | 40 | `def append_query_params(url, **params):` |
| `apps/exams/navigation.py` | 48 | `def append_return_to(url, return_to):` |
| `apps/exams/navigation.py` | 52 | `def build_exam_history_url(exam, return_to=""):` |
| `apps/exams/navigation.py` | 56 | `def build_exam_result_url(attempt, return_to=""):` |
| `apps/exams/score_adjustments.py` | 103 | `def student_visible_score_state(attempt):` |
| `apps/exams/score_adjustments.py` | 107 | `def student_visible_status_by_qid(attempt):` |
| `apps/exams/score_adjustments.py` | 111 | `def can_create(request, attempt):` |
| `apps/exams/score_adjustments.py` | 115 | `def remaining_window_seconds(attempt):` |
| `apps/exams/score_adjustments.py` | 18 | `def _default_bonus_map(attempt_ids):` |
| `apps/exams/score_adjustments.py` | 22 | `def _default_apply_bonus(test_result, bonus):` |
| `apps/exams/score_adjustments.py` | 26 | `def _default_effective_test_score(attempt, *, answers=None):` |
| `apps/exams/score_adjustments.py` | 30 | `def _default_score_state(attempt):` |
| `apps/exams/score_adjustments.py` | 34 | `def _default_student_visible_bonus_map(attempt_ids):` |
| `apps/exams/score_adjustments.py` | 38 | `def _default_student_visible_effective_test_score(attempt, *, answers=None):` |
| `apps/exams/score_adjustments.py` | 42 | `def _default_student_visible_score_state(attempt):` |
| `apps/exams/score_adjustments.py` | 46 | `def _default_student_visible_status_by_qid(attempt):` |
| `apps/exams/score_adjustments.py` | 50 | `def _default_can_create(request, attempt):` |
| `apps/exams/score_adjustments.py` | 54 | `def _default_remaining_window_seconds(attempt):` |
| `apps/exams/score_adjustments.py` | 72 | `def register(name, fn):` |
| `apps/exams/score_adjustments.py` | 79 | `def bonus_map(attempt_ids):` |
| `apps/exams/score_adjustments.py` | 83 | `def apply_bonus(test_result, bonus):` |
| `apps/exams/score_adjustments.py` | 87 | `def effective_test_score(attempt, *, answers=None):` |
| `apps/exams/score_adjustments.py` | 91 | `def score_state(attempt):` |
| `apps/exams/score_adjustments.py` | 95 | `def student_visible_bonus_map(attempt_ids):` |
| `apps/exams/score_adjustments.py` | 99 | `def student_visible_effective_test_score(attempt, *, answers=None):` |
| `apps/exams/services/access_policy.py` | 103 | `def ensure_can_manage_exam_rooms(user):` |
| `apps/exams/services/access_policy.py` | 109 | `def can_assign_invigilators(user):` |
| `apps/exams/services/access_policy.py` | 122 | `def can_manage_final_exam_content(user):` |
| `apps/exams/services/access_policy.py` | 126 | `def can_manage_exam_questions(user, exam):` |
| `apps/exams/services/access_policy.py` | 133 | `def ensure_can_manage_exam_questions(user, exam):` |
| `apps/exams/services/access_policy.py` | 139 | `def can_create_question_bank(user):` |
| `apps/exams/services/access_policy.py` | 143 | `def ensure_can_create_question_bank(user):` |
| `apps/exams/services/access_policy.py` | 22 | `def can_user_access_exam(exam, user):` |
| `apps/exams/services/access_policy.py` | 48 | `def _ensure_teacher(user):` |
| `apps/exams/services/access_policy.py` | 54 | `def can_view_attempt_results(user):` |
| `apps/exams/services/access_policy.py` | 65 | `def _ensure_can_view_attempt_results(user):` |
| `apps/exams/services/access_policy.py` | 7 | `def is_teacher_user(user):` |
| `apps/exams/services/access_policy.py` | 81 | `def is_exam_center_user(user):` |
| `apps/exams/services/access_policy.py` | 87 | `def can_manage_exam_rooms(user):` |
| `apps/exams/services/ai_grading.py` | 114 | `def _get_quota_info(user_id: int \| None) -> dict:` |
| `apps/exams/services/ai_grading.py` | 122 | `def _check_rate_limit(user_id: int) -> dict \| None:` |
| `apps/exams/services/ai_grading.py` | 128 | `def _record_hit(user_id: int) -> None:` |
| `apps/exams/services/ai_grading.py` | 134 | `def _round_score(value: Decimal) -> int:` |
| `apps/exams/services/ai_grading.py` | 138 | `def _parse_score_number(raw_value: str) -> Decimal \| None:` |
| `apps/exams/services/ai_grading.py` | 145 | `def _parse_ai_grade(text: str, max_points: int) -> tuple[int, str]:` |
| `apps/exams/services/ai_grading.py` | 192 | `def _normalized_text(student_answer: str) -> str:` |
| `apps/exams/services/ai_grading.py` | 196 | `def _materialize_answer_files(answer_files) -> list:` |
| `apps/exams/services/ai_grading.py` | 204 | `def _detect_mime_type(file_obj, fallback_name: str = "") -> str:` |
| `apps/exams/services/ai_grading.py` | 217 | `def _is_image_mime_type(mime_type: str) -> bool:` |
| `apps/exams/services/ai_grading.py` | 221 | `def _read_file_bytes(file_obj) -> bytes:` |
| `apps/exams/services/ai_grading.py` | 243 | `def _collect_image_inputs(*, answer_files=None, paint_image=None) -> list[dict]:` |
| `apps/exams/services/ai_grading.py` | 283 | `def has_written_answer_content(*, student_answer: str = "", answer_files=None, paint_image=None) -> bool:` |
| `apps/exams/services/ai_grading.py` | 287 | `def has_ai_gradeable_answer_content(*, student_answer: str = "", answer_files=None, paint_image=None) -> bool:` |
| `apps/exams/services/ai_grading.py` | 293 | `def _build_grading_prompt(` |
| `apps/exams/services/ai_grading.py` | 344 | `def _gemini_generate_content(*, model_name: str, api_key: str, prompt: str, image_inputs: list[dict]) -> str:` |
| `apps/exams/services/ai_grading.py` | 388 | `def grade_written_answer(` |
| `apps/exams/services/ai_grading.py` | 41 | `def _get_grading_model_chain() -> tuple[str, ...]:` |
| `apps/exams/services/ai_grading.py` | 55 | `def _is_ai_enabled() -> bool:` |
| `apps/exams/services/ai_grading.py` | 65 | `def _get_api_key() -> str \| None:` |
| `apps/exams/services/ai_grading.py` | 70 | `def _language_name(code: str) -> str:` |
| `apps/exams/services/ai_grading.py` | 80 | `def _grade_cache_key(question_text: str, student_answer: str, max_points: int, lang: str) -> str:` |
| `apps/exams/services/ai_grading.py` | 90 | `def _grade_cache_key_with_attachments(` |
| `apps/exams/services/ai_question_generation.py` | 132 | `def _build_prompt(` |
| `apps/exams/services/ai_question_generation.py` | 206 | `def _clean_label(value: str) -> str:` |
| `apps/exams/services/ai_question_generation.py` | 211 | `def _normalise_test_questions(payload: dict, question_count: int) -> list[dict]:` |
| `apps/exams/services/ai_question_generation.py` | 261 | `def _normalise_written_questions(payload: dict, question_count: int) -> list[str]:` |
| `apps/exams/services/ai_question_generation.py` | 279 | `def _render_test_questions(questions: list[dict]) -> str:` |
| `apps/exams/services/ai_question_generation.py` | 28 | `def _is_ai_enabled() -> bool:` |
| `apps/exams/services/ai_question_generation.py` | 291 | `def _render_written_questions(questions: list[str]) -> str:` |
| `apps/exams/services/ai_question_generation.py` | 295 | `def generate_question_bank_text(` |
| `apps/exams/services/ai_question_generation.py` | 37 | `def _question_model_chain() -> tuple[str, ...]:` |
| `apps/exams/services/ai_question_generation.py` | 45 | `def _language_name(code: str) -> str:` |
| `apps/exams/services/ai_question_generation.py` | 55 | `def _safe_question_count(raw_count) -> int:` |
| `apps/exams/services/ai_question_generation.py` | 63 | `def _compact_source_text(source_text: str) -> str:` |
| `apps/exams/services/ai_question_generation.py` | 70 | `def _json_from_model_text(text: str) -> dict:` |
| `apps/exams/services/ai_question_generation.py` | 95 | `def _call_gemini_text(*, prompt: str, model_chain: tuple[str, ...]) -> str:` |
| `apps/exams/services/ai_summary.py` | 100 | `def check_user_ai_rate_limit(user_id: int) -> dict \| None:` |
| `apps/exams/services/ai_summary.py` | 113 | `def get_user_ai_quota_info(user_id: int) -> dict:` |
| `apps/exams/services/ai_summary.py` | 142 | `def generate_exam_statistics_summary(` |
| `apps/exams/services/ai_summary.py` | 254 | `def _build_prompt(` |
| `apps/exams/services/ai_summary.py` | 41 | `def _get_ai_config():` |
| `apps/exams/services/ai_summary.py` | 51 | `def _get_rate_limit() -> str:` |
| `apps/exams/services/ai_summary.py` | 58 | `def _get_summary_model_chain() -> tuple[str, ...]:` |
| `apps/exams/services/ai_summary.py` | 67 | `def _is_ai_enabled() -> bool:` |
| `apps/exams/services/ai_summary.py` | 72 | `def _get_api_key() -> str \| None:` |
| `apps/exams/services/ai_summary.py` | 78 | `def _language_name(code: str) -> str:` |
| `apps/exams/services/ai_summary.py` | 88 | `def _stats_cache_key(exam_title: str, exam_type: str, stats: dict, lang: str) -> str:` |
| `apps/exams/services/attempts.py` | 124 | `def _exam_start_capacity_gate(exam_id: int):` |
| `apps/exams/services/attempts.py` | 177 | `def get_active_attempt_for_user(exam, user):` |
| `apps/exams/services/attempts.py` | 185 | `def get_finished_attempts_for_user(exam, user):` |
| `apps/exams/services/attempts.py` | 189 | `def can_user_start_new_attempt(exam, user):` |
| `apps/exams/services/attempts.py` | 201 | `def _next_attempt_number(exam, user) -> int:` |
| `apps/exams/services/attempts.py` | 206 | `def _create_attempt_or_get_active(exam, user, **extra_fields):` |
| `apps/exams/services/attempts.py` | 252 | `def create_exam_attempt(exam, user):` |
| `apps/exams/services/attempts.py` | 258 | `def submit_exam_attempt(attempt):` |
| `apps/exams/services/attempts.py` | 267 | `def _build_exam_result_url(exam, attempt, return_to):` |
| `apps/exams/services/attempts.py` | 274 | `def get_attempt_limit_result_redirect_url(request, exam: Exam, user):` |
| `apps/exams/services/attempts.py` | 295 | `def _start_or_resume_attempt(request, exam: Exam):` |
| `apps/exams/services/attempts.py` | 32 | `class ExamStartBusy(Exception):` |
| `apps/exams/services/attempts.py` | 36 | `def _exam_start_cache():` |
| `apps/exams/services/attempts.py` | 40 | `def _exam_start_wait_timeout() -> float:` |
| `apps/exams/services/attempts.py` | 44 | `def _exam_start_poll_interval() -> float:` |
| `apps/exams/services/attempts.py` | 48 | `def _exam_start_lock_lease_seconds() -> int:` |
| `apps/exams/services/attempts.py` | 52 | `def _release_capacity_counter(cache, key: str) -> None:` |
| `apps/exams/services/attempts.py` | 63 | `def _try_acquire_capacity_counter(cache, key: str, limit: int, lease_seconds: int) -> str:` |
| `apps/exams/services/attempts.py` | 86 | `def _exam_start_actor_lock(exam_id: int, user_id: int):` |
| `apps/exams/services/bank_analysis.py` | 105 | `def build_question_meta(warnings: list) -> dict:` |
| `apps/exams/services/bank_analysis.py` | 158 | `def _run_analysis(questions) -> QuestionBankAnalysis:` |
| `apps/exams/services/bank_analysis.py` | 283 | `def analyze_question_bank(exam, *, language=None) -> QuestionBankAnalysis:` |
| `apps/exams/services/bank_analysis.py` | 294 | `def analyze_bank_questions(bank, *, language=None) -> QuestionBankAnalysis:` |
| `apps/exams/services/bank_analysis.py` | 39 | `class QuestionBankAnalysis:` |
| `apps/exams/services/bank_analysis.py` | 54 | `def _empty_analysis() -> QuestionBankAnalysis:` |
| `apps/exams/services/bank_analysis.py` | 76 | `def _options_map(question) -> tuple[dict, list]:` |
| `apps/exams/services/bank_analysis.py` | 94 | `def _fingerprint(text: str, opt_map: dict) -> str:` |
| `apps/exams/services/bank_analysis.py` | 98 | `def _short_preview(text: str, length: int = 60) -> str:` |
| `apps/exams/services/bulk_workbench.py` | 112 | `def exam_question_fp_map(exam, *, language=None):` |
| `apps/exams/services/bulk_workbench.py` | 134 | `def bank_question_fp_map(bank, *, language=None):` |
| `apps/exams/services/bulk_workbench.py` | 157 | `def bank_written_text_map(bank, *, language=None):` |
| `apps/exams/services/bulk_workbench.py` | 172 | `def exam_written_text_map(exam, *, language=None):` |
| `apps/exams/services/bulk_workbench.py` | 190 | `def analyze_mcq_bulk(raw_text, *, existing_fp_map=None, already_msg_key="already_in_exam"):` |
| `apps/exams/services/bulk_workbench.py` | 361 | `def _detect_length_bias(parsed):` |
| `apps/exams/services/bulk_workbench.py` | 37 | `def fingerprint_parsed(question: dict) -> str:` |
| `apps/exams/services/bulk_workbench.py` | 415 | `def parse_written_bulk(raw_text):` |
| `apps/exams/services/bulk_workbench.py` | 43 | `def fingerprint_from_texts(text: str, option_texts) -> str:` |
| `apps/exams/services/bulk_workbench.py` | 443 | `def analyze_written_bulk(raw_text, *, existing_text_map=None):` |
| `apps/exams/services/bulk_workbench.py` | 51 | `def _short_preview(text: str, length: int = 60) -> str:` |
| `apps/exams/services/bulk_workbench.py` | 62 | `def parse_selected_indices(post_data):` |
| `apps/exams/services/bulk_workbench.py` | 95 | `def parse_points_payload(post_data):` |
| `apps/exams/services/coding_definition.py` | 108 | `def build_coding_payload_from_question_form(cleaned_data):` |
| `apps/exams/services/coding_definition.py` | 127 | `def sync_coding_test_cases(coding_question, *, visible_cases, hidden_cases):` |
| `apps/exams/services/coding_definition.py` | 147 | `def upsert_coding_question(exam, *, payload, visible_cases=None, hidden_cases=None, base_question=None):` |
| `apps/exams/services/coding_definition.py` | 19 | `def _next_question_order(exam):` |
| `apps/exams/services/coding_definition.py` | 24 | `def _question_title(question):` |
| `apps/exams/services/coding_definition.py` | 30 | `def _question_time_limit(question):` |
| `apps/exams/services/coding_definition.py` | 38 | `def build_coding_payload_from_exam_question(question):` |
| `apps/exams/services/coding_definition.py` | 57 | `def ensure_coding_question_for_exam_question(question, *, sync_existing=False):` |
| `apps/exams/services/coding_definition.py` | 84 | `def sync_coding_questions_for_exam(exam):` |
| `apps/exams/services/coding_definition.py` | 89 | `def build_coding_payload_from_exam_form(cleaned_data):` |
| `apps/exams/services/coding_polyfills.py` | 68 | `def javascript_main_has_top_level_input_loop(content: str) -> bool:` |
| `apps/exams/services/coding_runtime/_shared.py` | 18 | `class ExecutionResult:` |
| `apps/exams/services/coding_runtime/_shared.py` | 26 | `def get_first_coding_question(exam):` |
| `apps/exams/services/coding_runtime/_shared.py` | 36 | `def sanitize_filename(filename):` |
| `apps/exams/services/coding_runtime/_shared.py` | 43 | `def truncate_capture(value):` |
| `apps/exams/services/coding_runtime/_shared.py` | 56 | `def normalize_output(value):` |
| `apps/exams/services/coding_runtime/execution.py` | 102 | `def _container_command(language, files):` |
| `apps/exams/services/coding_runtime/execution.py` | 123 | `def _docker_available():` |
| `apps/exams/services/coding_runtime/execution.py` | 146 | `def _resolve_execution_backend(language):` |
| `apps/exams/services/coding_runtime/execution.py` | 167 | `def execute_code(*, language, files, stdin, time_limit_seconds, memory_limit_mb):` |
| `apps/exams/services/coding_runtime/execution.py` | 283 | `def _piston_endpoint():` |
| `apps/exams/services/coding_runtime/execution.py` | 288 | `def _piston_files_payload(language, files):` |
| `apps/exams/services/coding_runtime/execution.py` | 315 | `def _execute_via_piston(*, language, files, stdin, time_limit_seconds, memory_limit_mb):` |
| `apps/exams/services/coding_runtime/execution.py` | 32 | `def _is_docker_pull_noise(line):` |
| `apps/exams/services/coding_runtime/execution.py` | 55 | `def clean_docker_stderr(value):` |
| `apps/exams/services/coding_runtime/execution.py` | 61 | `def _ensure_docker_image(image):` |
| `apps/exams/services/coding_runtime/execution.py` | 96 | `def _write_files(workspace, files):` |
| `apps/exams/services/coding_runtime/files.py` | 106 | `def _line_bracket_delta(line):` |
| `apps/exams/services/coding_runtime/files.py` | 111 | `def normalize_python_indentation(content):` |
| `apps/exams/services/coding_runtime/files.py` | 170 | `def normalize_files(files, *, coding_question):` |
| `apps/exams/services/coding_runtime/files.py` | 18 | `def file_language_for_name(filename, fallback_language):` |
| `apps/exams/services/coding_runtime/files.py` | 216 | `def get_main_file(files):` |
| `apps/exams/services/coding_runtime/files.py` | 220 | `def mark_file_as_main(files, filename):` |
| `apps/exams/services/coding_runtime/files.py` | 229 | `def _cpp_contains_main(content):` |
| `apps/exams/services/coding_runtime/files.py` | 233 | `def _wrap_cpp_snippet(content):` |
| `apps/exams/services/coding_runtime/files.py` | 259 | `def prepare_files_for_execution(language, files):` |
| `apps/exams/services/coding_runtime/files.py` | 35 | `def execution_language_for_filename(filename, fallback_language):` |
| `apps/exams/services/coding_runtime/files.py` | 43 | `def default_starter_code(language):` |
| `apps/exams/services/coding_runtime/files.py` | 51 | `def build_starter_files(coding_question):` |
| `apps/exams/services/coding_runtime/files.py` | 91 | `def _line_has_unclosed_triple_quote(line, current_quote=None):` |
| `apps/exams/services/coding_runtime/grading.py` | 16 | `def _facade_execute_code():` |
| `apps/exams/services/coding_runtime/grading.py` | 25 | `def run_visible_code(*, coding_question, selected_language, files, stdin=""):` |
| `apps/exams/services/coding_runtime/grading.py` | 81 | `def grade_files_against_tests(*, coding_question, selected_language, files, include_hidden):` |
| `apps/exams/services/coding_runtime/submission.py` | 13 | `def create_or_update_draft_submission(*, attempt, coding_question, selected_language, files):` |
| `apps/exams/services/coding_runtime/submission.py` | 57 | `def create_final_submission(*, attempt, coding_question, selected_language, files):` |
| `apps/exams/services/coding_runtime/submission.py` | 78 | `def sync_submission_files(submission, files):` |
| `apps/exams/services/coding_throttle.py` | 145 | `def release_run_slot(token: Optional[str]) -> None:` |
| `apps/exams/services/coding_throttle.py` | 46 | `class ThrottleDecision:` |
| `apps/exams/services/coding_throttle.py` | 53 | `def _rate_limit_per_minute() -> int:` |
| `apps/exams/services/coding_throttle.py` | 62 | `def _max_concurrent_per_user() -> int:` |
| `apps/exams/services/coding_throttle.py` | 71 | `def _bucket_key(user_id: int) -> str:` |
| `apps/exams/services/coding_throttle.py` | 78 | `def _concurrency_key(user_id: int) -> str:` |
| `apps/exams/services/coding_throttle.py` | 82 | `def _slot_key(token: str) -> str:` |
| `apps/exams/services/coding_throttle.py` | 86 | `def acquire_run_slot(*, user_id: int) -> ThrottleDecision:` |
| `apps/exams/services/difficulty.py` | 112 | `def classify_question_difficulties_with_ai(exam, questions: list[ExamQuestion]) -> dict[int, str]:` |
| `apps/exams/services/difficulty.py` | 122 | `def ensure_ai_question_difficulties(exam, *, force: bool = False) -> int:` |
| `apps/exams/services/difficulty.py` | 172 | `def _set_ai_balance_status(exam_pk: int, *, status: str, updated_count: int \| None = None, error: str = "") -> None:` |
| `apps/exams/services/difficulty.py` | 191 | `def warm_ai_question_difficulties_for_exam(*, exam_pk: int, force: bool = False) -> int:` |
| `apps/exams/services/difficulty.py` | 217 | `def schedule_ai_question_difficulty_warmup(exam, *, force: bool = False) -> bool:` |
| `apps/exams/services/difficulty.py` | 25 | `def _normalise_difficulty(value) -> str:` |
| `apps/exams/services/difficulty.py` | 43 | `def _question_payload(question: ExamQuestion) -> dict:` |
| `apps/exams/services/difficulty.py` | 60 | `def _build_difficulty_prompt(exam, questions: list[ExamQuestion]) -> str:` |
| `apps/exams/services/difficulty.py` | 83 | `def _parse_difficulty_payload(payload: dict) -> dict[int, str]:` |
| `apps/exams/services/duplication.py` | 38 | `def _clone_supervision_config(source_exam: Exam, target_exam: Exam) -> None:` |
| `apps/exams/services/duplication.py` | 59 | `def duplicate_exam(*, exam: Exam, user, title_suffix: str = " (kopya)") -> Exam:` |
| `apps/exams/services/exam_center_gate.py` | 126 | `def room_ip_access_allowed(request, room) -> bool:` |
| `apps/exams/services/exam_center_gate.py` | 168 | `def org_computer_access_allowed(request, organization) -> bool:` |
| `apps/exams/services/exam_center_gate.py` | 207 | `def exam_room_isolation_allowed(exam, room) -> bool:` |
| `apps/exams/services/exam_center_gate.py` | 244 | `def resolve_room_computer(request, organization):` |
| `apps/exams/services/exam_center_gate.py` | 30 | `def mac_enforcement_active() -> bool:` |
| `apps/exams/services/exam_center_gate.py` | 35 | `def resolve_client_mac(request) -> str \| None:` |
| `apps/exams/services/exam_center_gate.py` | 71 | `def get_client_ip(request) -> str:` |
| `apps/exams/services/exam_center_gate.py` | 90 | `def _allowed_entries():` |
| `apps/exams/services/exam_center_gate.py` | 94 | `def final_exam_access_allowed(request) -> bool:` |
| `apps/exams/services/exam_definition.py` | 1 | `def effective_random_question_count(exam) -> int:` |
| `apps/exams/services/final_center/cabinet.py` | 16 | `def student_final_exam_context(user, exam) -> dict:` |
| `apps/exams/services/final_center/entry.py` | 104 | `def validate_entry(request, username: str, raw_pin: str):` |
| `apps/exams/services/final_center/entry.py` | 168 | `def _log_suspicious(request, ticket, label: str) -> None:` |
| `apps/exams/services/final_center/entry.py` | 182 | `def store_entry_session(request, ticket) -> None:` |
| `apps/exams/services/final_center/entry.py` | 186 | `def entry_ticket_id(request):` |
| `apps/exams/services/final_center/entry.py` | 190 | `def clear_entry_session(request) -> None:` |
| `apps/exams/services/final_center/entry.py` | 199 | `def ensure_open_room_sitting(room):` |
| `apps/exams/services/final_center/entry.py` | 231 | `def ensure_pin_ticket(exam, student, room, computer=None):` |
| `apps/exams/services/final_center/entry.py` | 268 | `def attach_ticket_to_room_sitting(ticket, room, computer=None):` |
| `apps/exams/services/final_center/entry.py` | 53 | `def _rate_key(kind: str, value: str) -> str:` |
| `apps/exams/services/final_center/entry.py` | 57 | `def _rate_limited(request, username: str) -> bool:` |
| `apps/exams/services/final_center/entry.py` | 77 | `def _candidate_tickets(user):` |
| `apps/exams/services/final_center/events.py` | 22 | `def staff_group(session_id: int) -> str:` |
| `apps/exams/services/final_center/events.py` | 26 | `def students_group(session_id: int) -> str:` |
| `apps/exams/services/final_center/events.py` | 30 | `def ticket_group(ticket_id: int) -> str:` |
| `apps/exams/services/final_center/events.py` | 34 | `def _group_send(group_name: str, payload: dict) -> None:` |
| `apps/exams/services/final_center/events.py` | 47 | `def broadcast_to_staff(session_id: int, payload: dict) -> None:` |
| `apps/exams/services/final_center/events.py` | 51 | `def broadcast_to_students(session_id: int, payload: dict) -> None:` |
| `apps/exams/services/final_center/events.py` | 55 | `def notify_ticket(ticket_id: int, payload: dict) -> None:` |
| `apps/exams/services/final_center/history.py` | 38 | `def _base_code(reason):` |
| `apps/exams/services/final_center/history.py` | 50 | `def _detail(code, log, extra):` |
| `apps/exams/services/final_center/history.py` | 78 | `def session_history(session):` |
| `apps/exams/services/final_center/monitor.py` | 149 | `def room_live_sessions(room):` |
| `apps/exams/services/final_center/monitor.py` | 165 | `def _room_attempt_rows(room):` |
| `apps/exams/services/final_center/monitor.py` | 221 | `def room_monitor_snapshot(room):` |
| `apps/exams/services/final_center/monitor.py` | 315 | `def session_list_annotations(queryset):` |
| `apps/exams/services/final_center/monitor.py` | 35 | `def _visible_grid_tickets(tickets):` |
| `apps/exams/services/final_center/monitor.py` | 62 | `def _ticket_row(ticket, presence, exam_title=None):` |
| `apps/exams/services/final_center/monitor.py` | 96 | `def session_monitor_snapshot(session):` |
| `apps/exams/services/final_center/permissions.py` | 101 | `def can_view_final_history(user, organization) -> bool:` |
| `apps/exams/services/final_center/permissions.py` | 123 | `def ensure_can_view_final_history(user, organization) -> None:` |
| `apps/exams/services/final_center/permissions.py` | 129 | `def user_supervises_final_sessions(user) -> bool:` |
| `apps/exams/services/final_center/permissions.py` | 22 | `def can_manage_final_center(user) -> bool:` |
| `apps/exams/services/final_center/permissions.py` | 26 | `def ensure_can_manage_final_center(user) -> None:` |
| `apps/exams/services/final_center/permissions.py` | 32 | `def can_supervise_session(user, session) -> bool:` |
| `apps/exams/services/final_center/permissions.py` | 49 | `def ensure_can_supervise_session(user, session) -> None:` |
| `apps/exams/services/final_center/permissions.py` | 55 | `def supervised_sessions_q(user) -> Q:` |
| `apps/exams/services/final_center/permissions.py` | 64 | `def sessions_visible_to(user, base_queryset):` |
| `apps/exams/services/final_center/permissions.py` | 75 | `def ensure_ticket_owner(user, ticket) -> None:` |
| `apps/exams/services/final_center/permissions.py` | 81 | `def user_is_org_member(user, organization_id) -> bool:` |
| `apps/exams/services/final_center/permissions.py` | 91 | `def can_supervise_session_ws(user, session) -> bool:` |
| `apps/exams/services/final_center/pins.py` | 108 | `def decrypt_ticket_pin(ticket) -> str \| None:` |
| `apps/exams/services/final_center/pins.py` | 118 | `def student_visible_pin(ticket) -> str \| None:` |
| `apps/exams/services/final_center/pins.py` | 140 | `def verify_ticket_pin(ticket, raw_pin: str) -> bool:` |
| `apps/exams/services/final_center/pins.py` | 174 | `def equalize_verification_timing(raw_pin: str) -> None:` |
| `apps/exams/services/final_center/pins.py` | 36 | `def _pin_length() -> int:` |
| `apps/exams/services/final_center/pins.py` | 40 | `def _fernet() -> Fernet:` |
| `apps/exams/services/final_center/pins.py` | 45 | `def generate_pin_value() -> str:` |
| `apps/exams/services/final_center/pins.py` | 50 | `def _pin_expiry_for(exam):` |
| `apps/exams/services/final_center/pins.py` | 61 | `def set_ticket_pin(ticket, by_user, *, save=True) -> str:` |
| `apps/exams/services/final_center/pins.py` | 92 | `def revoke_ticket_pin(ticket, *, save=True) -> None:` |
| `apps/exams/services/final_center/pins.py` | 99 | `def wipe_ticket_pin_cipher(ticket, *, save=True) -> None:` |
| `apps/exams/services/final_center/presence.py` | 23 | `def _key(session_id: int, ticket_id: int) -> str:` |
| `apps/exams/services/final_center/presence.py` | 27 | `def touch_presence(session_id: int, ticket_id: int, *, status: str = "waiting") -> None:` |
| `apps/exams/services/final_center/presence.py` | 35 | `def drop_presence(session_id: int, ticket_id: int) -> None:` |
| `apps/exams/services/final_center/presence.py` | 39 | `def presence_map(session_id: int, ticket_ids) -> dict:` |
| `apps/exams/services/final_center/presence.py` | 49 | `def connected_count(session_id: int, ticket_ids) -> int:` |
| `apps/exams/services/final_center/presence.py` | 53 | `def touch_ticket_last_seen(ticket) -> None:` |
| `apps/exams/services/final_center/reminders.py` | 22 | `def _thresholds():` |
| `apps/exams/services/final_center/reminders.py` | 28 | `def _smallest_applicable(days_left, thresholds):` |
| `apps/exams/services/final_center/reminders.py` | 37 | `def notify_upcoming_final_exams(now=None) -> int:` |
| `apps/exams/services/final_center/reminders.py` | 91 | `def _reminder_title(threshold: int) -> str:` |
| `apps/exams/services/final_center/reminders.py` | 99 | `def _reminder_message(ticket, threshold: int) -> str:` |
| `apps/exams/services/final_center/reports.py` | 15 | `def filter_sessions(organization, params):` |
| `apps/exams/services/final_center/reports.py` | 46 | `def filter_tickets(organization, params):` |
| `apps/exams/services/final_center/room_admin.py` | 101 | `def update_computer(` |
| `apps/exams/services/final_center/room_admin.py` | 145 | `def bulk_add_computers(*, room: ExamRoom, text: str, user=None) -> tuple[int, list[str]]:` |
| `apps/exams/services/final_center/room_admin.py` | 20 | `class RoomAdminError(ValueError):` |
| `apps/exams/services/final_center/room_admin.py` | 24 | `def _clean_ip(raw: str) -> str:` |
| `apps/exams/services/final_center/room_admin.py` | 40 | `def _normalize_mac_or_error(raw: str) -> str:` |
| `apps/exams/services/final_center/room_admin.py` | 49 | `def _coerce_seat(raw) -> int \| None:` |
| `apps/exams/services/final_center/room_admin.py` | 64 | `def add_computer(` |
| `apps/exams/services/final_center/sessions.py` | 107 | `def start_room(session, by, *, request=None, override=False) -> bool:` |
| `apps/exams/services/final_center/sessions.py` | 166 | `def _finalize_session_attempts(session) -> dict:` |
| `apps/exams/services/final_center/sessions.py` | 185 | `def end_room(session, by, *, request=None, auto=False) -> bool:` |
| `apps/exams/services/final_center/sessions.py` | 233 | `def cancel_session(session, by, *, request=None, reason="") -> bool:` |
| `apps/exams/services/final_center/sessions.py` | 257 | `def maybe_auto_end(session) -> bool:` |
| `apps/exams/services/final_center/sessions.py` | 42 | `class RoomSessionStateError(ValueError):` |
| `apps/exams/services/final_center/sessions.py` | 46 | `def _audit_session(session, *, action, user=None, request=None, reason="", changes=None):` |
| `apps/exams/services/final_center/sessions.py` | 61 | `def validate_session_plan(*, room, scheduled_start, scheduled_end, exclude_pk=None):` |
| `apps/exams/services/final_center/sessions.py` | 78 | `def _live_ticket_ids(session):` |
| `apps/exams/services/final_center/sessions.py` | 86 | `def open_entry(session, by, *, request=None) -> bool:` |
| `apps/exams/services/final_center/tickets.py` | 129 | `def _notify_assignment(exam, tickets):` |
| `apps/exams/services/final_center/tickets.py` | 153 | `def regenerate_pin(ticket, by, *, request=None) -> str:` |
| `apps/exams/services/final_center/tickets.py` | 168 | `def set_seat(ticket, seat_number, by, *, request=None) -> None:` |
| `apps/exams/services/final_center/tickets.py` | 187 | `def resolve_ticket_language(ticket, requested_language):` |
| `apps/exams/services/final_center/tickets.py` | 203 | `def enter_waiting(ticket, *, language, request=None) -> bool:` |
| `apps/exams/services/final_center/tickets.py` | 238 | `def set_ready(ticket, ready: bool) -> bool:` |
| `apps/exams/services/final_center/tickets.py` | 250 | `def student_cancel_waiting(ticket, *, request=None) -> bool:` |
| `apps/exams/services/final_center/tickets.py` | 265 | `def begin_attempt_for_ticket(ticket):` |
| `apps/exams/services/final_center/tickets.py` | 325 | `def sync_ticket_completion(ticket) -> bool:` |
| `apps/exams/services/final_center/tickets.py` | 350 | `def remove_student(ticket, by, *, action="removed", reason="", allow_reentry=False, request=None) -> bool:` |
| `apps/exams/services/final_center/tickets.py` | 37 | `class TicketStateError(ValueError):` |
| `apps/exams/services/final_center/tickets.py` | 41 | `def _audit_ticket(ticket, *, action, user=None, request=None, reason="", changes=None):` |
| `apps/exams/services/final_center/tickets.py` | 429 | `def readmit_student(ticket, by, *, request=None) -> bool:` |
| `apps/exams/services/final_center/tickets.py` | 56 | `def transition_ticket(ticket, new_status, *, extra_updates=None) -> bool:` |
| `apps/exams/services/final_center/tickets.py` | 79 | `def assign_students(exam, students, by, *, request=None):` |
| `apps/exams/services/grading.py` | 19 | `def grade_exam_answer(answer, score, graded_by=None, feedback=None):` |
| `apps/exams/services/grading.py` | 36 | `def bulk_grade_answers(answer_ids, scores, graded_by=None):` |
| `apps/exams/services/grading.py` | 53 | `def parse_score_value(value, *, default=None):` |
| `apps/exams/services/grading.py` | 8 | `def calculate_attempt_score(attempt):` |
| `apps/exams/services/import_media.py` | 115 | `def _assign_image(instance, path: Path) -> None:` |
| `apps/exams/services/import_media.py` | 123 | `def clear_stash(token: str) -> None:` |
| `apps/exams/services/import_media.py` | 42 | `def _stash_root() -> Path:` |
| `apps/exams/services/import_media.py` | 46 | `def _safe_dir(token: str) -> Path \| None:` |
| `apps/exams/services/import_media.py` | 52 | `def _png_name(q_no: str, label: str \| None) -> str:` |
| `apps/exams/services/import_media.py` | 58 | `def stash_math_images(uploaded_file) -> str \| None:` |
| `apps/exams/services/import_media.py` | 87 | `def attach_math_images(token: str, q_no: str, question) -> None:` |
| `apps/exams/services/language_variants.py` | 104 | `def effective_needed_count_for_attempt(attempt):` |
| `apps/exams/services/language_variants.py` | 132 | `def create_variant(exam, language, *, display_name="", question_count_override=None, is_active=True):` |
| `apps/exams/services/language_variants.py` | 161 | `def set_variant_active(variant, is_active):` |
| `apps/exams/services/language_variants.py` | 167 | `def ensure_default_variant(exam, language=DEFAULT_EXAM_LANGUAGE):` |
| `apps/exams/services/language_variants.py` | 177 | `def create_questions_for_variant(exam, language, parsed_questions, *, default_points=1):` |
| `apps/exams/services/language_variants.py` | 26 | `def language_label(code):` |
| `apps/exams/services/language_variants.py` | 30 | `def active_variants(exam):` |
| `apps/exams/services/language_variants.py` | 35 | `def get_active_variant(exam, language):` |
| `apps/exams/services/language_variants.py` | 41 | `def scoped_active_questions(exam, language=None):` |
| `apps/exams/services/language_variants.py` | 53 | `def available_language_options(exam):` |
| `apps/exams/services/language_variants.py` | 77 | `def exam_is_multilingual(exam):` |
| `apps/exams/services/language_variants.py` | 82 | `def resolve_requested_language(exam, requested):` |
| `apps/exams/services/language_variants.py` | 93 | `def auto_language_for_attempt(exam):` |
| `apps/exams/services/parsing/_core.py` | 121 | `def _question_line_index(lines: list[str]) -> int:` |
| `apps/exams/services/parsing/_core.py` | 132 | `def _looks_like_question_prompt(line: str) -> bool:` |
| `apps/exams/services/parsing/_core.py` | 179 | `def _split_unlabeled_question_and_options(lines: list[str], q_idx: int) -> tuple[list[str], list[str]]:` |
| `apps/exams/services/parsing/_core.py` | 193 | `def _parse_unlabeled_end_question_block(lines: list[str], fallback_no: int) -> dict \| None:` |
| `apps/exams/services/parsing/_core.py` | 212 | `def _parse_labeled_end_question_block(lines: list[str], fallback_no: int) -> dict \| None:` |
| `apps/exams/services/parsing/_core.py` | 255 | `def _parse_end_question_blocks(raw_text: str) -> list[dict]:` |
| `apps/exams/services/parsing/_core.py` | 259 | `def flush_block() -> None:` |
| `apps/exams/services/parsing/_core.py` | 275 | `def _block_has_option(current_block):` |
| `apps/exams/services/parsing/_core.py` | 302 | `def _add_warning(q: dict, w_type: str, msg: str, severity: str = SEVERITY_WARNING, **extra) -> None:` |
| `apps/exams/services/parsing/_core.py` | 308 | `def _validate_questions(questions: list[dict]) -> None:` |
| `apps/exams/services/parsing/_core.py` | 32 | `def _isolate_end_question_markers(raw_text: str) -> str:` |
| `apps/exams/services/parsing/_core.py` | 38 | `def _new_question(q_no: str, text: str) -> dict:` |
| `apps/exams/services/parsing/_core.py` | 407 | `def parse_bulk_mcq(raw_text: str):` |
| `apps/exams/services/parsing/_core.py` | 441 | `def close_option():` |
| `apps/exams/services/parsing/_core.py` | 445 | `def close_question():` |
| `apps/exams/services/parsing/_core.py` | 49 | `def _strip_question_number(line: str, fallback_no: int) -> tuple[str, str]:` |
| `apps/exams/services/parsing/_core.py` | 56 | `def _finish_question(current: dict \| None) -> dict \| None:` |
| `apps/exams/services/parsing/_core.py` | 80 | `def _is_option_continuation(line: str) -> bool:` |
| `apps/exams/services/parsing/_core.py` | 86 | `def _coerce_unlabeled_options(option_lines: list[str]) -> list[str]:` |
| `apps/exams/services/parsing/extraction/highlight.py` | 101 | `def _extract_pdf_highlights(uploaded_file) -> list[str]:` |
| `apps/exams/services/parsing/extraction/highlight.py` | 147 | `def _pdf_has_text_layer(uploaded_file) -> bool \| None:` |
| `apps/exams/services/parsing/extraction/highlight.py` | 15 | `def _highlight_core(text: str) -> str:` |
| `apps/exams/services/parsing/extraction/highlight.py` | 175 | `def _build_yellow_mask(pil_image):` |
| `apps/exams/services/parsing/extraction/highlight.py` | 186 | `def at_least(channel, threshold):` |
| `apps/exams/services/parsing/extraction/highlight.py` | 202 | `def _line_yellow_ratio(mask, bbox) -> float:` |
| `apps/exams/services/parsing/extraction/highlight.py` | 20 | `def _frag_label_and_core(fragment: str) -> tuple[str \| None, str]:` |
| `apps/exams/services/parsing/extraction/highlight.py` | 216 | `def _word_bbox(word, zoom: float, mask_w: int, mask_h: int) -> tuple[int, int, int, int]:` |
| `apps/exams/services/parsing/extraction/highlight.py` | 225 | `def _line_words_have_yellow(mask, line_words, zoom: float, min_ratio: float, mask_w: int, mask_h: int) -> bool:` |
| `apps/exams/services/parsing/extraction/highlight.py` | 28 | `def _fragment_matches_option(frag_label, frag_core, opt_label, opt_core) -> bool:` |
| `apps/exams/services/parsing/extraction/highlight.py` | 42 | `def _mark_correct_option_lines(text: str, highlight_fragments: list[str]) -> str:` |
| `apps/exams/services/parsing/extraction/highlight.py` | 64 | `def _mark_correct_options_by_position(text: str, correct_map: dict) -> str:` |
| `apps/exams/services/parsing/extraction/normalize.py` | 110 | `def normalize_pdf_extracted_text(text: str) -> str:` |
| `apps/exams/services/parsing/extraction/normalize.py` | 21 | `def _normalize_cyrillic_option_labels(text: str) -> str:` |
| `apps/exams/services/parsing/extraction/normalize.py` | 32 | `def _label_repl(match):` |
| `apps/exams/services/parsing/extraction/normalize.py` | 38 | `def _answer_repl(match):` |
| `apps/exams/services/parsing/extraction/normalize.py` | 46 | `def _merge_bare_question_numbers(text: str) -> str:` |
| `apps/exams/services/parsing/extraction/normalize.py` | 79 | `def _convert_marker_options(text: str) -> str:` |
| `apps/exams/services/parsing/extraction/ocr.py` | 123 | `def _ocr_image_text(uploaded_file) -> str:` |
| `apps/exams/services/parsing/extraction/ocr.py` | 172 | `def _ocr_page_text_with_highlights(page, textpage, zoom, detect_highlight, min_ratio, Image, dpi) -> str:` |
| `apps/exams/services/parsing/extraction/ocr.py` | 24 | `def _ensure_tessdata_prefix() -> None:` |
| `apps/exams/services/parsing/extraction/ocr.py` | 43 | `def _ocr_pdf_text(uploaded_file) -> str:` |
| `apps/exams/services/parsing/extraction/pipeline.py` | 32 | `def extract_text_from_upload(uploaded_file) -> str:` |
| `apps/exams/services/parsing/extraction/safety.py` | 10 | `def _ensure_within_size_limit(uploaded_file, limit: int) -> None:` |
| `apps/exams/services/parsing/extraction/safety.py` | 15 | `def _peek_magic_bytes(uploaded_file, length: int = 8) -> bytes:` |
| `apps/exams/services/parsing/extraction/safety.py` | 29 | `def _verify_magic_bytes(head: bytes, expected_key: str) -> bool:` |
| `apps/exams/services/parsing/extraction/safety.py` | 34 | `def _pdf_safety_check(uploaded_file) -> None:` |
| `apps/exams/services/pdf_math.py` | 217 | `def remap_symbol_pua(text: str) -> str:` |
| `apps/exams/services/pdf_math.py` | 227 | `def _translate(ch: str) -> str:` |
| `apps/exams/services/pdf_math.py` | 249 | `def _iter_pages(doc):` |
| `apps/exams/services/pdf_math.py` | 263 | `def _has_structural_glyph(text: str) -> bool:` |
| `apps/exams/services/pdf_math.py` | 267 | `def _iter_text_lines(page):` |
| `apps/exams/services/pdf_math.py` | 278 | `def _build_anchors(lines):` |
| `apps/exams/services/pdf_math.py` | 301 | `def _owner_for_y(center_y: float, anchors):` |
| `apps/exams/services/pdf_math.py` | 315 | `def _regions_by_owner(lines, anchors):` |
| `apps/exams/services/pdf_math.py` | 339 | `def _render_region(page, region: "fitz.Rect") -> bytes:` |
| `apps/exams/services/pdf_math.py` | 353 | `def extract_math_images(file_or_bytes) -> dict[str, dict]:` |
| `apps/exams/services/pdf_math.py` | 425 | `def _is_yellow_fill(fill) -> bool:` |
| `apps/exams/services/pdf_math.py` | 430 | `def _highlight_rects(page) -> list:` |
| `apps/exams/services/pdf_math.py` | 455 | `def _vertical_overlap(a, b) -> float:` |
| `apps/exams/services/pdf_math.py` | 459 | `def extract_correct_labels(file_or_bytes) -> dict[str, set]:` |
| `apps/exams/services/pdf_math.py` | 515 | `def _read_bytes(file_or_bytes) -> bytes:` |
| `apps/exams/services/question_bank.py` | 4 | `def normalize_question_text(text: str) -> str:` |
| `apps/exams/services/question_bank_attach.py` | 134 | `def _duplicate_filefield(source_fieldfile, target_instance, target_field_name):` |
| `apps/exams/services/question_bank_attach.py` | 161 | `def attach_bank_questions_to_exam(exam, bank_question_ids, *, block=None, created_by=None, default_points=None):` |
| `apps/exams/services/question_bank_attach.py` | 35 | `def _question_fingerprint(text):` |
| `apps/exams/services/question_bank_attach.py` | 43 | `def accessible_banks(user, organization, *, include_shared=True):` |
| `apps/exams/services/question_bank_attach.py` | 55 | `def bank_questions_queryset(` |
| `apps/exams/services/question_bank_attach.py` | 83 | `def count_bank_questions(bank, **filters):` |
| `apps/exams/services/question_bank_attach.py` | 88 | `def create_bank_questions_from_parsed(` |
| `apps/exams/services/question_submission.py` | 100 | `def submit_question_set(` |
| `apps/exams/services/question_submission.py` | 145 | `def resubmit_question_set(` |
| `apps/exams/services/question_submission.py` | 198 | `def ensure_can_review_submission(user, submission):` |
| `apps/exams/services/question_submission.py` | 206 | `def accept_submission(submission, *, reviewer, bank=None, new_bank_name="", note=""):` |
| `apps/exams/services/question_submission.py` | 265 | `def reject_submission(submission, *, reviewer, note=""):` |
| `apps/exams/services/question_submission.py` | 281 | `def _exam_center_members(organization):` |
| `apps/exams/services/question_submission.py` | 294 | `def _notify_exam_center_new_submission(submission, *, resubmitted):` |
| `apps/exams/services/question_submission.py` | 29 | `def analyze_submission_text(raw_text):` |
| `apps/exams/services/question_submission.py` | 332 | `def _notify_teacher_decision(submission):` |
| `apps/exams/services/question_submission.py` | 47 | `def clean_snapshot_entries(parsed):` |
| `apps/exams/services/question_submission.py` | 60 | `def _snapshot_counts(parsed):` |
| `apps/exams/services/question_submission.py` | 78 | `def _apply_snapshot(submission, raw_text, *, parsed=None):` |
| `apps/exams/services/question_word_export.py` | 28 | `def _question_lines(index, text, options):` |
| `apps/exams/services/question_word_export.py` | 41 | `def build_questions_docx(*, title, questions, subtitle=""):` |
| `apps/exams/services/question_word_export.py` | 79 | `def bank_questions_payload(bank, *, language=None, only_active=True):` |
| `apps/exams/services/question_word_export.py` | 97 | `def exam_questions_payload(exam, *, language=None):` |
| `apps/exams/services/randomizer.py` | 119 | `def _historical_question_usage(exam, attempt):` |
| `apps/exams/services/randomizer.py` | 120 | `def build_counts():` |
| `apps/exams/services/randomizer.py` | 132 | `def _historical_block_usage(exam, attempt):` |
| `apps/exams/services/randomizer.py` | 133 | `def build_counts():` |
| `apps/exams/services/randomizer.py` | 145 | `def _normalise_difficulty(value):` |
| `apps/exams/services/randomizer.py` | 150 | `def _build_difficulty_targets(questions, total_needed):` |
| `apps/exams/services/randomizer.py` | 186 | `def _difficulty_penalty(question, difficulty_targets, use_difficulty_balance):` |
| `apps/exams/services/randomizer.py` | 18 | `def available_question_count(exam) -> int:` |
| `apps/exams/services/randomizer.py` | 194 | `def _question_rank(` |
| `apps/exams/services/randomizer.py` | 213 | `def _pick_questions(` |
| `apps/exams/services/randomizer.py` | 253 | `def generate_random_questions_for_attempt(attempt, *, force_rebuild: bool = False):` |
| `apps/exams/services/randomizer.py` | 31 | `def _usage_cache_seconds() -> int:` |
| `apps/exams/services/randomizer.py` | 38 | `def _cached_usage_counts(cache_key: str, builder):` |
| `apps/exams/services/randomizer.py` | 59 | `def build_shuffled_options(attempt_id, question):` |
| `apps/exams/services/randomizer.py` | 77 | `def _build_block_pick_plan(blocks, total_needed):` |
| `apps/exams/services/randomizer.py` | 98 | `def _build_fair_block_pick_plan(blocks, total_needed, block_usage_counts):` |
| `apps/exams/services/result_calculation.py` | 12 | `def _format_decimal(value):` |
| `apps/exams/services/result_calculation.py` | 136 | `def sync_test_attempt_counts(attempt, *, answers=None):` |
| `apps/exams/services/result_calculation.py` | 144 | `def attach_test_result_summaries(attempts, *, bonus_map_fn=None):` |
| `apps/exams/services/result_calculation.py` | 19 | `def _percentage(score, max_score):` |
| `apps/exams/services/result_calculation.py` | 26 | `def _option_ids(option_manager):` |
| `apps/exams/services/result_calculation.py` | 31 | `class TestAttemptResult:` |
| `apps/exams/services/result_calculation.py` | 42 | `def score_display(self):` |
| `apps/exams/services/result_calculation.py` | 46 | `def max_score_display(self):` |
| `apps/exams/services/result_calculation.py` | 50 | `def percentage_display(self):` |
| `apps/exams/services/result_calculation.py` | 54 | `def _legacy_test_attempt_result(attempt):` |
| `apps/exams/services/result_calculation.py` | 5 | `def _as_decimal(value, default="0"):` |
| `apps/exams/services/result_calculation.py` | 72 | `def calculate_test_attempt_result(attempt, *, answers=None):` |
| `apps/exams/services/review_visibility.py` | 30 | `def resolve_exam_attempt_review_window_seconds(attempt, *, current_time=None):` |
| `apps/exams/services/review_visibility.py` | 45 | `def attempt_review_window_locked(attempt, *, current_time=None):` |
| `apps/exams/services/review_visibility.py` | 6 | `def resolve_exam_attempt_name_visibility(attempt, *, current_time=None):` |
| `apps/exams/services/student_pins.py` | 103 | `def student_visible_pin(exam, user) -> str \| None:` |
| `apps/exams/services/student_pins.py` | 116 | `def verify_student_pin(exam, user, raw_pin: str) -> bool:` |
| `apps/exams/services/student_pins.py` | 126 | `def resolve_student_pin_login(username: str, raw_pin: str):` |
| `apps/exams/services/student_pins.py` | 27 | `def _student_pin_rate_key(username: str) -> str:` |
| `apps/exams/services/student_pins.py` | 31 | `def student_pin_login_rate_limited(username: str) -> bool:` |
| `apps/exams/services/student_pins.py` | 57 | `def exam_requires_student_pins(exam) -> bool:` |
| `apps/exams/services/student_pins.py` | 61 | `def _assigned_student_ids(exam) -> set[int]:` |
| `apps/exams/services/student_pins.py` | 68 | `def provision_exam_student_pins(exam) -> None:` |
| `apps/exams/services/supervision/_shared.py` | 12 | `def _notify_student_via_ws(attempt_id: int, event_data: dict) -> None:` |
| `apps/exams/services/supervision/_shared.py` | 30 | `def get_supervision_config(exam):` |
| `apps/exams/services/supervision/_shared.py` | 43 | `def save_supervision_config_from_form(exam, form_data):` |
| `apps/exams/services/supervision/actions.py` | 112 | `def teacher_lock_attempt(attempt, teacher):` |
| `apps/exams/services/supervision/actions.py` | 14 | `def teacher_resume_attempt(attempt, teacher, grant_extra_chance=False):` |
| `apps/exams/services/supervision/actions.py` | 169 | `def teacher_stop_attempt(attempt, teacher):` |
| `apps/exams/services/supervision/actions.py` | 215 | `def mark_student_returned(attempt):` |
| `apps/exams/services/supervision/actions.py` | 231 | `def sweep_expired_resume_windows(queryset=None):` |
| `apps/exams/services/supervision/incidents.py` | 136 | `def _log_system_incident(attempt, event_type, metadata):` |
| `apps/exams/services/supervision/incidents.py` | 17 | `def log_supervision_incident(attempt, event_type, metadata=None):` |
| `apps/exams/services/supervision/incidents.py` | 75 | `def _apply_violation_action(attempt, config, violation_count):` |
| `apps/exams/services/supervision/monitor.py` | 160 | `def get_exam_question_total(exam):` |
| `apps/exams/services/supervision/monitor.py` | 174 | `def _attempt_live_state(attempt):` |
| `apps/exams/services/supervision/monitor.py` | 190 | `def get_exam_live_monitor_data(exam, date_value=None):` |
| `apps/exams/services/supervision/monitor.py` | 19 | `def get_attempt_supervision_status(attempt):` |
| `apps/exams/services/supervision/monitor.py` | 337 | `def get_exam_session_dates(exam):` |
| `apps/exams/services/supervision/monitor.py` | 64 | `def get_flagged_students_for_exam(exam, organization):` |
| `apps/exams/services/supervision/monitor.py` | 94 | `def get_supervision_monitor_data(organization, exam_id=None, exam_queryset=None):` |
| `apps/exams/services/supervision/snapshot.py` | 12 | `def _media_url(file_field):` |
| `apps/exams/services/supervision/snapshot.py` | 145 | `def _coding_snapshot_answers(attempt):` |
| `apps/exams/services/supervision/snapshot.py` | 212 | `def _submission_file_items_safe(submission):` |
| `apps/exams/services/supervision/snapshot.py` | 22 | `def _question_kind(question, exam_type):` |
| `apps/exams/services/supervision/snapshot.py` | 231 | `def get_attempt_live_snapshot(attempt):` |
| `apps/exams/services/supervision/snapshot.py` | 49 | `def _written_test_snapshot_answers(attempt, exam_type):` |
| `apps/exams/services/teacher_dashboard.py` | 40 | `def build_teacher_exam_dashboard(exams) -> dict:` |
| `apps/exams/services/teacher_dashboard.py` | 68 | `def _descriptor(key):` |
| `apps/exams/services/utils.py` | 13 | `def _norm(text: str) -> str:` |
| `apps/exams/services/utils.py` | 17 | `def _effective_needed_count(exam) -> int:` |
| `apps/exams/services/utils.py` | 21 | `def _attempt_has_any_answer(attempt) -> bool:` |
| `apps/exams/services/utils.py` | 46 | `def _save_paint_png_to_answer(ans, data_url: str):` |
| `apps/exams/services/utils.py` | 76 | `def _clear_paint_from_answer(ans):` |
| `apps/exams/signals.py` | 13 | `def _sync_pin_assignments_for_group_ids(group_ids):` |
| `apps/exams/signals.py` | 22 | `def sync_student_pins_when_group_students_change(sender, instance, action, reverse, pk_set, **kwargs):` |
| `apps/exams/signals.py` | 43 | `def sync_student_pins_when_exam_assignments_change(sender, instance, action, reverse, pk_set, **kwargs):` |
| `apps/exams/tasks.py` | 165 | `def run_ai_generation_job(job_id):` |
| `apps/exams/tasks.py` | 20 | `def expire_stale_resumed_attempts():` |
| `apps/exams/tasks.py` | 269 | `def run_export_job(job_id):` |
| `apps/exams/tasks.py` | 45 | `def notify_upcoming_final_exams():` |
| `apps/exams/tasks.py` | 69 | `def run_text_extraction_job(job_id):` |
| `apps/exams/templatetags/exam_filters.py` | 20 | `def subtract(value, arg):` |
| `apps/exams/templatetags/exam_filters.py` | 29 | `def format_duration(seconds):` |
| `apps/exams/templatetags/exam_filters.py` | 60 | `def format_duration_clock(seconds):` |
| `apps/exams/templatetags/exam_filters.py` | 9 | `def minutes_since(value):` |
| `apps/exams/templatetags/exams_ui.py` | 24 | `def exam_type_meta(type_key):` |
| `apps/exams/templatetags/exams_ui.py` | 30 | `def exam_status_meta(status_key):` |
| `apps/exams/templatetags/exams_ui.py` | 36 | `def exam_category_meta(category_key):` |
| `apps/exams/templatetags/exams_ui.py` | 42 | `def dict_key(mapping, key):` |
| `apps/exams/tests/test_answer_snapshot.py` | 107 | `def test_randomizer_populates_question_snapshot(self):` |
| `apps/exams/tests/test_answer_snapshot.py` | 24 | `class TestAnswerSnapshotIntegrity(TestCase):` |
| `apps/exams/tests/test_answer_snapshot.py` | 25 | `def setUp(self):` |
| `apps/exams/tests/test_answer_snapshot.py` | 43 | `def _question(self, *, order, points=1):` |
| `apps/exams/tests/test_answer_snapshot.py` | 46 | `def _option(self, question, *, text, is_correct):` |
| `apps/exams/tests/test_answer_snapshot.py` | 49 | `def _attempt(self):` |
| `apps/exams/tests/test_answer_snapshot.py` | 55 | `def test_snapshot_preserves_score_when_live_options_edited_after_submit(self):` |
| `apps/exams/tests/test_answer_snapshot.py` | 91 | `def test_legacy_answer_without_snapshot_uses_live_options(self):` |
| `apps/exams/tests/test_attempt_constraints.py` | 25 | `def _build_exam_fixture(suffix=""):` |
| `apps/exams/tests/test_attempt_constraints.py` | 46 | `class ExamAttemptConstraintTests(TestCase):` |
| `apps/exams/tests/test_attempt_constraints.py` | 49 | `def setUp(self):` |
| `apps/exams/tests/test_attempt_constraints.py` | 52 | `def test_second_in_progress_attempt_is_rejected_by_db(self):` |
| `apps/exams/tests/test_attempt_constraints.py` | 57 | `def test_finished_attempts_do_not_block_new_active_attempt(self):` |
| `apps/exams/tests/test_attempt_constraints.py` | 63 | `def test_duplicate_attempt_number_is_rejected_by_db(self):` |
| `apps/exams/tests/test_attempt_constraints.py` | 68 | `def test_create_exam_attempt_returns_existing_active_on_collision(self):` |
| `apps/exams/tests/test_attempt_constraints.py` | 79 | `class ExamAttemptRaceTests(TransactionTestCase):` |
| `apps/exams/tests/test_attempt_constraints.py` | 82 | `def test_parallel_create_exam_attempt_yields_single_active_attempt(self):` |
| `apps/exams/tests/test_attempt_constraints.py` | 88 | `def worker():` |
| `apps/exams/tests/test_attempt_timer.py` | 26 | `class ExamAttemptTimerExpiryTest(TestCase):` |
| `apps/exams/tests/test_attempt_timer.py` | 29 | `def setUp(self):` |
| `apps/exams/tests/test_attempt_timer.py` | 47 | `def _new_attempt(self, status="in_progress"):` |
| `apps/exams/tests/test_attempt_timer.py` | 50 | `def test_expires_after_time_limit(self):` |
| `apps/exams/tests/test_attempt_timer.py` | 58 | `def test_not_expired_before_deadline(self):` |
| `apps/exams/tests/test_attempt_timer.py` | 65 | `def test_no_duration_means_no_expiry(self):` |
| `apps/exams/tests/test_attempt_timer.py` | 74 | `def test_already_finished_attempt_is_not_re_expired(self):` |
| `apps/exams/tests/test_attempt_timer.py` | 81 | `def test_finished_at_clamped_to_deadline_on_late_expiry(self):` |
| `apps/exams/tests/test_coding_exam.py` | 111 | `class CodingExamFormTests(TestCase):` |
| `apps/exams/tests/test_coding_exam.py` | 112 | `def test_coding_exam_form_does_not_require_inline_coding_task_fields(self):` |
| `apps/exams/tests/test_coding_exam.py` | 128 | `def test_coding_exam_form_rejects_practical_exam_when_disabled(self):` |
| `apps/exams/tests/test_coding_exam.py` | 142 | `def test_truncate_capture_accepts_timeout_bytes(self):` |
| `apps/exams/tests/test_coding_exam.py` | 145 | `def test_cpp_snippet_is_wrapped_for_execution(self):` |
| `apps/exams/tests/test_coding_exam.py` | 155 | `def test_javascript_main_gets_prompt_polyfill_injected(self):` |
| `apps/exams/tests/test_coding_exam.py` | 168 | `def test_javascript_polyfill_is_not_double_injected(self):` |
| `apps/exams/tests/test_coding_exam.py` | 180 | `def test_node_prompt_polyfill_does_not_echo_stdin(self):` |
| `apps/exams/tests/test_coding_exam.py` | 196 | `def test_non_javascript_languages_are_unchanged_by_polyfill(self):` |
| `apps/exams/tests/test_coding_exam.py` | 203 | `def test_polyfill_module_exports_match_runtime_re_export(self):` |
| `apps/exams/tests/test_coding_exam.py` | 215 | `def test_docker_pull_noise_is_removed_from_stderr(self):` |
| `apps/exams/tests/test_coding_exam.py` | 229 | `class CodingExamDefinitionTests(TestCase):` |
| `apps/exams/tests/test_coding_exam.py` | 230 | `def setUp(self):` |
| `apps/exams/tests/test_coding_exam.py` | 241 | `def test_upsert_coding_question_creates_question_details_and_cases(self):` |
| `apps/exams/tests/test_coding_exam.py` | 282 | `class CodingExamSubmissionApiTests(TestCase):` |
| `apps/exams/tests/test_coding_exam.py` | 283 | `def setUp(self):` |
| `apps/exams/tests/test_coding_exam.py` | 335 | `def test_autosave_and_submit_store_code_submission(self):` |
| `apps/exams/tests/test_coding_exam.py` | 34 | `class CodingRuntimeIndentationTests(SimpleTestCase):` |
| `apps/exams/tests/test_coding_exam.py` | 35 | `def test_execution_language_uses_file_extension(self):` |
| `apps/exams/tests/test_coding_exam.py` | 365 | `def test_take_coding_exam_includes_five_minute_warning_modal(self):` |
| `apps/exams/tests/test_coding_exam.py` | 379 | `def test_run_uses_active_python_file_and_custom_stdin(self):` |
| `apps/exams/tests/test_coding_exam.py` | 40 | `def test_mark_file_as_main_switches_without_deleting_files(self):` |
| `apps/exams/tests/test_coding_exam.py` | 423 | `def test_run_visible_code_returns_output_for_supported_sandbox_languages(self):` |
| `apps/exams/tests/test_coding_exam.py` | 457 | `def test_submission_download_returns_all_code_files_as_zip(self):` |
| `apps/exams/tests/test_coding_exam.py` | 511 | `def test_teacher_check_attempt_syncs_missing_coding_answers_from_final_submissions(self):` |
| `apps/exams/tests/test_coding_exam.py` | 52 | `def test_python_loose_top_level_unindent_is_normalized(self):` |
| `apps/exams/tests/test_coding_exam.py` | 60 | `def test_python_valid_one_space_suite_indent_is_preserved(self):` |
| `apps/exams/tests/test_coding_exam.py` | 65 | `def test_python_multiline_string_indentation_is_preserved(self):` |
| `apps/exams/tests/test_coding_exam.py` | 76 | `def test_execute_code_keeps_stdin_open_for_docker(self, run_mock, _image_mock, _which_mock):` |
| `apps/exams/tests/test_coding_exam.py` | 93 | `def assign_user_to_org(user, organization, role):` |
| `apps/exams/tests/test_coding_exam_frontend_assets.py` | 23 | `class CodingExamJavaScriptAssetTests(SimpleTestCase):` |
| `apps/exams/tests/test_coding_exam_frontend_assets.py` | 33 | `def setUpClass(cls):` |
| `apps/exams/tests/test_coding_exam_frontend_assets.py` | 38 | `def test_js_asset_exists_on_disk(self):` |
| `apps/exams/tests/test_coding_exam_frontend_assets.py` | 42 | `def test_inline_terminal_helpers_are_defined(self):` |
| `apps/exams/tests/test_coding_exam_frontend_assets.py` | 56 | `def test_run_clears_previous_stdin_before_inline_terminal(self):` |
| `apps/exams/tests/test_coding_exam_frontend_assets.py` | 66 | `def test_clear_button_resets_stdin_and_terminal_state(self):` |
| `apps/exams/tests/test_coding_exam_frontend_assets.py` | 77 | `def test_keyboard_shortcuts_are_wired(self):` |
| `apps/exams/tests/test_coding_exam_frontend_assets.py` | 83 | `def test_redirects_stop_supervision_before_navigation(self):` |
| `apps/exams/tests/test_coding_exam_frontend_assets.py` | 89 | `class ExamSupervisionJavaScriptAssetTests(SimpleTestCase):` |
| `apps/exams/tests/test_coding_exam_frontend_assets.py` | 91 | `def setUpClass(cls):` |
| `apps/exams/tests/test_coding_exam_frontend_assets.py` | 95 | `def test_result_navigation_is_idempotent(self):` |
| `apps/exams/tests/test_exam_center_policy.py` | 104 | `class ExamCenterPolicyUnitTests(_Base):` |
| `apps/exams/tests/test_exam_center_policy.py` | 105 | `def setUp(self):` |
| `apps/exams/tests/test_exam_center_policy.py` | 111 | `def test_is_exam_center_user(self):` |
| `apps/exams/tests/test_exam_center_policy.py` | 115 | `def test_final_exam_questions_only_exam_center(self):` |
| `apps/exams/tests/test_exam_center_policy.py` | 119 | `def test_non_final_exam_questions_open_to_teacher(self):` |
| `apps/exams/tests/test_exam_center_policy.py` | 125 | `def test_question_bank_creation_only_exam_center(self):` |
| `apps/exams/tests/test_exam_center_policy.py` | 129 | `def test_superuser_bypasses(self):` |
| `apps/exams/tests/test_exam_center_policy.py` | 136 | `class FinalExamQuestionViewTests(_Base):` |
| `apps/exams/tests/test_exam_center_policy.py` | 139 | `def _question_urls(self, exam):` |
| `apps/exams/tests/test_exam_center_policy.py` | 147 | `def test_teacher_blocked_on_final_exam_question_views(self):` |
| `apps/exams/tests/test_exam_center_policy.py` | 153 | `def test_teacher_allowed_on_quiz_exam_question_views(self):` |
| `apps/exams/tests/test_exam_center_policy.py` | 161 | `def test_exam_center_allowed_on_own_final_exam_question_views(self):` |
| `apps/exams/tests/test_exam_center_policy.py` | 169 | `def test_teacher_blocked_on_final_questions_bank_mutation(self):` |
| `apps/exams/tests/test_exam_center_policy.py` | 179 | `class QuestionBankCreationViewTests(_Base):` |
| `apps/exams/tests/test_exam_center_policy.py` | 180 | `def test_teacher_cannot_create_bank(self):` |
| `apps/exams/tests/test_exam_center_policy.py` | 189 | `def test_exam_center_can_create_bank(self):` |
| `apps/exams/tests/test_exam_center_policy.py` | 199 | `class ExamFormFinalCategoryTests(_Base):` |
| `apps/exams/tests/test_exam_center_policy.py` | 200 | `def setUp(self):` |
| `apps/exams/tests/test_exam_center_policy.py` | 204 | `def _form_data(self, **overrides):` |
| `apps/exams/tests/test_exam_center_policy.py` | 216 | `def test_teacher_cannot_select_final_category(self):` |
| `apps/exams/tests/test_exam_center_policy.py` | 221 | `def test_teacher_final_choice_hidden(self):` |
| `apps/exams/tests/test_exam_center_policy.py` | 228 | `def test_exam_center_can_select_final_category(self):` |
| `apps/exams/tests/test_exam_center_policy.py` | 233 | `def test_exam_center_can_open_create_exam_modal(self):` |
| `apps/exams/tests/test_exam_center_policy.py` | 239 | `def test_teacher_can_select_quiz_and_midterm(self):` |
| `apps/exams/tests/test_exam_center_policy.py` | 244 | `def test_teacher_editing_existing_final_keeps_value(self):` |
| `apps/exams/tests/test_exam_center_policy.py` | 33 | `def _assign_user_to_org(user, organization, profile_role, membership_role_name):` |
| `apps/exams/tests/test_exam_center_policy.py` | 50 | `class _Base(TestCase):` |
| `apps/exams/tests/test_exam_center_policy.py` | 52 | `def setUpTestData(cls):` |
| `apps/exams/tests/test_exam_center_policy.py` | 95 | `def _client_for(self, user):` |
| `apps/exams/tests/test_exam_center_stats_charts.py` | 100 | `def test_charts_respect_type_filter(self):` |
| `apps/exams/tests/test_exam_center_stats_charts.py` | 106 | `def test_ai_endpoint_fail_soft_without_api_key(self):` |
| `apps/exams/tests/test_exam_center_stats_charts.py` | 114 | `def test_profile_section_renders_charts_block(self):` |
| `apps/exams/tests/test_exam_center_stats_charts.py` | 21 | `class ExamCenterStatsChartsTests(TestCase):` |
| `apps/exams/tests/test_exam_center_stats_charts.py` | 23 | `def setUpTestData(cls):` |
| `apps/exams/tests/test_exam_center_stats_charts.py` | 69 | `def _client(self, user):` |
| `apps/exams/tests/test_exam_center_stats_charts.py` | 77 | `def test_student_cannot_access(self):` |
| `apps/exams/tests/test_exam_center_stats_charts.py` | 82 | `def test_charts_payload(self):` |
| `apps/exams/tests/test_exam_room_admin.py` | 102 | `class MacGateTests(_RoomBase):` |
| `apps/exams/tests/test_exam_room_admin.py` | 107 | `def setUp(self):` |
| `apps/exams/tests/test_exam_room_admin.py` | 111 | `def _with_client_mac(self, mac):` |
| `apps/exams/tests/test_exam_room_admin.py` | 117 | `def test_registered_mac_allowed_ip_irrelevant(self):` |
| `apps/exams/tests/test_exam_room_admin.py` | 126 | `def test_unregistered_mac_blocked(self):` |
| `apps/exams/tests/test_exam_room_admin.py` | 132 | `def test_unresolvable_mac_fail_closed(self):` |
| `apps/exams/tests/test_exam_room_admin.py` | 140 | `def test_org_gate_matches_mac(self):` |
| `apps/exams/tests/test_exam_room_admin.py` | 147 | `def test_org_gate_open_when_no_computers(self):` |
| `apps/exams/tests/test_exam_room_admin.py` | 154 | `class RoomIsolationAndMonitorTests(_RoomBase):` |
| `apps/exams/tests/test_exam_room_admin.py` | 158 | `def setUpTestData(cls):` |
| `apps/exams/tests/test_exam_room_admin.py` | 181 | `def _attempt(self, status="in_progress", room=None, computer=None, user=None):` |
| `apps/exams/tests/test_exam_room_admin.py` | 194 | `def test_isolation_open_without_live_attempts(self):` |
| `apps/exams/tests/test_exam_room_admin.py` | 200 | `def test_isolation_binds_to_first_live_room(self):` |
| `apps/exams/tests/test_exam_room_admin.py` | 207 | `def test_isolation_releases_when_attempts_finish(self):` |
| `apps/exams/tests/test_exam_room_admin.py` | 214 | `def test_room_monitor_snapshot_includes_ticketless_attempts(self):` |
| `apps/exams/tests/test_exam_room_admin.py` | 238 | `def test_other_room_snapshot_does_not_show_foreign_attempts(self):` |
| `apps/exams/tests/test_exam_room_admin.py` | 247 | `class OrgGateIpModeTests(_RoomBase):` |
| `apps/exams/tests/test_exam_room_admin.py` | 250 | `def setUp(self):` |
| `apps/exams/tests/test_exam_room_admin.py` | 253 | `def test_ip_mode_matches_registered_ip(self):` |
| `apps/exams/tests/test_exam_room_admin.py` | 261 | `class ManageRoomsPermissionTests(_RoomBase):` |
| `apps/exams/tests/test_exam_room_admin.py` | 262 | `def test_superuser_can(self):` |
| `apps/exams/tests/test_exam_room_admin.py` | 266 | `def test_flagged_profile_can(self):` |
| `apps/exams/tests/test_exam_room_admin.py` | 273 | `def test_plain_user_cannot(self):` |
| `apps/exams/tests/test_exam_room_admin.py` | 278 | `class RoomInvigilatorSupervisionTests(_RoomBase):` |
| `apps/exams/tests/test_exam_room_admin.py` | 279 | `def test_room_invigilator_supervises_all_room_sessions(self):` |
| `apps/exams/tests/test_exam_room_admin.py` | 27 | `class MacNormalizationTests(TestCase):` |
| `apps/exams/tests/test_exam_room_admin.py` | 28 | `def test_normalize_variants(self):` |
| `apps/exams/tests/test_exam_room_admin.py` | 32 | `def test_invalid_length_raises(self):` |
| `apps/exams/tests/test_exam_room_admin.py` | 38 | `class _RoomBase(TestCase):` |
| `apps/exams/tests/test_exam_room_admin.py` | 40 | `def setUpTestData(cls):` |
| `apps/exams/tests/test_exam_room_admin.py` | 52 | `class AddComputerServiceTests(_RoomBase):` |
| `apps/exams/tests/test_exam_room_admin.py` | 53 | `def test_add_normalizes_and_persists(self):` |
| `apps/exams/tests/test_exam_room_admin.py` | 61 | `def test_duplicate_mac_rejected(self):` |
| `apps/exams/tests/test_exam_room_admin.py` | 66 | `def test_duplicate_seat_rejected(self):` |
| `apps/exams/tests/test_exam_room_admin.py` | 71 | `def test_invalid_mac_rejected(self):` |
| `apps/exams/tests/test_exam_room_admin.py` | 76 | `class RoomIpGateTests(_RoomBase):` |
| `apps/exams/tests/test_exam_room_admin.py` | 77 | `def setUp(self):` |
| `apps/exams/tests/test_exam_room_admin.py` | 80 | `def test_no_registered_ips_allows(self):` |
| `apps/exams/tests/test_exam_room_admin.py` | 85 | `def test_matching_ip_allowed_mismatch_blocked(self):` |
| `apps/exams/tests/test_exam_room_admin.py` | 92 | `def test_inactive_computer_ip_ignored(self):` |
| `apps/exams/tests/test_final_center_cabinet.py` | 102 | `class ReminderTaskTests(_CabinetBase):` |
| `apps/exams/tests/test_final_center_cabinet.py` | 103 | `def _count_reminders(self):` |
| `apps/exams/tests/test_final_center_cabinet.py` | 106 | `def test_reminder_sent_within_threshold(self):` |
| `apps/exams/tests/test_final_center_cabinet.py` | 116 | `def test_reminder_not_duplicated_for_same_stage(self):` |
| `apps/exams/tests/test_final_center_cabinet.py` | 125 | `def test_second_reminder_at_closer_threshold(self):` |
| `apps/exams/tests/test_final_center_cabinet.py` | 138 | `def test_no_reminder_outside_horizon(self):` |
| `apps/exams/tests/test_final_center_cabinet.py` | 145 | `def test_no_reminder_for_completed_ticket(self):` |
| `apps/exams/tests/test_final_center_cabinet.py` | 154 | `class SupervisorNavFlagTests(_CabinetBase):` |
| `apps/exams/tests/test_final_center_cabinet.py` | 157 | `def test_exam_center_always_sees_final_center(self):` |
| `apps/exams/tests/test_final_center_cabinet.py` | 164 | `def test_assigned_invigilator_flag_true(self):` |
| `apps/exams/tests/test_final_center_cabinet.py` | 175 | `def test_cancelled_session_does_not_count(self):` |
| `apps/exams/tests/test_final_center_cabinet.py` | 23 | `class _CabinetBase(TestCase):` |
| `apps/exams/tests/test_final_center_cabinet.py` | 25 | `def setUpTestData(cls):` |
| `apps/exams/tests/test_final_center_cabinet.py` | 49 | `def _set_window(self, *, start_delta, end_delta):` |
| `apps/exams/tests/test_final_center_cabinet.py` | 57 | `def _session(self, *, start_delta, end_delta):` |
| `apps/exams/tests/test_final_center_cabinet.py` | 68 | `def _ticket(self, session=None):` |
| `apps/exams/tests/test_final_center_cabinet.py` | 76 | `class CabinetContextTests(_CabinetBase):` |
| `apps/exams/tests/test_final_center_cabinet.py` | 77 | `def test_no_ticket_returns_has_ticket_false(self):` |
| `apps/exams/tests/test_final_center_cabinet.py` | 81 | `def test_context_exposes_window_and_pin_within_visibility(self):` |
| `apps/exams/tests/test_final_center_cabinet.py` | 92 | `def test_pin_hidden_outside_visibility_window(self):` |
| `apps/exams/tests/test_final_center_consumers.py` | 100 | `def _try_connect(self, path, headers):` |
| `apps/exams/tests/test_final_center_consumers.py` | 101 | `async def scenario():` |
| `apps/exams/tests/test_final_center_consumers.py` | 112 | `def test_room_channel_rejects_student(self):` |
| `apps/exams/tests/test_final_center_consumers.py` | 119 | `def test_room_channel_rejects_unauthenticated(self):` |
| `apps/exams/tests/test_final_center_consumers.py` | 123 | `def test_room_channel_accepts_exam_center_of_same_org(self):` |
| `apps/exams/tests/test_final_center_consumers.py` | 130 | `def test_room_channel_rejects_exam_center_of_other_org(self):` |
| `apps/exams/tests/test_final_center_consumers.py` | 138 | `def test_wait_channel_accepts_ticket_owner(self):` |
| `apps/exams/tests/test_final_center_consumers.py` | 145 | `def test_wait_channel_rejects_other_student(self):` |
| `apps/exams/tests/test_final_center_consumers.py` | 152 | `def test_wait_channel_rejects_removed_ticket(self):` |
| `apps/exams/tests/test_final_center_consumers.py` | 40 | `class FinalCenterConsumerAuthTests(TransactionTestCase):` |
| `apps/exams/tests/test_final_center_consumers.py` | 41 | `def setUp(self):` |
| `apps/exams/tests/test_final_center_consumers.py` | 94 | `def _session_headers(self, username):` |
| `apps/exams/tests/test_final_center_flow.py` | 1017 | `def test_pin_login_blocked_from_other_room_while_live(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 1040 | `class RoomListScopingTests(_FlowBase):` |
| `apps/exams/tests/test_final_center_flow.py` | 1043 | `def test_room_invigilator_sees_only_assigned_room(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 1054 | `def test_unassigned_teacher_sees_no_rooms(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 1062 | `def test_exam_center_sees_all_rooms(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 110 | `def setUp(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 130 | `def tearDown(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 135 | `def _client_for(self, user):` |
| `apps/exams/tests/test_final_center_flow.py` | 143 | `def _entry_client(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 153 | `class EntryValidationTests(_FlowBase):` |
| `apps/exams/tests/test_final_center_flow.py` | 154 | `def test_valid_entry_logs_student_in_and_redirects_to_self(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 162 | `def test_modal_shown_on_get_after_pin_validation(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 170 | `def test_login_page_renders_pin_form_for_anonymous(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 176 | `def test_wrong_pin_returns_generic_error(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 185 | `def test_unknown_user_gets_same_generic_error_as_wrong_pin(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 203 | `def test_pin_of_one_student_cannot_be_used_by_another_username(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 212 | `def test_entry_rejected_when_no_open_room_sitting(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 225 | `def test_get_without_pin_validation_shows_login_not_modal(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 232 | `def test_waiting_of_foreign_ticket_is_404(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 241 | `class _FakeRequest:` |
| `apps/exams/tests/test_final_center_flow.py` | 248 | `class GateAndWaitingTests(_FlowBase):` |
| `apps/exams/tests/test_final_center_flow.py` | 249 | `def test_modal_confirm_moves_ticket_to_waiting(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 261 | `def test_modal_without_rules_confirmation_stays(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 270 | `class MultilingualModalTests(_FlowBase):` |
| `apps/exams/tests/test_final_center_flow.py` | 273 | `def _make_multilingual(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 284 | `def test_modal_lists_language_options(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 293 | `def test_confirm_stores_selected_language_and_display(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 307 | `def test_confirm_without_language_rejected_for_multilingual(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 320 | `def test_modal_back_logs_out_and_returns_to_login(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 328 | `def test_student_cancel_waiting_returns_to_assigned_without_attempt(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 335 | `def test_begin_rejected_before_room_start(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 341 | `class RoomLifecycleTests(_FlowBase):` |
| `apps/exams/tests/test_final_center_flow.py` | 342 | `def test_start_room_is_idempotent(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 350 | `def test_start_too_early_requires_override(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 360 | `def test_synchronized_start_then_begin_creates_attempt(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 373 | `def test_pin_is_revoked_and_reentry_blocked_after_begin(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 387 | `def test_invigilator_reentry_issues_new_pin_and_resumes_same_attempt(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 418 | `def test_begin_endpoint_via_http(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 429 | `def test_end_room_finalizes_attempts_and_tickets(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 454 | `def test_concurrent_sessions_in_room_allowed(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 467 | `def test_session_plan_rejects_end_before_start(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 476 | `class RemoveStudentTests(_FlowBase):` |
| `apps/exams/tests/test_final_center_flow.py` | 477 | `def test_remove_requires_reason(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 482 | `def test_remove_active_student_stops_attempt_and_revokes_pin(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 496 | `def test_suspend_locks_attempt_but_keeps_ticket_active(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 510 | `class PermissionAndTenantTests(_FlowBase):` |
| `apps/exams/tests/test_final_center_flow.py` | 512 | `def setUpTestData(cls):` |
| `apps/exams/tests/test_final_center_flow.py` | 525 | `def _other_org_client(self, user):` |
| `apps/exams/tests/test_final_center_flow.py` | 533 | `def test_monitor_denied_for_unassigned_teacher(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 538 | `def test_monitor_allowed_for_assigned_invigilator(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 543 | `def test_room_management_denied_for_invigilator(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 550 | `def test_room_management_denied_for_exam_center_without_flag(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 555 | `def test_session_list_hides_manage_buttons_for_invigilator(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 566 | `def test_session_list_shows_manage_buttons_for_center(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 572 | `def test_room_list_shows_only_assigned_rooms_for_invigilator(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 57 | `class _FlowBase(TestCase):` |
| `apps/exams/tests/test_final_center_flow.py` | 595 | `def test_room_list_shows_all_rooms_for_center(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 59 | `def setUpTestData(cls):` |
| `apps/exams/tests/test_final_center_flow.py` | 601 | `def test_history_access_control(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 607 | `def test_session_history_records_operations(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 618 | `def test_ticket_snapshot_no_attempt(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 626 | `def test_ticket_snapshot_with_active_attempt(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 639 | `def test_ticket_snapshot_cross_tenant_404(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 644 | `def test_room_monitor_aggregates_live_sessions(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 673 | `def test_completed_result_hidden_after_timeout_but_counted(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 686 | `def test_recent_completed_result_still_visible(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 696 | `def test_seat_reuse_hides_old_completed_immediately(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 735 | `def test_room_start_all_time_window_error_is_graceful(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 751 | `def test_ticket_resume_with_extra_chance_flag(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 772 | `def test_room_start_all_starts_every_live_session(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 791 | `def test_ticket_resume_restores_locked_attempt(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 806 | `def test_cross_tenant_session_access_is_404(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 812 | `def test_start_endpoint_denied_for_student(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 817 | `def test_snapshot_contains_compact_rows_only(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 828 | `class CenterPageRenderTests(_FlowBase):` |
| `apps/exams/tests/test_final_center_flow.py` | 831 | `def test_room_list_renders(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 836 | `def test_room_create_via_superadmin(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 859 | `def test_room_monitor_renders_with_computers_and_invigilator_panel(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 870 | `def test_assign_room_invigilators(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 879 | `def test_session_list_renders(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 885 | `def test_session_detail_renders_with_tickets(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 892 | `def test_session_create_form_renders(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 896 | `def test_reports_render_both_tabs(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 901 | `def test_reports_csv_export(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 908 | `def test_snapshot_endpoint_returns_json(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 915 | `def test_final_login_page_renders_form(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 923 | `def test_waiting_page_renders_after_modal_confirm(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 931 | `class StudentPinWaitingFlowTests(_FlowBase):` |
| `apps/exams/tests/test_final_center_flow.py` | 942 | `def setUpTestData(cls):` |
| `apps/exams/tests/test_final_center_flow.py` | 959 | `def _pin_login(self, client, **extra):` |
| `apps/exams/tests/test_final_center_flow.py` | 966 | `def test_pin_login_creates_ticket_and_lands_in_gate_not_exam(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 986 | `def test_pin_login_auto_creates_sitting_when_room_idle(self):` |
| `apps/exams/tests/test_final_center_flow.py` | 997 | `def test_pin_flow_waits_then_starts_with_room_stamp(self):` |
| `apps/exams/tests/test_final_center_pins.py` | 104 | `def test_verify_accepts_correct_and_rejects_wrong_pin(self):` |
| `apps/exams/tests/test_final_center_pins.py` | 110 | `def test_repeated_failures_lock_the_ticket(self):` |
| `apps/exams/tests/test_final_center_pins.py` | 120 | `def test_successful_verify_resets_failure_counter(self):` |
| `apps/exams/tests/test_final_center_pins.py` | 129 | `def test_expired_pin_is_rejected(self):` |
| `apps/exams/tests/test_final_center_pins.py` | 137 | `def test_regeneration_invalidates_previous_pin(self):` |
| `apps/exams/tests/test_final_center_pins.py` | 145 | `def test_revoked_pin_is_rejected_and_cipher_wiped(self):` |
| `apps/exams/tests/test_final_center_pins.py` | 153 | `def test_decrypt_returns_original_pin_for_authorized_display(self):` |
| `apps/exams/tests/test_final_center_pins.py` | 158 | `def test_student_visible_pin_respects_visibility_window(self):` |
| `apps/exams/tests/test_final_center_pins.py` | 166 | `def test_student_visible_pin_hidden_after_final_status(self):` |
| `apps/exams/tests/test_final_center_pins.py` | 174 | `class TicketStateMachineTests(_FinalCenterBase):` |
| `apps/exams/tests/test_final_center_pins.py` | 175 | `def test_valid_transition_assigned_to_waiting(self):` |
| `apps/exams/tests/test_final_center_pins.py` | 181 | `def test_invalid_transition_rejected(self):` |
| `apps/exams/tests/test_final_center_pins.py` | 188 | `def test_completed_is_terminal(self):` |
| `apps/exams/tests/test_final_center_pins.py` | 195 | `def test_stale_status_loses_the_race(self):` |
| `apps/exams/tests/test_final_center_pins.py` | 205 | `def test_unique_ticket_per_exam_student(self):` |
| `apps/exams/tests/test_final_center_pins.py` | 36 | `class _FinalCenterBase(TestCase):` |
| `apps/exams/tests/test_final_center_pins.py` | 38 | `def setUpTestData(cls):` |
| `apps/exams/tests/test_final_center_pins.py` | 79 | `def _ticket(self, student=None):` |
| `apps/exams/tests/test_final_center_pins.py` | 88 | `class PinSecurityTests(_FinalCenterBase):` |
| `apps/exams/tests/test_final_center_pins.py` | 89 | `def test_generated_pin_has_configured_length_and_charset(self):` |
| `apps/exams/tests/test_final_center_pins.py` | 94 | `def test_set_ticket_pin_stores_hash_not_plaintext(self):` |
| `apps/exams/tests/test_final_exam_center_page.py` | 107 | `def test_final_page_is_pin_login_not_exam_list(self):` |
| `apps/exams/tests/test_final_exam_center_page.py` | 116 | `def test_mistyped_exmas_final_redirects_to_final_exam_center(self):` |
| `apps/exams/tests/test_final_exam_center_page.py` | 121 | `def test_open_to_everyone_when_allowlist_empty(self):` |
| `apps/exams/tests/test_final_exam_center_page.py` | 126 | `def test_blocked_when_client_ip_not_in_allowlist(self):` |
| `apps/exams/tests/test_final_exam_center_page.py` | 131 | `def test_allowed_when_client_ip_matches(self):` |
| `apps/exams/tests/test_final_exam_center_page.py` | 136 | `def test_allowed_when_client_ip_in_cidr(self):` |
| `apps/exams/tests/test_final_exam_center_page.py` | 141 | `def test_final_take_exam_hides_base_header(self):` |
| `apps/exams/tests/test_final_exam_center_page.py` | 148 | `def test_final_result_hides_base_header_and_my_appeals_link(self):` |
| `apps/exams/tests/test_final_exam_center_page.py` | 158 | `def test_final_result_after_five_minutes_logs_out_to_final_login(self):` |
| `apps/exams/tests/test_final_exam_center_page.py` | 168 | `def test_final_result_from_my_results_stays_viewable_after_timeout(self):` |
| `apps/exams/tests/test_final_exam_center_page.py` | 182 | `def test_final_result_from_center_shows_answer_analysis_but_cabinet_hides_it(self):` |
| `apps/exams/tests/test_final_exam_center_page.py` | 206 | `def test_midterm_result_from_cabinet_hides_answer_analysis(self):` |
| `apps/exams/tests/test_final_exam_center_page.py` | 232 | `class ExamCenterGateUnitTests(TestCase):` |
| `apps/exams/tests/test_final_exam_center_page.py` | 233 | `def setUp(self):` |
| `apps/exams/tests/test_final_exam_center_page.py` | 236 | `def test_get_client_ip_uses_last_xff_member(self):` |
| `apps/exams/tests/test_final_exam_center_page.py` | 242 | `def test_spoofed_xff_prefix_cannot_bypass_allowlist(self):` |
| `apps/exams/tests/test_final_exam_center_page.py` | 247 | `def test_empty_allowlist_allows_all(self):` |
| `apps/exams/tests/test_final_exam_center_page.py` | 252 | `def test_invalid_allowlist_entry_is_skipped_not_fatal(self):` |
| `apps/exams/tests/test_final_exam_center_page.py` | 257 | `def test_mismatched_ip_denied(self):` |
| `apps/exams/tests/test_final_exam_center_page.py` | 26 | `class FinalExamCenterPageTests(TestCase):` |
| `apps/exams/tests/test_final_exam_center_page.py` | 28 | `def setUpTestData(cls):` |
| `apps/exams/tests/test_final_exam_center_page.py` | 60 | `def _client(self):` |
| `apps/exams/tests/test_final_exam_center_page.py` | 68 | `def _finished_attempt(self, *, exam=None, finished_at=None, status="submitted"):` |
| `apps/exams/tests/test_final_exam_center_page.py` | 91 | `def _in_progress_attempt(self):` |
| `apps/exams/tests/test_forms.py` | 115 | `def test_edit_form_keeps_existing_is_active_value(self):` |
| `apps/exams/tests/test_forms.py` | 125 | `def test_create_form_can_require_organization_selection_for_superadmin_flow(self):` |
| `apps/exams/tests/test_forms.py` | 14 | `class ExamFormDefaultStateTests(TestCase):` |
| `apps/exams/tests/test_forms.py` | 151 | `class StudentGroupFormRoleSourceTests(TestCase):` |
| `apps/exams/tests/test_forms.py` | 152 | `def setUp(self):` |
| `apps/exams/tests/test_forms.py` | 15 | `def setUp(self):` |
| `apps/exams/tests/test_forms.py` | 228 | `def test_auth_groups_do_not_expand_teacher_or_student_queryset(self):` |
| `apps/exams/tests/test_forms.py` | 241 | `def test_student_options_include_registered_group_number_metadata(self):` |
| `apps/exams/tests/test_forms.py` | 251 | `def test_student_options_include_existing_group_membership_metadata(self):` |
| `apps/exams/tests/test_forms.py` | 265 | `def test_student_registered_group_number_is_separate_from_memberships(self):` |
| `apps/exams/tests/test_forms.py` | 282 | `def test_teacher_options_do_not_include_group_membership_metadata(self):` |
| `apps/exams/tests/test_forms.py` | 32 | `def test_create_form_marks_is_active_checked_by_default(self):` |
| `apps/exams/tests/test_forms.py` | 36 | `def test_create_form_defaults_new_exam_parameters(self):` |
| `apps/exams/tests/test_forms.py` | 43 | `def test_create_form_defaults_distribution_toggles_on(self):` |
| `apps/exams/tests/test_forms.py` | 48 | `def test_legacy_create_post_defaults_distribution_toggles_on_when_omitted(self):` |
| `apps/exams/tests/test_forms.py` | 62 | `def test_create_post_can_disable_distribution_toggles(self):` |
| `apps/exams/tests/test_forms.py` | 78 | `def test_blank_random_question_count_falls_back_to_ten(self):` |
| `apps/exams/tests/test_forms.py` | 91 | `def test_random_question_count_help_applies_to_written_and_practical(self):` |
| `apps/exams/tests/test_forms.py` | 95 | `def test_edit_form_preserves_existing_zero_random_question_count_when_blank(self):` |
| `apps/exams/tests/test_group_unit_scope.py` | 23 | `class GroupUnitScopeTest(TestCase):` |
| `apps/exams/tests/test_group_unit_scope.py` | 25 | `def setUpTestData(cls):` |
| `apps/exams/tests/test_group_unit_scope.py` | 66 | `def _visible(self, user):` |
| `apps/exams/tests/test_group_unit_scope.py` | 71 | `def test_dean_sees_only_own_faculty_subtree(self):` |
| `apps/exams/tests/test_group_unit_scope.py` | 79 | `def test_owner_sees_all_groups(self):` |
| `apps/exams/tests/test_group_unit_scope.py` | 82 | `def test_teacher_sees_only_own_groups(self):` |
| `apps/exams/tests/test_language_variants.py` | 108 | `def test_effective_needed_count_uses_variant_override(self):` |
| `apps/exams/tests/test_language_variants.py` | 117 | `def test_effective_needed_count_falls_back_to_exam(self):` |
| `apps/exams/tests/test_language_variants.py` | 23 | `class MultiLanguageExamTests(TestCase):` |
| `apps/exams/tests/test_language_variants.py` | 24 | `def setUp(self):` |
| `apps/exams/tests/test_language_variants.py` | 43 | `def _question(self, *, order, language, correct_label="A"):` |
| `apps/exams/tests/test_language_variants.py` | 52 | `def test_available_languages_lists_only_active_variants_with_questions(self):` |
| `apps/exams/tests/test_language_variants.py` | 66 | `def test_language_with_no_questions_is_not_offered(self):` |
| `apps/exams/tests/test_language_variants.py` | 74 | `def test_resolve_requested_language_validates_against_available(self):` |
| `apps/exams/tests/test_language_variants.py` | 82 | `def test_randomizer_delivers_only_selected_language_questions(self):` |
| `apps/exams/tests/test_language_variants.py` | 99 | `def test_randomizer_without_language_delivers_all(self):` |
| `apps/exams/tests/test_models.py` | 106 | `def test_student_group_requires_organization(self):` |
| `apps/exams/tests/test_models.py` | 117 | `class ExamTest(TestCase):` |
| `apps/exams/tests/test_models.py` | 120 | `def setUp(self):` |
| `apps/exams/tests/test_models.py` | 134 | `def test_exam_creation(self):` |
| `apps/exams/tests/test_models.py` | 148 | `def test_exam_organization_defaults_from_author_profile(self):` |
| `apps/exams/tests/test_models.py` | 157 | `def test_exam_slug_auto_generated(self):` |
| `apps/exams/tests/test_models.py` | 168 | `def test_exam_is_before_start(self):` |
| `apps/exams/tests/test_models.py` | 186 | `def test_exam_is_after_end(self):` |
| `apps/exams/tests/test_models.py` | 204 | `def test_exam_is_currently_active(self):` |
| `apps/exams/tests/test_models.py` | 21 | `class StudentGroupTest(TestCase):` |
| `apps/exams/tests/test_models.py` | 223 | `def test_exam_can_user_see(self):` |
| `apps/exams/tests/test_models.py` | 246 | `def test_exam_string_representation(self):` |
| `apps/exams/tests/test_models.py` | 24 | `def setUp(self):` |
| `apps/exams/tests/test_models.py` | 256 | `class ExamQuestionTest(TestCase):` |
| `apps/exams/tests/test_models.py` | 259 | `def setUp(self):` |
| `apps/exams/tests/test_models.py` | 277 | `def test_exam_question_creation(self):` |
| `apps/exams/tests/test_models.py` | 290 | `def test_exam_question_with_options(self):` |
| `apps/exams/tests/test_models.py` | 313 | `def test_exam_question_option_text_allows_long_imported_variants(self):` |
| `apps/exams/tests/test_models.py` | 317 | `def test_exam_question_effective_time_limit(self):` |
| `apps/exams/tests/test_models.py` | 337 | `def test_exam_question_string_representation(self):` |
| `apps/exams/tests/test_models.py` | 348 | `class ExamAttemptTest(TestCase):` |
| `apps/exams/tests/test_models.py` | 351 | `def setUp(self):` |
| `apps/exams/tests/test_models.py` | 371 | `def test_exam_attempt_creation(self):` |
| `apps/exams/tests/test_models.py` | 385 | `def test_exam_attempt_is_finished(self):` |
| `apps/exams/tests/test_models.py` | 402 | `def test_exam_attempt_mark_finished(self):` |
| `apps/exams/tests/test_models.py` | 418 | `def test_exam_attempt_score_percent(self):` |
| `apps/exams/tests/test_models.py` | 439 | `def test_exam_attempt_string_representation(self):` |
| `apps/exams/tests/test_models.py` | 450 | `class ExamAccessControlTest(TestCase):` |
| `apps/exams/tests/test_models.py` | 453 | `def setUp(self):` |
| `apps/exams/tests/test_models.py` | 477 | `def test_exam_with_access_code(self):` |
| `apps/exams/tests/test_models.py` | 47 | `def test_student_group_creation(self):` |
| `apps/exams/tests/test_models.py` | 494 | `def test_exam_attempt_limit(self):` |
| `apps/exams/tests/test_models.py` | 511 | `def test_attempts_left_ignores_in_progress_attempts(self):` |
| `apps/exams/tests/test_models.py` | 519 | `def test_can_user_start_allows_resume_for_in_progress_attempt(self):` |
| `apps/exams/tests/test_models.py` | 530 | `def test_exam_time_restrictions(self):` |
| `apps/exams/tests/test_models.py` | 58 | `def test_student_group_string_representation(self):` |
| `apps/exams/tests/test_models.py` | 68 | `def test_student_group_has_student_method(self):` |
| `apps/exams/tests/test_models.py` | 84 | `def test_student_group_has_teacher_method(self):` |
| `apps/exams/tests/test_pin_lookup.py` | 108 | `def test_search_and_detail_include_wizard_student_pin(self):` |
| `apps/exams/tests/test_pin_lookup.py` | 122 | `def test_search_and_detail_exclude_non_student_pin_holders(self):` |
| `apps/exams/tests/test_pin_lookup.py` | 132 | `def test_revoked_pin_not_revealed(self):` |
| `apps/exams/tests/test_pin_lookup.py` | 142 | `def test_non_center_forbidden(self):` |
| `apps/exams/tests/test_pin_lookup.py` | 23 | `class PinLookupTests(TestCase):` |
| `apps/exams/tests/test_pin_lookup.py` | 25 | `def setUpTestData(cls):` |
| `apps/exams/tests/test_pin_lookup.py` | 78 | `def _client(self, user):` |
| `apps/exams/tests/test_pin_lookup.py` | 86 | `def test_page_shell_renders(self):` |
| `apps/exams/tests/test_pin_lookup.py` | 92 | `def test_search_finds_student(self):` |
| `apps/exams/tests/test_pin_lookup.py` | 99 | `def test_student_detail_reveals_pin(self):` |
| `apps/exams/tests/test_question_bank_attach.py` | 104 | `def test_user_sees_own_and_shared_within_org_only(self):` |
| `apps/exams/tests/test_question_bank_attach.py` | 20 | `def _parsed(text, correct="B"):` |
| `apps/exams/tests/test_question_bank_attach.py` | 29 | `class QuestionBankLibraryTests(TestCase):` |
| `apps/exams/tests/test_question_bank_attach.py` | 30 | `def setUp(self):` |
| `apps/exams/tests/test_question_bank_attach.py` | 42 | `def test_create_bank_questions_from_parsed(self):` |
| `apps/exams/tests/test_question_bank_attach.py` | 52 | `def test_attach_snapshots_questions_into_exam(self):` |
| `apps/exams/tests/test_question_bank_attach.py` | 71 | `def test_attach_is_independent_of_bank_edits(self):` |
| `apps/exams/tests/test_question_bank_attach.py` | 82 | `class AccessibleBanksTests(TestCase):` |
| `apps/exams/tests/test_question_bank_attach.py` | 83 | `def setUp(self):` |
| `apps/exams/tests/test_question_submission.py` | 100 | `def test_submit_records_warnings_for_problem_text(self):` |
| `apps/exams/tests/test_question_submission.py` | 106 | `def test_submit_notifies_exam_center_members(self):` |
| `apps/exams/tests/test_question_submission.py` | 110 | `def test_submit_rejects_empty_text(self):` |
| `apps/exams/tests/test_question_submission.py` | 114 | `def test_submit_requires_subject(self):` |
| `apps/exams/tests/test_question_submission.py` | 118 | `def test_submit_requires_group(self):` |
| `apps/exams/tests/test_question_submission.py` | 122 | `def test_submit_with_student_group_fk(self):` |
| `apps/exams/tests/test_question_submission.py` | 130 | `def test_accept_creates_new_bank_with_questions(self):` |
| `apps/exams/tests/test_question_submission.py` | 145 | `def test_accept_into_existing_bank(self):` |
| `apps/exams/tests/test_question_submission.py` | 157 | `def test_accept_twice_blocked(self):` |
| `apps/exams/tests/test_question_submission.py` | 163 | `def test_reject_then_resubmit_cycle(self):` |
| `apps/exams/tests/test_question_submission.py` | 178 | `def test_accepted_submission_cannot_be_resubmitted(self):` |
| `apps/exams/tests/test_question_submission.py` | 186 | `class SubmissionViewTests(_Base):` |
| `apps/exams/tests/test_question_submission.py` | 187 | `def test_teacher_creates_submission_via_view(self):` |
| `apps/exams/tests/test_question_submission.py` | 210 | `def test_preview_shows_warnings_without_creating(self):` |
| `apps/exams/tests/test_question_submission.py` | 222 | `def test_inbox_requires_exam_center(self):` |
| `apps/exams/tests/test_question_submission.py` | 227 | `def test_review_decide_accept_flow(self):` |
| `apps/exams/tests/test_question_submission.py` | 243 | `def test_reject_requires_note(self):` |
| `apps/exams/tests/test_question_submission.py` | 260 | `def test_teacher_cannot_open_others_submission(self):` |
| `apps/exams/tests/test_question_submission.py` | 270 | `def test_exam_center_can_open_detail(self):` |
| `apps/exams/tests/test_question_submission.py` | 277 | `def test_view_submit_with_group_dropdown(self):` |
| `apps/exams/tests/test_question_submission.py` | 298 | `def test_view_subject_scoped_to_group_subjects(self):` |
| `apps/exams/tests/test_question_submission.py` | 324 | `def test_create_page_renders_subject_dropdown_and_map(self):` |
| `apps/exams/tests/test_question_submission.py` | 341 | `def test_view_rejects_subject_not_in_group(self):` |
| `apps/exams/tests/test_question_submission.py` | 365 | `def test_view_save_respects_selection_and_points(self):` |
| `apps/exams/tests/test_question_submission.py` | 389 | `def test_view_save_carries_teacher_note(self):` |
| `apps/exams/tests/test_question_submission.py` | 414 | `def test_view_submit_requires_group(self):` |
| `apps/exams/tests/test_question_submission.py` | 433 | `class ProfileSectionTests(_Base):` |
| `apps/exams/tests/test_question_submission.py` | 434 | `def test_teacher_sees_dashboard_section(self):` |
| `apps/exams/tests/test_question_submission.py` | 441 | `def test_exam_center_sees_inbox_variant(self):` |
| `apps/exams/tests/test_question_submission.py` | 449 | `def test_teacher_sees_rejected_alert(self):` |
| `apps/exams/tests/test_question_submission.py` | 457 | `def test_student_does_not_get_section(self):` |
| `apps/exams/tests/test_question_submission.py` | 52 | `class _Base(TestCase):` |
| `apps/exams/tests/test_question_submission.py` | 54 | `def setUpTestData(cls):` |
| `apps/exams/tests/test_question_submission.py` | 69 | `def _client_for(self, user):` |
| `apps/exams/tests/test_question_submission.py` | 77 | `def _submission(self, raw_text=VALID_TEXT, title="İnformatika finalı", **overrides):` |
| `apps/exams/tests/test_question_submission.py` | 91 | `class SubmissionServiceTests(_Base):` |
| `apps/exams/tests/test_question_submission.py` | 92 | `def test_submit_builds_snapshot_and_counts(self):` |
| `apps/exams/tests/test_question_word_export.py` | 108 | `def test_payload_respects_language_filter(self):` |
| `apps/exams/tests/test_question_word_export.py` | 115 | `class ExamWordExportViewTests(TestCase):` |
| `apps/exams/tests/test_question_word_export.py` | 116 | `def setUp(self):` |
| `apps/exams/tests/test_question_word_export.py` | 141 | `def test_author_can_export_exam_questions(self):` |
| `apps/exams/tests/test_question_word_export.py` | 149 | `def test_non_author_cannot_export_exam_questions(self):` |
| `apps/exams/tests/test_question_word_export.py` | 30 | `def _parsed(text, correct="B"):` |
| `apps/exams/tests/test_question_word_export.py` | 39 | `def _login_with_org(client, username, org, password="<test-value-masked>"):` |
| `apps/exams/tests/test_question_word_export.py` | 46 | `class QuestionWordExportServiceTests(TestCase):` |
| `apps/exams/tests/test_question_word_export.py` | 47 | `def test_question_lines_mark_correct_with_star(self):` |
| `apps/exams/tests/test_question_word_export.py` | 53 | `def test_build_docx_returns_nonempty_buffer(self):` |
| `apps/exams/tests/test_question_word_export.py` | 64 | `class BankWordExportViewTests(TestCase):` |
| `apps/exams/tests/test_question_word_export.py` | 65 | `def setUp(self):` |
| `apps/exams/tests/test_question_word_export.py` | 83 | `def test_owner_can_export_bank_docx(self):` |
| `apps/exams/tests/test_question_word_export.py` | 91 | `def test_foreign_org_teacher_cannot_export(self):` |
| `apps/exams/tests/test_result_calculation.py` | 113 | `def test_per_question_points_are_respected(self):` |
| `apps/exams/tests/test_result_calculation.py` | 129 | `def test_multiple_correct_options_must_all_match(self):` |
| `apps/exams/tests/test_result_calculation.py` | 150 | `def test_empty_attempt_falls_back_to_legacy_counts(self):` |
| `apps/exams/tests/test_result_calculation.py` | 165 | `def test_non_test_exam_returns_zero_result(self):` |
| `apps/exams/tests/test_result_calculation.py` | 28 | `class TestResultCalculation(TestCase):` |
| `apps/exams/tests/test_result_calculation.py` | 31 | `def setUp(self):` |
| `apps/exams/tests/test_result_calculation.py` | 50 | `def _question(self, *, order, points=1):` |
| `apps/exams/tests/test_result_calculation.py` | 53 | `def _option(self, question, *, text, is_correct):` |
| `apps/exams/tests/test_result_calculation.py` | 56 | `def _attempt(self):` |
| `apps/exams/tests/test_result_calculation.py` | 63 | `def _answer(self, attempt, question, *, selected=None):` |
| `apps/exams/tests/test_result_calculation.py` | 70 | `def test_score_uses_only_delivered_questions_not_the_full_bank(self):` |
| `apps/exams/tests/test_result_calculation.py` | 96 | `def test_unanswered_questions_are_counted_separately(self):` |
| `apps/exams/tests/test_results_duration.py` | 20 | `def test_expire_overdue_and_duration_clamp():` |
| `apps/exams/tests/test_services.py` | 1023 | `def test_sweep_finishes_only_stale_locked_attempts(self):` |
| `apps/exams/tests/test_services.py` | 1041 | `def test_copy_paste_rightclick_are_logged_but_do_not_count_as_violations(self):` |
| `apps/exams/tests/test_services.py` | 105 | `def test_cannot_start_attempt_when_active_exists(self):` |
| `apps/exams/tests/test_services.py` | 1069 | `def test_fullscreen_exit_still_counts_as_violation(self):` |
| `apps/exams/tests/test_services.py` | 1089 | `def test_status_includes_resume_countdown(self):` |
| `apps/exams/tests/test_services.py` | 1103 | `def test_lock_window_disabled_when_zero(self):` |
| `apps/exams/tests/test_services.py` | 1111 | `def test_status_reports_manual_lock_even_when_exam_is_not_supervised(self):` |
| `apps/exams/tests/test_services.py` | 1129 | `class ExamStatisticsAiSummaryServiceTest(SimpleTestCase):` |
| `apps/exams/tests/test_services.py` | 1131 | `def test_returns_localized_missing_key_error_in_azerbaijani(self):` |
| `apps/exams/tests/test_services.py` | 1145 | `def test_returns_localized_missing_key_error_in_english(self):` |
| `apps/exams/tests/test_services.py` | 114 | `def test_create_exam_attempt(self):` |
| `apps/exams/tests/test_services.py` | 1159 | `class ExamAccessControlServicesTest(TestCase):` |
| `apps/exams/tests/test_services.py` | 1162 | `def setUp(self):` |
| `apps/exams/tests/test_services.py` | 1188 | `def test_is_teacher_user(self):` |
| `apps/exams/tests/test_services.py` | 1193 | `def test_is_teacher_user_denies_without_bound_tenant_context(self):` |
| `apps/exams/tests/test_services.py` | 1198 | `def test_is_teacher_user_allows_org_admin_level_membership(self):` |
| `apps/exams/tests/test_services.py` | 1215 | `def test_can_user_access_exam_as_author(self):` |
| `apps/exams/tests/test_services.py` | 1219 | `def test_parse_score_value(self):` |
| `apps/exams/tests/test_services.py` | 1226 | `class ExamParsingServicesTest(TestCase):` |
| `apps/exams/tests/test_services.py` | 1227 | `def test_parse_bulk_mcq_supports_end_question_unlabeled_format(self):` |
| `apps/exams/tests/test_services.py` | 124 | `def test_submit_exam_attempt(self):` |
| `apps/exams/tests/test_services.py` | 1263 | `def test_parse_bulk_mcq_end_question_keeps_e_option_separate(self):` |
| `apps/exams/tests/test_services.py` | 1280 | `def test_parse_bulk_mcq_end_question_merges_wrapped_unlabeled_option(self):` |
| `apps/exams/tests/test_services.py` | 1302 | `def test_parse_bulk_mcq_end_question_splits_joined_missing_e_option(self):` |
| `apps/exams/tests/test_services.py` | 1318 | `def test_parse_bulk_mcq_end_question_keeps_title_and_prompt_together(self):` |
| `apps/exams/tests/test_services.py` | 1340 | `def test_parse_bulk_mcq_end_question_does_not_treat_ip_as_question_number(self):` |
| `apps/exams/tests/test_services.py` | 134 | `class AIWrittenGradingServiceTest(SimpleTestCase):` |
| `apps/exams/tests/test_services.py` | 1359 | `def test_normalize_pdf_extracted_text_keeps_ip_option_intact(self):` |
| `apps/exams/tests/test_services.py` | 135 | `def test_parse_ai_grade_rounds_decimal_scores_like_teacher_points(self):` |
| `apps/exams/tests/test_services.py` | 1368 | `def test_extract_text_from_upload_reads_pdf_with_pypdf(self):` |
| `apps/exams/tests/test_services.py` | 1379 | `def test_extract_text_from_upload_fails_without_pypdf(self):` |
| `apps/exams/tests/test_services.py` | 1388 | `def test_extract_text_from_upload_routes_png_to_ocr(self):` |
| `apps/exams/tests/test_services.py` | 1397 | `def test_extract_text_from_upload_rejects_fake_png(self):` |
| `apps/exams/tests/test_services.py` | 1408 | `def test_extract_text_from_upload_rejects_docx(self):` |
| `apps/exams/tests/test_services.py` | 1414 | `def test_extract_text_from_upload_rejects_legacy_doc_and_rtf(self):` |
| `apps/exams/tests/test_services.py` | 141 | `def test_parse_ai_grade_scales_fractional_score_to_requested_max(self):` |
| `apps/exams/tests/test_services.py` | 1421 | `def test_parse_bulk_mcq_bullet_and_check_markers(self):` |
| `apps/exams/tests/test_services.py` | 1439 | `def test_parse_bulk_mcq_inline_end_question_marker(self):` |
| `apps/exams/tests/test_services.py` | 1462 | `def test_parse_bulk_mcq_missing_end_question_marker_between_questions(self):` |
| `apps/exams/tests/test_services.py` | 147 | `def test_parse_ai_grade_accepts_localized_score_label(self):` |
| `apps/exams/tests/test_services.py` | 1487 | `def test_parse_bulk_mcq_defaulted_correct_emits_error_warning(self):` |
| `apps/exams/tests/test_services.py` | 1496 | `def test_parse_bulk_mcq_marked_correct_has_no_defaulted_warning(self):` |
| `apps/exams/tests/test_services.py` | 1503 | `def test_parse_bulk_mcq_bare_question_number_line_merged(self):` |
| `apps/exams/tests/test_services.py` | 1521 | `def test_parse_bulk_mcq_cyrillic_sequential_labels(self):` |
| `apps/exams/tests/test_services.py` | 1535 | `def test_parse_bulk_mcq_cyrillic_lookalike_labels(self):` |
| `apps/exams/tests/test_services.py` | 1550 | `def test_parse_bulk_mcq_multilang_answer_lines(self):` |
| `apps/exams/tests/test_services.py` | 155 | `def test_grade_written_answer_sends_uploaded_images_to_gemini(self, mock_post):` |
| `apps/exams/tests/test_services.py` | 1565 | `def test_mark_correct_option_lines_label_match_no_false_positive(self):` |
| `apps/exams/tests/test_services.py` | 1572 | `def test_mark_correct_option_lines_empty_fragments_unchanged(self):` |
| `apps/exams/tests/test_services.py` | 1576 | `def test_extract_pdf_highlights_safe_on_invalid_bytes(self):` |
| `apps/exams/tests/test_services.py` | 1582 | `def test_extract_text_from_upload_marks_highlighted_pdf_option(self):` |
| `apps/exams/tests/test_services.py` | 1611 | `def test_highlight_is_scoped_per_question_no_cross_contamination(self):` |
| `apps/exams/tests/test_services.py` | 1654 | `def _build_scanned_pdf(lines):` |
| `apps/exams/tests/test_services.py` | 1676 | `def _ocr_available():` |
| `apps/exams/tests/test_services.py` | 1691 | `def test_scanned_pdf_without_text_raises_clear_error_when_ocr_disabled(self):` |
| `apps/exams/tests/test_services.py` | 1704 | `def test_ocr_extracts_questions_from_scanned_pdf(self):` |
| `apps/exams/tests/test_services.py` | 1722 | `def test_yellow_highlight_mask_detects_region(self):` |
| `apps/exams/tests/test_services.py` | 1740 | `class ExamParsingOcrHighlightHelperTest(SimpleTestCase):` |
| `apps/exams/tests/test_services.py` | 1742 | `def _ocr_page_text_from_words(words, yellow_rects, *, width=260, height=160):` |
| `apps/exams/tests/test_services.py` | 1755 | `class Pix:` |
| `apps/exams/tests/test_services.py` | 1756 | `def tobytes(self, image_format):` |
| `apps/exams/tests/test_services.py` | 1759 | `class Page:` |
| `apps/exams/tests/test_services.py` | 1760 | `def get_text(self, mode=None, **kwargs):` |
| `apps/exams/tests/test_services.py` | 1765 | `def get_pixmap(self, dpi=None):` |
| `apps/exams/tests/test_services.py` | 1770 | `def test_ocr_page_text_marks_option_when_only_answer_word_is_yellow(self):` |
| `apps/exams/tests/test_services.py` | 1785 | `def test_ocr_page_text_marks_option_from_highlighted_continuation_line(self):` |
| `apps/exams/tests/test_services.py` | 1813 | `class ExamGradingServiceTest(TestCase):` |
| `apps/exams/tests/test_services.py` | 1816 | `def setUp(self):` |
| `apps/exams/tests/test_services.py` | 1846 | `def test_grade_exam_answer_sets_score(self):` |
| `apps/exams/tests/test_services.py` | 1852 | `def test_grade_exam_answer_with_feedback(self):` |
| `apps/exams/tests/test_services.py` | 1858 | `def test_grade_exam_answer_decimal_input(self):` |
| `apps/exams/tests/test_services.py` | 1866 | `def test_bulk_grade_answers(self):` |
| `apps/exams/tests/test_services.py` | 1876 | `def test_bulk_grade_answers_pairs_score_to_correct_answer(self):` |
| `apps/exams/tests/test_services.py` | 1892 | `def test_grade_exam_answer_rounds_half_up_instead_of_truncating(self):` |
| `apps/exams/tests/test_services.py` | 1901 | `def test_calculate_attempt_score_test_type_correct(self):` |
| `apps/exams/tests/test_services.py` | 190 | `class AIQuestionGenerationServiceTest(SimpleTestCase):` |
| `apps/exams/tests/test_services.py` | 1914 | `def test_calculate_attempt_score_uses_teacher_score_if_set(self):` |
| `apps/exams/tests/test_services.py` | 1924 | `def test_calculate_test_attempt_result_uses_delivered_answers_only(self):` |
| `apps/exams/tests/test_services.py` | 193 | `def test_generates_test_questions_in_bulk_import_format(self, mock_call_gemini_text):` |
| `apps/exams/tests/test_services.py` | 1965 | `def test_parse_score_value_valid(self):` |
| `apps/exams/tests/test_services.py` | 1972 | `def test_parse_score_value_invalid_returns_default(self):` |
| `apps/exams/tests/test_services.py` | 1978 | `def test_parse_score_value_none_returns_default(self):` |
| `apps/exams/tests/test_services.py` | 1985 | `class AttachTestResultSummariesQueryTests(TestCase):` |
| `apps/exams/tests/test_services.py` | 1993 | `def setUp(self):` |
| `apps/exams/tests/test_services.py` | 2032 | `def test_query_count_is_independent_of_attempt_count(self):` |
| `apps/exams/tests/test_services.py` | 2052 | `def test_attempt_without_answers_falls_back_to_legacy(self):` |
| `apps/exams/tests/test_services.py` | 231 | `def test_generates_written_questions_in_block_format(self, mock_call_gemini_text):` |
| `apps/exams/tests/test_services.py` | 252 | `class ExamGradingServicesTest(TestCase):` |
| `apps/exams/tests/test_services.py` | 255 | `def setUp(self):` |
| `apps/exams/tests/test_services.py` | 288 | `def test_grade_exam_answer(self):` |
| `apps/exams/tests/test_services.py` | 294 | `def test_calculate_attempt_score(self):` |
| `apps/exams/tests/test_services.py` | 303 | `class ExamQuestionRandomizerServicesTest(TestCase):` |
| `apps/exams/tests/test_services.py` | 304 | `def setUp(self):` |
| `apps/exams/tests/test_services.py` | 330 | `def test_generate_random_questions_for_attempt_balances_one_question_per_block(self):` |
| `apps/exams/tests/test_services.py` | 364 | `def test_generate_random_questions_for_attempt_distributes_remainder_to_first_blocks_by_order(self):` |
| `apps/exams/tests/test_services.py` | 401 | `def test_generate_random_questions_for_attempt_gives_extra_question_to_first_block_when_one_remainder(self):` |
| `apps/exams/tests/test_services.py` | 437 | `def test_generate_random_questions_for_attempt_avoids_questions_already_seen_by_four_students(self):` |
| `apps/exams/tests/test_services.py` | 481 | `def test_generate_random_questions_for_attempt_rotates_blocks_when_enough_blocks_exist(self):` |
| `apps/exams/tests/test_services.py` | 527 | `def test_generate_random_questions_for_attempt_balances_existing_difficulty_levels(self):` |
| `apps/exams/tests/test_services.py` | 560 | `def test_ensure_ai_question_difficulties_updates_questions(self, _mock_enabled, _mock_key, mock_classify):` |
| `apps/exams/tests/test_services.py` | 580 | `def test_schedule_ai_question_difficulty_warmup_only_when_active_and_enabled(self, mock_defer):` |
| `apps/exams/tests/test_services.py` | 58 | `class ExamAttemptManagementServicesTest(TestCase):` |
| `apps/exams/tests/test_services.py` | 595 | `class ExamSupervisionServicesTest(TestCase):` |
| `apps/exams/tests/test_services.py` | 596 | `def setUp(self):` |
| `apps/exams/tests/test_services.py` | 61 | `def setUp(self):` |
| `apps/exams/tests/test_services.py` | 624 | `def test_teacher_stop_attempt_persists_removed_status_and_finishes_attempt(self):` |
| `apps/exams/tests/test_services.py` | 640 | `def test_monitor_data_includes_exam_without_supervision_config_or_attempts(self):` |
| `apps/exams/tests/test_services.py` | 647 | `def test_monitor_data_includes_attempt_without_violations(self):` |
| `apps/exams/tests/test_services.py` | 661 | `def test_disabled_supervision_does_not_log_lock_or_keep_config_enabled(self):` |
| `apps/exams/tests/test_services.py` | 693 | `def test_auto_submit_persists_removed_status_and_finishes_attempt(self):` |
| `apps/exams/tests/test_services.py` | 717 | `def test_teacher_resume_attempt_rejects_expired_timed_attempt(self):` |
| `apps/exams/tests/test_services.py` | 743 | `def _supervised_resumable_exam(self, resume_window_seconds=600):` |
| `apps/exams/tests/test_services.py` | 753 | `def _locked_attempt(self, locked_minutes_ago, number=1, user=None):` |
| `apps/exams/tests/test_services.py` | 768 | `def test_lock_action_stamps_locked_at(self):` |
| `apps/exams/tests/test_services.py` | 76 | `def test_get_active_attempt_for_user(self):` |
| `apps/exams/tests/test_services.py` | 792 | `def test_lock_window_auto_finishes_when_teacher_does_not_resume(self):` |
| `apps/exams/tests/test_services.py` | 807 | `def test_lock_window_not_expired_when_within_window(self):` |
| `apps/exams/tests/test_services.py` | 818 | `def test_teacher_resume_stops_lock_countdown(self):` |
| `apps/exams/tests/test_services.py` | 830 | `def test_manual_teacher_lock_does_not_start_auto_finish_window(self):` |
| `apps/exams/tests/test_services.py` | 84 | `def test_get_active_attempt_for_user_expires_timed_out_attempt(self):` |
| `apps/exams/tests/test_services.py` | 852 | `def test_manual_lock_is_resumable_even_with_no_second_chance(self):` |
| `apps/exams/tests/test_services.py` | 882 | `def test_auto_lock_resume_still_honours_no_second_chance(self):` |
| `apps/exams/tests/test_services.py` | 905 | `def test_snapshot_surfaces_coding_draft_files(self):` |
| `apps/exams/tests/test_services.py` | 956 | `def test_snapshot_lists_test_questions_with_selected_options(self):` |
| `apps/exams/tests/test_services.py` | 98 | `def test_can_user_start_new_attempt(self):` |
| `apps/exams/tests/test_services.py` | 997 | `def test_snapshot_uses_attempt_answer_order_and_omits_unassigned_questions(self):` |
| `apps/exams/tests/test_student_pin_throttle.py` | 21 | `class StudentPinThrottleTests(TestCase):` |
| `apps/exams/tests/test_student_pin_throttle.py` | 22 | `def setUp(self):` |
| `apps/exams/tests/test_student_pin_throttle.py` | 25 | `def test_allows_up_to_limit_then_blocks(self):` |
| `apps/exams/tests/test_student_pin_throttle.py` | 30 | `def test_per_username_isolation_is_freeze_safe(self):` |
| `apps/exams/tests/test_student_pin_throttle.py` | 36 | `def test_case_and_whitespace_normalised(self):` |
| `apps/exams/tests/test_student_pin_throttle.py` | 41 | `def test_blank_username_never_limited(self):` |
| `apps/exams/tests/test_student_pin_throttle.py` | 45 | `def test_zero_limit_disables_throttle(self):` |
| `apps/exams/tests/test_supervision_consumer.py` | 100 | `def test_rejects_unknown_attempt(self):` |
| `apps/exams/tests/test_supervision_consumer.py` | 36 | `class ExamSupervisionConsumerAuthTests(TransactionTestCase):` |
| `apps/exams/tests/test_supervision_consumer.py` | 37 | `def setUp(self):` |
| `apps/exams/tests/test_supervision_consumer.py` | 62 | `def _session_headers(self, username):` |
| `apps/exams/tests/test_supervision_consumer.py` | 68 | `def _try_connect(self, path, headers):` |
| `apps/exams/tests/test_supervision_consumer.py` | 69 | `async def scenario():` |
| `apps/exams/tests/test_supervision_consumer.py` | 80 | `def _path(self, attempt_id):` |
| `apps/exams/tests/test_supervision_consumer.py` | 83 | `def test_accepts_attempt_owner(self):` |
| `apps/exams/tests/test_supervision_consumer.py` | 87 | `def test_rejects_other_student(self):` |
| `apps/exams/tests/test_supervision_consumer.py` | 92 | `def test_accepts_exam_author(self):` |
| `apps/exams/tests/test_supervision_consumer.py` | 96 | `def test_rejects_unauthenticated(self):` |
| `apps/exams/tests/test_text_extraction_jobs.py` | 102 | `def test_student_forbidden(self, client, django_user_model, org):` |
| `apps/exams/tests/test_text_extraction_jobs.py` | 114 | `class TestStatusEndpoint:` |
| `apps/exams/tests/test_text_extraction_jobs.py` | 115 | `def test_owner_sees_result(self, teacher_client, teacher):` |
| `apps/exams/tests/test_text_extraction_jobs.py` | 122 | `def test_other_teacher_gets_404(self, teacher_client, client, django_user_model, org):` |
| `apps/exams/tests/test_text_extraction_jobs.py` | 136 | `class TestTaskDirect:` |
| `apps/exams/tests/test_text_extraction_jobs.py` | 137 | `def test_missing_job_is_noop(self):` |
| `apps/exams/tests/test_text_extraction_jobs.py` | 141 | `class TestAiGenerationJob:` |
| `apps/exams/tests/test_text_extraction_jobs.py` | 144 | `def _post_ai(self, client, exam_slug, extra=None):` |
| `apps/exams/tests/test_text_extraction_jobs.py` | 154 | `def exam(self, teacher, org):` |
| `apps/exams/tests/test_text_extraction_jobs.py` | 164 | `def test_eager_success_returns_classic_payload(self, teacher_client, exam, monkeypatch):` |
| `apps/exams/tests/test_text_extraction_jobs.py` | 167 | `def fake_generate(**kwargs):` |
| `apps/exams/tests/test_text_extraction_jobs.py` | 183 | `def test_eager_service_refusal_maps_to_400(self, teacher_client, exam, monkeypatch):` |
| `apps/exams/tests/test_text_extraction_jobs.py` | 196 | `def test_eager_service_exception_maps_to_500(self, teacher_client, exam, monkeypatch):` |
| `apps/exams/tests/test_text_extraction_jobs.py` | 199 | `def boom(**kw):` |
| `apps/exams/tests/test_text_extraction_jobs.py` | 19 | `def org(django_user_model):` |
| `apps/exams/tests/test_text_extraction_jobs.py` | 207 | `def test_uploaded_file_text_reaches_service(self, teacher_client, exam, monkeypatch):` |
| `apps/exams/tests/test_text_extraction_jobs.py` | 212 | `def fake_generate(**kwargs):` |
| `apps/exams/tests/test_text_extraction_jobs.py` | 228 | `class TestStashMathFlag:` |
| `apps/exams/tests/test_text_extraction_jobs.py` | 231 | `def test_txt_with_stash_flag_succeeds_without_token(self, teacher_client):` |
| `apps/exams/tests/test_text_extraction_jobs.py` | 243 | `def test_pdf_stash_failure_is_non_fatal(self, teacher_client, monkeypatch):` |
| `apps/exams/tests/test_text_extraction_jobs.py` | 252 | `def boom(f):` |
| `apps/exams/tests/test_text_extraction_jobs.py` | 267 | `class TestExportJobs:` |
| `apps/exams/tests/test_text_extraction_jobs.py` | 271 | `def exam(self, teacher, org):` |
| `apps/exams/tests/test_text_extraction_jobs.py` | 276 | `def test_small_dataset_stays_sync(self, teacher_client, exam):` |
| `apps/exams/tests/test_text_extraction_jobs.py` | 283 | `def test_large_dataset_goes_through_job_eager(self, teacher_client, exam, settings):` |
| `apps/exams/tests/test_text_extraction_jobs.py` | 294 | `def test_pending_job_redirects_to_waiting_page(self, teacher_client, teacher, org, exam, settings, monkeypatch):` |
| `apps/exams/tests/test_text_extraction_jobs.py` | 317 | `def test_download_is_owner_only(self, teacher_client, client, django_user_model, org, exam, settings):` |
| `apps/exams/tests/test_text_extraction_jobs.py` | 332 | `def test_registry_org_mismatch_fails_closed(self, teacher, org, django_user_model, exam):` |
| `apps/exams/tests/test_text_extraction_jobs.py` | 34 | `def _make_member(django_user_model, org, *, username, profile_role, role_name):` |
| `apps/exams/tests/test_text_extraction_jobs.py` | 354 | `class TestWorkerDeadFallback:` |
| `apps/exams/tests/test_text_extraction_jobs.py` | 358 | `def _fast_watchdog(self, settings):` |
| `apps/exams/tests/test_text_extraction_jobs.py` | 362 | `def _dead_worker(self, monkeypatch):` |
| `apps/exams/tests/test_text_extraction_jobs.py` | 370 | `def test_extract_falls_back_to_sync(self, teacher_client, _dead_worker):` |
| `apps/exams/tests/test_text_extraction_jobs.py` | 377 | `def test_ai_falls_back_to_classic_response(self, teacher_client, teacher, org, _dead_worker, monkeypatch):` |
| `apps/exams/tests/test_text_extraction_jobs.py` | 397 | `def test_export_falls_back_to_attachment(self, teacher_client, teacher, org, _dead_worker, settings):` |
| `apps/exams/tests/test_text_extraction_jobs.py` | 407 | `class TestCasClaim:` |
| `apps/exams/tests/test_text_extraction_jobs.py` | 410 | `def test_second_run_is_noop(self, teacher_client, monkeypatch):` |
| `apps/exams/tests/test_text_extraction_jobs.py` | 418 | `def boom(f):` |
| `apps/exams/tests/test_text_extraction_jobs.py` | 425 | `class TestMathTokenPropagation:` |
| `apps/exams/tests/test_text_extraction_jobs.py` | 428 | `def test_token_reaches_status_meta(self, teacher_client, monkeypatch):` |
| `apps/exams/tests/test_text_extraction_jobs.py` | 52 | `def teacher(django_user_model, org):` |
| `apps/exams/tests/test_text_extraction_jobs.py` | 57 | `def teacher_client(client, teacher, org):` |
| `apps/exams/tests/test_text_extraction_jobs.py` | 65 | `def _upload(name="questions.txt", content=b"1. Sual metni?\nA) a\nB) b\n"):` |
| `apps/exams/tests/test_text_extraction_jobs.py` | 69 | `class TestStartEndpoint:` |
| `apps/exams/tests/test_text_extraction_jobs.py` | 70 | `def test_txt_upload_extracts_text(self, teacher_client, teacher):` |
| `apps/exams/tests/test_text_extraction_jobs.py` | 84 | `def test_missing_file_rejected(self, teacher_client):` |
| `apps/exams/tests/test_text_extraction_jobs.py` | 88 | `def test_blocked_extension_fails_job(self, teacher_client):` |
| `apps/exams/tests/test_text_extraction_jobs.py` | 98 | `def test_anonymous_redirected(self, client):` |
| `apps/exams/tests/test_views.py` | 1002 | `def test_student_cannot_delete_exam(self):` |
| `apps/exams/tests/test_views.py` | 100 | `def setUp(self):` |
| `apps/exams/tests/test_views.py` | 1012 | `def test_delete_exam_redirects_to_profile_my_exams_section(self):` |
| `apps/exams/tests/test_views.py` | 1022 | `def test_delete_exam_soft_deletes_and_preserves_attempts(self):` |
| `apps/exams/tests/test_views.py` | 1039 | `def test_soft_deleted_exam_is_hidden_from_teacher_edit_lookup(self):` |
| `apps/exams/tests/test_views.py` | 1045 | `def test_deleted_exams_list_lists_soft_deleted_exam(self):` |
| `apps/exams/tests/test_views.py` | 1051 | `def test_restore_exam_brings_it_back(self):` |
| `apps/exams/tests/test_views.py` | 1059 | `def test_permanent_delete_removes_exam_and_attempts(self):` |
| `apps/exams/tests/test_views.py` | 1072 | `def test_permanent_delete_rejects_non_deleted_exam(self):` |
| `apps/exams/tests/test_views.py` | 1078 | `def test_view_results_of_deleted_exam_is_readonly(self):` |
| `apps/exams/tests/test_views.py` | 1101 | `def test_edit_other_tenant_exam_is_not_found(self):` |
| `apps/exams/tests/test_views.py` | 1105 | `def test_edit_exam_full_page_redirects_to_profile_my_exams(self):` |
| `apps/exams/tests/test_views.py` | 1111 | `def test_modal_edit_exam_updates_random_question_count(self):` |
| `apps/exams/tests/test_views.py` | 1135 | `def test_teacher_exam_detail_defaults_to_generic_back_with_profile_fallback(self):` |
| `apps/exams/tests/test_views.py` | 1143 | `def test_teacher_exam_detail_uses_explicit_course_dashboard_return_url(self):` |
| `apps/exams/tests/test_views.py` | 1155 | `def test_teacher_exam_detail_questions_bank_link_preserves_return_to(self):` |
| `apps/exams/tests/test_views.py` | 1168 | `def test_teacher_exam_detail_bulk_add_link_preserves_return_to(self):` |
| `apps/exams/tests/test_views.py` | 1181 | `def test_teacher_exam_detail_live_results_link_preserves_return_to(self):` |
| `apps/exams/tests/test_views.py` | 1194 | `def test_teacher_exam_detail_includes_archive_toggle(self):` |
| `apps/exams/tests/test_views.py` | 1207 | `def test_teacher_can_archive_from_detail_and_stay_on_detail(self):` |
| `apps/exams/tests/test_views.py` | 1219 | `def test_teacher_exam_detail_initially_renders_first_question_batch(self):` |
| `apps/exams/tests/test_views.py` | 1240 | `def test_teacher_exam_detail_questions_page_returns_next_batch(self):` |
| `apps/exams/tests/test_views.py` | 1263 | `def test_teacher_can_toggle_exam_results_visibility(self):` |
| `apps/exams/tests/test_views.py` | 1283 | `def test_hidden_exam_results_are_not_visible_to_student(self):` |
| `apps/exams/tests/test_views.py` | 1314 | `def test_teacher_exam_detail_disables_live_start_when_exam_is_passive(self):` |
| `apps/exams/tests/test_views.py` | 1328 | `def test_delete_exam_question_resequences_remaining_question_orders(self):` |
| `apps/exams/tests/test_views.py` | 1354 | `def test_teacher_exam_detail_falls_back_to_safe_referer_when_return_to_missing(self):` |
| `apps/exams/tests/test_views.py` | 1366 | `def test_teacher_exam_detail_ignores_internal_question_bank_referer(self):` |
| `apps/exams/tests/test_views.py` | 1377 | `def test_teacher_exam_results_keeps_generic_source_back_label(self):` |
| `apps/exams/tests/test_views.py` | 1393 | `def test_teacher_exam_results_renders_bulk_delete_controls(self):` |
| `apps/exams/tests/test_views.py` | 1407 | `def test_delete_exam_attempts_removes_selected_attempts(self):` |
| `apps/exams/tests/test_views.py` | 1431 | `def test_teacher_exam_results_reveals_student_name_for_test_attempts(self):` |
| `apps/exams/tests/test_views.py` | 143 | `def _assign_profile(self, user, organization, role):` |
| `apps/exams/tests/test_views.py` | 1449 | `def test_test_exam_results_use_delivered_question_set_on_teacher_and_student_pages(self):` |
| `apps/exams/tests/test_views.py` | 146 | `def _login_as(self, user):` |
| `apps/exams/tests/test_views.py` | 149 | `def _set_active_org(self, organization):` |
| `apps/exams/tests/test_views.py` | 1513 | `def test_test_exam_result_falls_back_to_legacy_counts_without_rebuilding_finished_attempt(self):` |
| `apps/exams/tests/test_views.py` | 1538 | `def test_teacher_exam_results_keeps_written_student_name_hidden_until_review_is_completed(self):` |
| `apps/exams/tests/test_views.py` | 154 | `def _group_payload(self, **overrides):` |
| `apps/exams/tests/test_views.py` | 1578 | `def test_teacher_exam_results_shows_recheck_then_view_for_written_attempts(self):` |
| `apps/exams/tests/test_views.py` | 1617 | `def test_teacher_exam_results_reveals_student_name_when_written_grade_is_visible_without_timestamp(self):` |
| `apps/exams/tests/test_views.py` | 1642 | `def test_teacher_exam_results_reveals_pending_written_student_name_when_org_override_enabled(self):` |
| `apps/exams/tests/test_views.py` | 164 | `def test_my_groups_page_links_to_create_group_template(self):` |
| `apps/exams/tests/test_views.py` | 1669 | `def test_teacher_exam_results_keeps_recheck_window_when_org_override_enabled(self):` |
| `apps/exams/tests/test_views.py` | 1698 | `def test_teacher_view_attempt_keeps_generic_source_back_label(self):` |
| `apps/exams/tests/test_views.py` | 1716 | `def test_teacher_view_attempt_keeps_written_student_name_anonymous_before_review(self):` |
| `apps/exams/tests/test_views.py` | 1739 | `def test_teacher_view_attempt_shows_finished_at_and_computed_duration(self):` |
| `apps/exams/tests/test_views.py` | 177 | `def test_teacher_cannot_create_or_manage_groups(self):` |
| `apps/exams/tests/test_views.py` | 1785 | `def test_teacher_check_attempt_includes_confirm_modal_and_integer_score_input(self):` |
| `apps/exams/tests/test_views.py` | 1820 | `def test_teacher_check_attempt_shows_exam_timing_summary(self):` |
| `apps/exams/tests/test_views.py` | 1866 | `def test_teacher_check_attempt_shows_real_student_name_when_org_override_enabled(self):` |
| `apps/exams/tests/test_views.py` | 1899 | `def test_teacher_check_attempt_returns_to_pending_review_when_opened_from_queue(self):` |
| `apps/exams/tests/test_views.py` | 193 | `def test_group_manage_permission_delegation(self):` |
| `apps/exams/tests/test_views.py` | 1949 | `def test_teacher_check_attempt_post_updates_question_max_points(self):` |
| `apps/exams/tests/test_views.py` | 1995 | `def test_teacher_check_attempt_post_keeps_score_above_existing_question_points(self):` |
| `apps/exams/tests/test_views.py` | 2042 | `def test_ai_grade_answer_uses_posted_max_points(self, mock_grade_written_answer):` |
| `apps/exams/tests/test_views.py` | 2086 | `def test_ai_grade_answer_accepts_image_only_written_submission(self, mock_post):` |
| `apps/exams/tests/test_views.py` | 2135 | `def test_teacher_check_attempt_marks_image_only_answer_as_not_empty(self):` |
| `apps/exams/tests/test_views.py` | 2172 | `class StudentExamVisibilityFilteringTest(TestCase):` |
| `apps/exams/tests/test_views.py` | 2173 | `def setUp(self):` |
| `apps/exams/tests/test_views.py` | 221 | `def test_groups_are_created_and_listed_per_active_tenant(self):` |
| `apps/exams/tests/test_views.py` | 2354 | `def test_student_available_exam_list_includes_public_exams_in_active_tenant(self):` |
| `apps/exams/tests/test_views.py` | 2368 | `def test_student_available_exam_list_hides_soft_deleted_exam(self):` |
| `apps/exams/tests/test_views.py` | 2381 | `def test_student_exam_list_never_shows_final_or_midterm(self):` |
| `apps/exams/tests/test_views.py` | 2425 | `def test_student_exam_list_filters_practical_separately_from_written(self):` |
| `apps/exams/tests/test_views.py` | 2451 | `def test_student_exam_type_counts_exclude_attempt_exhausted_exams(self):` |
| `apps/exams/tests/test_views.py` | 2476 | `def test_student_exam_card_shows_category_and_mechanic_badges(self):` |
| `apps/exams/tests/test_views.py` | 2496 | `def test_student_exam_views_restore_profile_org_context_when_session_org_is_missing(self):` |
| `apps/exams/tests/test_views.py` | 2523 | `def test_student_assigned_exam_list_shows_only_assigned_in_active_tenant(self):` |
| `apps/exams/tests/test_views.py` | 2556 | `def test_course_assigned_exam_can_be_started_by_student(self):` |
| `apps/exams/tests/test_views.py` | 255 | `def test_group_creation_rejects_cross_tenant_students(self):` |
| `apps/exams/tests/test_views.py` | 2561 | `def test_in_progress_exam_resumes_from_start_route_when_attempt_limit_is_one(self):` |
| `apps/exams/tests/test_views.py` | 2576 | `def test_in_progress_code_exam_resumes_without_reasking_for_code(self):` |
| `apps/exams/tests/test_views.py` | 2589 | `def test_timed_out_test_attempt_no_longer_resumes_from_start_route(self):` |
| `apps/exams/tests/test_views.py` | 2610 | `def test_timed_out_written_attempt_starts_new_attempt_when_attempts_remain(self):` |
| `apps/exams/tests/test_views.py` | 2645 | `def test_take_exam_redirects_timed_out_written_attempt_to_result(self):` |
| `apps/exams/tests/test_views.py` | 265 | `def test_admin_assigns_subjects_to_group(self):` |
| `apps/exams/tests/test_views.py` | 2679 | `def test_take_exam_finished_attempt_ajax_finish_returns_result_json(self):` |
| `apps/exams/tests/test_views.py` | 2704 | `def test_take_exam_finished_attempt_ajax_autosave_returns_result_json(self):` |
| `apps/exams/tests/test_views.py` | 2737 | `def _take_exam_static_source(relative_path):` |
| `apps/exams/tests/test_views.py` | 2748 | `def test_take_exam_uses_deadline_based_timer_logic_for_background_tabs(self):` |
| `apps/exams/tests/test_views.py` | 2773 | `def test_take_exam_uses_five_minute_server_autosave_with_jitter(self):` |
| `apps/exams/tests/test_views.py` | 2792 | `def test_take_exam_time_warning_modal_strings_are_translated_for_supported_languages(self):` |
| `apps/exams/tests/test_views.py` | 2817 | `def test_take_exam_autosave_updates_only_changed_questions(self):` |
| `apps/exams/tests/test_views.py` | 285 | `def test_group_list_contains_edit_and_delete_routes(self):` |
| `apps/exams/tests/test_views.py` | 2873 | `def test_take_exam_autosave_ignores_file_and_paint_payloads(self):` |
| `apps/exams/tests/test_views.py` | 2921 | `def test_take_exam_rejects_too_many_files_for_one_written_answer(self):` |
| `apps/exams/tests/test_views.py` | 2961 | `def test_take_exam_test_autosave_skips_full_score_recalculation(self):` |
| `apps/exams/tests/test_views.py` | 298 | `def test_add_single_student_to_group(self):` |
| `apps/exams/tests/test_views.py` | 3017 | `def test_course_dashboard_student_exam_actions_use_info_modal(self):` |
| `apps/exams/tests/test_views.py` | 3034 | `def test_course_dashboard_exam_modal_embeds_language_options(self):` |
| `apps/exams/tests/test_views.py` | 3062 | `def test_student_exam_list_actions_use_bootstrap_info_modal(self):` |
| `apps/exams/tests/test_views.py` | 307 | `def test_add_student_rejects_cross_tenant(self):` |
| `apps/exams/tests/test_views.py` | 3088 | `def test_student_exam_list_modal_embeds_language_select_for_multilingual_exam(self):` |
| `apps/exams/tests/test_views.py` | 3127 | `def test_multilingual_exam_start_uses_selected_language_without_language_page(self):` |
| `apps/exams/tests/test_views.py` | 316 | `def test_add_student_requires_post(self):` |
| `apps/exams/tests/test_views.py` | 3172 | `def test_course_dashboard_student_history_button_shows_attempt_count(self):` |
| `apps/exams/tests/test_views.py` | 3189 | `def test_unassigned_private_exam_cannot_be_started(self):` |
| `apps/exams/tests/test_views.py` | 3195 | `def test_unassigned_private_exam_redirects_back_to_profile_assigned_section_when_requested(self):` |
| `apps/exams/tests/test_views.py` | 3204 | `def test_assigned_exam_with_code_requires_code_before_start(self):` |
| `apps/exams/tests/test_views.py` | 3210 | `def test_assigned_exam_with_code_starts_after_correct_code(self):` |
| `apps/exams/tests/test_views.py` | 3218 | `def test_assigned_exam_without_questions_cannot_be_started(self):` |
| `apps/exams/tests/test_views.py` | 3227 | `def test_assigned_code_exam_without_questions_cannot_be_started(self):` |
| `apps/exams/tests/test_views.py` | 3236 | `def test_take_exam_redirects_when_attempt_has_no_questions(self):` |
| `apps/exams/tests/test_views.py` | 323 | `def test_student_cannot_access_group_management_routes(self):` |
| `apps/exams/tests/test_views.py` | 3247 | `def test_exam_code_check_rejects_post_without_csrf_token(self):` |
| `apps/exams/tests/test_views.py` | 3262 | `def test_exam_code_check_sql_injection_payload_does_not_bypass_lookup(self):` |
| `apps/exams/tests/test_views.py` | 3271 | `def test_unassigned_exam_with_code_cannot_start_even_with_valid_code(self):` |
| `apps/exams/tests/test_views.py` | 3280 | `def test_unassigned_exam_with_code_redirects_back_to_profile_assigned_section_when_requested(self):` |
| `apps/exams/tests/test_views.py` | 3294 | `def test_other_tenant_exam_cannot_be_started(self):` |
| `apps/exams/tests/test_views.py` | 3299 | `def test_other_tenant_exam_code_check_is_not_found(self):` |
| `apps/exams/tests/test_views.py` | 3317 | `def test_other_tenant_exam_result_is_not_found(self):` |
| `apps/exams/tests/test_views.py` | 3329 | `def test_public_exams_are_visible_to_other_authenticated_roles(self):` |
| `apps/exams/tests/test_views.py` | 3340 | `def test_az_student_exam_list_uses_localized_strings(self):` |
| `apps/exams/tests/test_views.py` | 3361 | `def test_student_exam_list_modal_strings_are_translated_for_supported_languages(self):` |
| `apps/exams/tests/test_views.py` | 3384 | `def test_az_exam_result_uses_localized_strings(self):` |
| `apps/exams/tests/test_views.py` | 3436 | `def test_exam_result_page_avoids_placeholder_copy_in_all_supported_languages(self):` |
| `apps/exams/tests/test_views.py` | 345 | `def test_teacher_can_multi_assign_teachers(self):` |
| `apps/exams/tests/test_views.py` | 3488 | `def test_filtered_exam_history_shows_only_selected_exam_attempts(self):` |
| `apps/exams/tests/test_views.py` | 3521 | `def test_exam_result_defaults_back_to_course_dashboard_and_keeps_history_link_distinct(self):` |
| `apps/exams/tests/test_views.py` | 3550 | `def test_exam_result_restores_original_back_url_when_opened_from_history(self):` |
| `apps/exams/tests/test_views.py` | 3569 | `def test_take_exam_hides_previous_attempts_summary_while_attempt_is_active(self):` |
| `apps/exams/tests/test_views.py` | 3595 | `class TeacherViewAttemptSearchPaginationTest(TestCase):` |
| `apps/exams/tests/test_views.py` | 3596 | `def setUp(self):` |
| `apps/exams/tests/test_views.py` | 360 | `def test_org_admin_can_access_teacher_groups_url_and_multi_assign(self):` |
| `apps/exams/tests/test_views.py` | 3656 | `def test_teacher_view_attempt_supports_search_and_questions_pagination(self):` |
| `apps/exams/tests/test_views.py` | 3685 | `def test_teacher_view_attempt_search_matches_option_text(self):` |
| `apps/exams/tests/test_views.py` | 3696 | `class StudentExamResultVisibilityWindowTest(TestCase):` |
| `apps/exams/tests/test_views.py` | 3697 | `def setUp(self):` |
| `apps/exams/tests/test_views.py` | 3738 | `def test_exam_result_hidden_while_teacher_review_window_open(self):` |
| `apps/exams/tests/test_views.py` | 3743 | `def test_exam_result_visible_after_teacher_review_window_closes(self):` |
| `apps/exams/tests/test_views.py` | 3751 | `class TeacherQuestionsBankViewTest(TestCase):` |
| `apps/exams/tests/test_views.py` | 3752 | `def setUp(self):` |
| `apps/exams/tests/test_views.py` | 3791 | `def test_questions_bank_supports_search_status_filter_and_pagination(self):` |
| `apps/exams/tests/test_views.py` | 3809 | `def test_questions_bank_truncates_overlong_search_query(self):` |
| `apps/exams/tests/test_views.py` | 380 | `def test_org_admin_cannot_assign_more_than_three_teachers(self):` |
| `apps/exams/tests/test_views.py` | 3821 | `def test_questions_bank_drops_nested_exam_return_to_from_filter_forms(self):` |
| `apps/exams/tests/test_views.py` | 3835 | `def test_questions_bank_bulk_deactivate_selected(self):` |
| `apps/exams/tests/test_views.py` | 3852 | `def test_questions_bank_single_question_activate_request_works(self):` |
| `apps/exams/tests/test_views.py` | 3871 | `def test_questions_bank_bulk_delete_selected(self):` |
| `apps/exams/tests/test_views.py` | 3888 | `def test_questions_bank_filters_by_language(self):` |
| `apps/exams/tests/test_views.py` | 3905 | `def test_questions_bank_deletes_selected_language_questions(self):` |
| `apps/exams/tests/test_views.py` | 3927 | `def test_questions_bank_deletes_all_exam_questions(self):` |
| `apps/exams/tests/test_views.py` | 3945 | `def test_questions_bank_search_matches_option_text_without_duplicates(self):` |
| `apps/exams/tests/test_views.py` | 3969 | `def test_questions_bank_bulk_redirect_preserves_sort_filter(self):` |
| `apps/exams/tests/test_views.py` | 3989 | `def test_questions_bank_back_link_preserves_original_return_to(self):` |
| `apps/exams/tests/test_views.py` | 399 | `def test_org_admin_cannot_assign_cross_tenant_teachers(self):` |
| `apps/exams/tests/test_views.py` | 4002 | `def test_questions_bank_bulk_add_link_preserves_original_return_to(self):` |
| `apps/exams/tests/test_views.py` | 4015 | `def test_test_question_bank_view_bank_link_preserves_original_return_to(self):` |
| `apps/exams/tests/test_views.py` | 4028 | `def test_test_question_bank_back_link_preserves_original_return_to(self):` |
| `apps/exams/tests/test_views.py` | 4041 | `def test_test_question_bank_shows_ai_generation_panel(self):` |
| `apps/exams/tests/test_views.py` | 4053 | `def _end_question_import_text(self, count):` |
| `apps/exams/tests/test_views.py` | 4071 | `def test_test_question_bank_preview_checks_all_questions_and_adds_compact_save_fields(self):` |
| `apps/exams/tests/test_views.py` | 4087 | `def test_test_question_bank_downloads_problem_report_xlsx(self):` |
| `apps/exams/tests/test_views.py` | 413 | `def test_non_student_member_cannot_create_group(self):` |
| `apps/exams/tests/test_views.py` | 4144 | `def test_test_question_bank_preview_keeps_filter_counts_for_warning_types(self):` |
| `apps/exams/tests/test_views.py` | 4184 | `def test_test_question_bank_saves_500_end_question_import_with_compact_payload(self, mock_schedule_warmup):` |
| `apps/exams/tests/test_views.py` | 4212 | `def test_test_question_bank_compact_empty_selection_saves_no_questions(self, mock_schedule_warmup):` |
| `apps/exams/tests/test_views.py` | 4230 | `def test_test_question_bank_empty_compact_field_falls_back_to_legacy_selection(self, mock_schedule_warmup):` |
| `apps/exams/tests/test_views.py` | 4253 | `def test_test_question_bank_saves_large_import_with_long_option_text(self, mock_schedule_warmup):` |
| `apps/exams/tests/test_views.py` | 425 | `def test_update_and_delete_routes_are_tenant_scoped(self):` |
| `apps/exams/tests/test_views.py` | 4295 | `def test_ai_generate_question_bank_passes_prompt_and_uploaded_source_to_service(self, mock_generate):` |
| `apps/exams/tests/test_views.py` | 42 | `def _assign_user_to_org(user, organization, profile_role, *, membership_role_name=None):` |
| `apps/exams/tests/test_views.py` | 4323 | `def test_questions_bank_bulk_delete_resequences_remaining_question_orders(self):` |
| `apps/exams/tests/test_views.py` | 4340 | `def test_questions_bank_bulk_redirect_preserves_return_navigation(self):` |
| `apps/exams/tests/test_views.py` | 4359 | `def test_create_question_bank_cancel_link_preserves_original_return_to(self):` |
| `apps/exams/tests/test_views.py` | 4373 | `def test_create_question_bank_shows_student_question_count_setting_for_written_exam(self):` |
| `apps/exams/tests/test_views.py` | 4384 | `def test_create_question_bank_shows_student_question_count_setting_for_coding_exam(self):` |
| `apps/exams/tests/test_views.py` | 4397 | `def test_process_question_bank_success_redirect_preserves_return_navigation(self):` |
| `apps/exams/tests/test_views.py` | 4417 | `class WrittenExamPaintInheritanceTest(TestCase):` |
| `apps/exams/tests/test_views.py` | 4418 | `def setUp(self):` |
| `apps/exams/tests/test_views.py` | 442 | `def test_non_superadmin_cannot_switch_session_to_other_tenant(self):` |
| `apps/exams/tests/test_views.py` | 4482 | `def test_take_exam_hides_paint_for_question_with_explicit_disable(self):` |
| `apps/exams/tests/test_views.py` | 4491 | `def test_take_exam_post_clears_hidden_question_paint_even_if_payload_forces_it(self):` |
| `apps/exams/tests/test_views.py` | 449 | `def test_superadmin_can_manage_any_active_tenant(self):` |
| `apps/exams/tests/test_views.py` | 4509 | `def test_edit_question_unchecked_paint_creates_question_level_disable(self):` |
| `apps/exams/tests/test_views.py` | 4527 | `def test_edit_question_form_shows_checked_paint_checkbox_when_state_comes_from_block(self):` |
| `apps/exams/tests/test_views.py` | 4542 | `def test_edit_question_form_shows_question_source_when_question_override_disables_paint(self):` |
| `apps/exams/tests/test_views.py` | 4555 | `def test_add_written_question_without_blocks_creates_default_block_and_assigns_question(self):` |
| `apps/exams/tests/test_views.py` | 4583 | `def test_add_written_question_requires_block_when_blocks_exist(self):` |
| `apps/exams/tests/test_views.py` | 4601 | `def test_process_question_bank_preserves_question_override_and_saves_block_paint(self):` |
| `apps/exams/tests/test_views.py` | 4627 | `def test_create_question_bank_shows_ai_panel_per_written_block(self):` |
| `apps/exams/tests/test_views.py` | 4642 | `class SupervisionTeacherApiTest(TestCase):` |
| `apps/exams/tests/test_views.py` | 4643 | `def setUp(self):` |
| `apps/exams/tests/test_views.py` | 4686 | `def test_teacher_resume_api_rejects_attempt_after_exam_duration(self):` |
| `apps/exams/tests/test_views.py` | 4702 | `def test_student_status_api_keeps_manual_lock_visible_after_exam_duration(self):` |
| `apps/exams/tests/test_views.py` | 4718 | `def test_student_status_api_reports_manual_lock_without_supervision_config(self):` |
| `apps/exams/tests/test_views.py` | 4732 | `def test_unsupervised_student_exam_loads_manual_lock_listener(self):` |
| `apps/exams/tests/test_views.py` | 4751 | `def test_student_exam_omits_supervision_listener_when_feature_disabled(self):` |
| `apps/exams/tests/test_views.py` | 4767 | `def test_supervision_monitor_shows_exam_without_config_or_violations(self):` |
| `apps/exams/tests/test_views.py` | 4788 | `class ExamOrganizationRequiredTest(TestCase):` |
| `apps/exams/tests/test_views.py` | 4794 | `def setUp(self):` |
| `apps/exams/tests/test_views.py` | 4809 | `def test_exam_model_raises_validation_error_without_organization(self):` |
| `apps/exams/tests/test_views.py` | 480 | `class TeacherExamListOwnershipFilteringTest(TestCase):` |
| `apps/exams/tests/test_views.py` | 481 | `def setUp(self):` |
| `apps/exams/tests/test_views.py` | 4828 | `def test_exam_model_auto_assigns_organization_from_author_profile(self):` |
| `apps/exams/tests/test_views.py` | 4838 | `def test_exam_model_auto_assigns_organization_from_course(self):` |
| `apps/exams/tests/test_views.py` | 4857 | `def test_create_exam_view_raises_permission_denied_without_active_organization(self):` |
| `apps/exams/tests/test_views.py` | 4880 | `def test_exam_with_explicit_organization_is_created_successfully(self):` |
| `apps/exams/tests/test_views.py` | 558 | `def test_teacher_exam_list_redirects_to_profile_my_exams_section(self):` |
| `apps/exams/tests/test_views.py` | 563 | `def test_modal_create_exam_includes_course_hidden_field_when_requested_from_course_dashboard(self):` |
| `apps/exams/tests/test_views.py` | 574 | `def test_modal_create_exam_form_includes_random_question_count_with_default_fifty(self):` |
| `apps/exams/tests/test_views.py` | 586 | `def test_modal_edit_written_exam_includes_random_question_count(self):` |
| `apps/exams/tests/test_views.py` | 606 | `def test_modal_edit_coding_exam_includes_random_question_count(self):` |
| `apps/exams/tests/test_views.py` | 626 | `def test_modal_create_exam_links_new_exam_to_requested_course(self):` |
| `apps/exams/tests/test_views.py` | 648 | `def test_modal_create_exam_persists_custom_random_question_count(self):` |
| `apps/exams/tests/test_views.py` | 670 | `def test_modal_create_exam_can_disable_distribution_toggles(self):` |
| `apps/exams/tests/test_views.py` | 693 | `def test_create_exam_requires_active_organization(self):` |
| `apps/exams/tests/test_views.py` | 715 | `def test_create_exam_full_page_redirects_after_single_membership_org_restore(self):` |
| `apps/exams/tests/test_views.py` | 726 | `def test_org_admin_can_open_and_submit_create_exam_modal(self):` |
| `apps/exams/tests/test_views.py` | 757 | `def test_create_exam_redirects_to_org_selector_without_active_org_when_multiple_orgs(self):` |
| `apps/exams/tests/test_views.py` | 769 | `def test_superadmin_with_profile_org_can_create_exam_when_session_org_missing(self):` |
| `apps/exams/tests/test_views.py` | 806 | `def test_superadmin_without_profile_org_can_choose_organization_in_create_exam_modal(self):` |
| `apps/exams/tests/test_views.py` | 849 | `def test_modal_add_question_returns_partial_markup(self):` |
| `apps/exams/tests/test_views.py` | 864 | `def test_ru_question_add_translations_use_add_not_delete_or_topic(self):` |
| `apps/exams/tests/test_views.py` | 888 | `def test_modal_add_question_accepts_more_than_four_options(self):` |
| `apps/exams/tests/test_views.py` | 915 | `def test_modal_edit_question_updates_question_with_json_success(self):` |
| `apps/exams/tests/test_views.py` | 92 | `def _login_with_org(client, user, organization):` |
| `apps/exams/tests/test_views.py` | 940 | `def test_modal_edit_question_can_reduce_option_count_to_two(self):` |
| `apps/exams/tests/test_views.py` | 964 | `def test_modal_edit_question_rejects_multiple_correct_options_in_single_mode(self):` |
| `apps/exams/tests/test_views.py` | 989 | `def test_other_teacher_cannot_edit_or_delete_my_exam(self):` |
| `apps/exams/tests/test_views.py` | 99 | `class MyGroupsTenantIsolationTest(TestCase):` |
| `apps/exams/tests/test_wizard_enhancements.py` | 103 | `def test_provision_creates_unique_pin_per_student(self):` |
| `apps/exams/tests/test_wizard_enhancements.py` | 116 | `def test_provision_is_idempotent_and_prunes_removed(self):` |
| `apps/exams/tests/test_wizard_enhancements.py` | 131 | `def test_non_secure_exam_gets_no_pins(self):` |
| `apps/exams/tests/test_wizard_enhancements.py` | 136 | `def test_group_student_added_after_exam_assignment_gets_pin(self):` |
| `apps/exams/tests/test_wizard_enhancements.py` | 156 | `def test_excluded_group_student_loses_access_and_pin(self):` |
| `apps/exams/tests/test_wizard_enhancements.py` | 177 | `def test_user_lookup_returns_students_and_marks_group_members(self):` |
| `apps/exams/tests/test_wizard_enhancements.py` | 204 | `def test_grant_increases_attempts_left_for_single_student(self):` |
| `apps/exams/tests/test_wizard_enhancements.py` | 221 | `def test_create_modal_partial_renders_new_controls(self):` |
| `apps/exams/tests/test_wizard_enhancements.py` | 258 | `def test_trial_attempt_not_counted_against_limit(self):` |
| `apps/exams/tests/test_wizard_enhancements.py` | 29 | `class WizardEnhancementsTests(TestCase):` |
| `apps/exams/tests/test_wizard_enhancements.py` | 30 | `def setUp(self):` |
| `apps/exams/tests/test_wizard_enhancements.py` | 49 | `def test_midterm_requires_subject(self):` |
| `apps/exams/tests/test_wizard_enhancements.py` | 63 | `def test_midterm_with_subject_is_valid(self):` |
| `apps/exams/tests/test_wizard_enhancements.py` | 77 | `def test_quiz_does_not_require_subject(self):` |
| `apps/exams/tests/test_wizard_enhancements.py` | 91 | `def _make_secure_exam(self, category="midterm"):` |
| `apps/exams/validators.py` | 30 | `def validate_file_extension(file):` |
| `apps/exams/validators.py` | 40 | `def validate_file_size(file):` |
| `apps/exams/validators.py` | 47 | `def validate_zip_contents(file):` |
| `apps/exams/views/exam_center/_shared.py` | 16 | `def center_org_or_403(request):` |
| `apps/exams/views/exam_center/_shared.py` | 29 | `def supervisor_org_or_403(request):` |
| `apps/exams/views/exam_center/_shared.py` | 38 | `def get_center_session_or_404(request, session_id, *, for_supervision=False):` |
| `apps/exams/views/exam_center/_shared.py` | 57 | `def get_session_ticket_or_404(session, ticket_id):` |
| `apps/exams/views/exam_center/_shared.py` | 65 | `def get_center_ticket_or_404(request, ticket_id):` |
| `apps/exams/views/exam_center/_shared.py` | 77 | `def visible_sessions_qs(request, organization):` |
| `apps/exams/views/exam_center/_shared.py` | 83 | `def center_staff_queryset(organization):` |
| `apps/exams/views/exam_center/monitor.py` | 118 | `def exam_center_ticket_reentry(request, session_id, ticket_id):` |
| `apps/exams/views/exam_center/monitor.py` | 186 | `def exam_center_session_open_entry(request, session_id):` |
| `apps/exams/views/exam_center/monitor.py` | 201 | `def exam_center_session_start(request, session_id):` |
| `apps/exams/views/exam_center/monitor.py` | 233 | `def exam_center_session_end(request, session_id):` |
| `apps/exams/views/exam_center/monitor.py` | 252 | `def exam_center_session_cancel(request, session_id):` |
| `apps/exams/views/exam_center/monitor.py` | 266 | `def exam_center_ticket_remove(request, session_id, ticket_id):` |
| `apps/exams/views/exam_center/monitor.py` | 34 | `def exam_center_session_monitor(request, session_id):` |
| `apps/exams/views/exam_center/monitor.py` | 52 | `def exam_center_session_snapshot(request, session_id):` |
| `apps/exams/views/exam_center/monitor.py` | 59 | `def exam_center_ticket_snapshot(request, session_id, ticket_id):` |
| `apps/exams/views/exam_center/monitor.py` | 94 | `def exam_center_ticket_resume(request, session_id, ticket_id):` |
| `apps/exams/views/exam_center/pin_lookup.py` | 122 | `def exam_center_student_pins(request, student_id):` |
| `apps/exams/views/exam_center/pin_lookup.py` | 37 | `def exam_center_pin_lookup(request):` |
| `apps/exams/views/exam_center/pin_lookup.py` | 53 | `def _kafedra_subquery(organization):` |
| `apps/exams/views/exam_center/pin_lookup.py` | 65 | `def _pin_holder_student_queryset(organization):` |
| `apps/exams/views/exam_center/pin_lookup.py` | 82 | `def exam_center_pin_search(request):` |
| `apps/exams/views/exam_center/reports.py` | 20 | `def exam_center_reports(request):` |
| `apps/exams/views/exam_center/reports.py` | 58 | `def _export_csv(request, organization, tab, queryset):` |
| `apps/exams/views/exam_center/room_monitor.py` | 114 | `def _room_computer_grid(room, snapshot):` |
| `apps/exams/views/exam_center/room_monitor.py` | 135 | `def exam_center_room_monitor(request, room_id):` |
| `apps/exams/views/exam_center/room_monitor.py` | 167 | `def exam_center_room_assign_invigilators(request, room_id):` |
| `apps/exams/views/exam_center/room_monitor.py` | 208 | `def exam_center_room_snapshot(request, room_id):` |
| `apps/exams/views/exam_center/room_monitor.py` | 216 | `def exam_center_room_start_all(request, room_id):` |
| `apps/exams/views/exam_center/room_monitor.py` | 257 | `def exam_center_room_open_all(request, room_id):` |
| `apps/exams/views/exam_center/room_monitor.py` | 36 | `def _user_is_room_invigilator(user, room) -> bool:` |
| `apps/exams/views/exam_center/room_monitor.py` | 41 | `def _get_room_and_sessions(request, room_id):` |
| `apps/exams/views/exam_center/room_monitor.py` | 57 | `def _monitor_labels():` |
| `apps/exams/views/exam_center/rooms.py` | 24 | `def exam_center_room_list(request):` |
| `apps/exams/views/exam_center/sessions.py` | 111 | `def exam_center_session_detail(request, session_id):` |
| `apps/exams/views/exam_center/sessions.py` | 136 | `def exam_center_session_history(request, session_id):` |
| `apps/exams/views/exam_center/sessions.py` | 170 | `def exam_center_finals(request):` |
| `apps/exams/views/exam_center/sessions.py` | 209 | `def exam_center_assign_students(request):` |
| `apps/exams/views/exam_center/sessions.py` | 263 | `def exam_center_ticket_pin(request, ticket_id):` |
| `apps/exams/views/exam_center/sessions.py` | 297 | `def exam_center_ticket_seat(request, session_id, ticket_id):` |
| `apps/exams/views/exam_center/sessions.py` | 313 | `def exam_center_ticket_readmit(request, session_id, ticket_id):` |
| `apps/exams/views/exam_center/sessions.py` | 44 | `def exam_center_session_list(request):` |
| `apps/exams/views/exam_center/sessions.py` | 70 | `def exam_center_session_create(request):` |
| `apps/exams/views/exam_center/statistics.py` | 101 | `def _sorted(qs, request):` |
| `apps/exams/views/exam_center/statistics.py` | 113 | `def _dedup(names):` |
| `apps/exams/views/exam_center/statistics.py` | 122 | `def _row(attempt):` |
| `apps/exams/views/exam_center/statistics.py` | 151 | `def exam_center_stats_data(request):` |
| `apps/exams/views/exam_center/statistics.py` | 188 | `def exam_center_stats_export(request):` |
| `apps/exams/views/exam_center/statistics.py` | 239 | `def exam_center_stats_filters(request):` |
| `apps/exams/views/exam_center/statistics.py` | 43 | `def _stats_org(request):` |
| `apps/exams/views/exam_center/statistics.py` | 50 | `def _csv_ints(raw):` |
| `apps/exams/views/exam_center/statistics.py` | 54 | `def _unit_ids_with_children(organization, unit_ids):` |
| `apps/exams/views/exam_center/statistics.py` | 64 | `def _filtered_attempts(request, organization):` |
| `apps/exams/views/exam_center/statistics_charts.py` | 114 | `def _chart_payload(qs):` |
| `apps/exams/views/exam_center/statistics_charts.py` | 134 | `def exam_center_stats_charts(request):` |
| `apps/exams/views/exam_center/statistics_charts.py` | 143 | `def exam_center_stats_ai(request):` |
| `apps/exams/views/exam_center/statistics_charts.py` | 34 | `def _scored(qs):` |
| `apps/exams/views/exam_center/statistics_charts.py` | 39 | `def _rnd(value):` |
| `apps/exams/views/exam_center/statistics_charts.py` | 43 | `def _distribution(scored):` |
| `apps/exams/views/exam_center/statistics_charts.py` | 59 | `def _monthly(qs, limit=24):` |
| `apps/exams/views/exam_center/statistics_charts.py` | 77 | `def _by_type(qs):` |
| `apps/exams/views/exam_center/statistics_charts.py` | 96 | `def _by_subject(qs, limit=10):` |
| `apps/exams/views/shared/access.py` | 16 | `def _safe_same_origin_redirect_path(request, candidate_url):` |
| `apps/exams/views/shared/access.py` | 30 | `def _resolve_exam_failure_redirect(request):` |
| `apps/exams/views/shared/access.py` | 46 | `def _is_ajax_request(request):` |
| `apps/exams/views/shared/access.py` | 50 | `def _json_redirect_response(response):` |
| `apps/exams/views/shared/access.py` | 57 | `def exam_code_check(request):` |
| `apps/exams/views/shared/tenant.py` | 13 | `def get_active_organization(request):` |
| `apps/exams/views/shared/tenant.py` | 17 | `def tenant_scoped_exams(request, queryset=None, *, include_deleted=False):` |
| `apps/exams/views/shared/tenant.py` | 33 | `def ensure_teacher_exam_tenant_context(request):` |
| `apps/exams/views/shared/tenant.py` | 52 | `def get_teacher_exam_or_404(request, *, include_deleted=False, **filters):` |
| `apps/exams/views/shared/tenant.py` | 60 | `def get_result_viewable_exam_or_404(request, *, include_deleted=False, **filters):` |
| `apps/exams/views/shared/tenant.py` | 79 | `def exam_in_active_tenant(request, exam):` |
| `apps/exams/views/student/_helpers.py` | 18 | `def ensure_student_exam_tenant_context(request):` |
| `apps/exams/views/student/_helpers.py` | 24 | `def are_exam_results_hidden_from_student(exam):` |
| `apps/exams/views/student/_helpers.py` | 28 | `def annotate_attempt_result_visibility(attempts, *, current_time=None):` |
| `apps/exams/views/student/attempts.py` | 110 | `def _valid_question_option_ids(question):` |
| `apps/exams/views/student/attempts.py` | 114 | `def _correct_question_option_ids(question):` |
| `apps/exams/views/student/attempts.py` | 118 | `def _save_test_answer_if_changed(answer, question, selected_option_ids, current_selected_option_ids):` |
| `apps/exams/views/student/attempts.py` | 149 | `def _save_written_answer_if_changed(request, answer, question, *, allow_binary_uploads=True):` |
| `apps/exams/views/student/attempts.py` | 209 | `def _marked_question_ids_from_request(request, valid_question_ids):` |
| `apps/exams/views/student/attempts.py` | 237 | `def _save_marked_question_ids_from_request(request, attempt):` |
| `apps/exams/views/student/attempts.py` | 249 | `def _previous_attempts_for_context(request, exam, attempt):` |
| `apps/exams/views/student/attempts.py` | 270 | `def _resolve_exam_failure_redirect(request):` |
| `apps/exams/views/student/attempts.py` | 287 | `def start_exam(request, slug):` |
| `apps/exams/views/student/attempts.py` | 316 | `def _handle_take_exam_post(request, *, attempt, return_to, is_time_up):` |
| `apps/exams/views/student/attempts.py` | 41 | `def _attempt_answers_queryset(attempt, *, question_ids=None):` |
| `apps/exams/views/student/attempts.py` | 436 | `def take_exam(request, slug, attempt_id):` |
| `apps/exams/views/student/attempts.py` | 59 | `def _is_ajax_request(request):` |
| `apps/exams/views/student/attempts.py` | 63 | `def _finished_attempt_response(request, attempt, *, return_to):` |
| `apps/exams/views/student/attempts.py` | 77 | `def _posted_autosave_question_ids(request, *, action):` |
| `apps/exams/views/student/attempts.py` | 91 | `def _selected_option_ids_from_request(request, question):` |
| `apps/exams/views/student/coding.py` | 102 | `def _submission_payload(submission):` |
| `apps/exams/views/student/coding.py` | 118 | `def _safe_archive_name(name, used_names):` |
| `apps/exams/views/student/coding.py` | 131 | `def _submission_file_items(submission):` |
| `apps/exams/views/student/coding.py` | 151 | `def _get_submission_download_attempt(request, slug, attempt_id):` |
| `apps/exams/views/student/coding.py` | 172 | `def _serialize_visible_test_cases(coding_question):` |
| `apps/exams/views/student/coding.py` | 184 | `def _latest_draft_submissions_by_question(*, student, exam, attempt, coding_questions):` |
| `apps/exams/views/student/coding.py` | 199 | `def _serialize_coding_question(coding_question, *, index, latest_submission):` |
| `apps/exams/views/student/coding.py` | 225 | `def take_coding_exam(request, *, exam, attempt, remaining_seconds, history_url, previous_attempts, supervision):` |
| `apps/exams/views/student/coding.py` | 276 | `def coding_submission_download(request, slug, attempt_id, submission_id):` |
| `apps/exams/views/student/coding.py` | 304 | `def _build_submission_input(request, attempt):` |
| `apps/exams/views/student/coding.py` | 329 | `def _build_submission_items(request, attempt):` |
| `apps/exams/views/student/coding.py` | 377 | `def coding_autosave(request, slug, attempt_id):` |
| `apps/exams/views/student/coding.py` | 37 | `def _json_error(message, *, status=400, extra=None):` |
| `apps/exams/views/student/coding.py` | 409 | `def coding_run(request, slug, attempt_id):` |
| `apps/exams/views/student/coding.py` | 44 | `def _coding_disabled_error():` |
| `apps/exams/views/student/coding.py` | 487 | `def coding_submit(request, slug, attempt_id):` |
| `apps/exams/views/student/coding.py` | 48 | `def _parse_json_body(request):` |
| `apps/exams/views/student/coding.py` | 55 | `def _get_coding_attempt(request, slug, attempt_id):` |
| `apps/exams/views/student/coding.py` | 69 | `def _get_attempt_coding_questions(attempt):` |
| `apps/exams/views/student/coding.py` | 83 | `def _get_attempt_coding_question(attempt, coding_question_id=None):` |
| `apps/exams/views/student/final_center.py` | 106 | `def _render_login(request, *, error="", username="", modal_ticket=None, modal_error=""):` |
| `apps/exams/views/student/final_center.py` | 132 | `def _route_validated_ticket(request, ticket):` |
| `apps/exams/views/student/final_center.py` | 164 | `def _validated_session_ticket(request):` |
| `apps/exams/views/student/final_center.py` | 177 | `def final_exam_entry(request):` |
| `apps/exams/views/student/final_center.py` | 212 | `def _handle_login(request):` |
| `apps/exams/views/student/final_center.py` | 254 | `def _handle_student_pin_login(request, username, raw_pin):` |
| `apps/exams/views/student/final_center.py` | 351 | `def _handle_confirm(request):` |
| `apps/exams/views/student/final_center.py` | 379 | `def _resolve_own_ticket(request, ticket_id):` |
| `apps/exams/views/student/final_center.py` | 395 | `def final_exam_waiting(request, ticket_id):` |
| `apps/exams/views/student/final_center.py` | 436 | `def final_exam_cancel(request, ticket_id):` |
| `apps/exams/views/student/final_center.py` | 450 | `def final_exam_begin(request, ticket_id):` |
| `apps/exams/views/student/final_center.py` | 480 | `def final_ticket_state(request, ticket_id):` |
| `apps/exams/views/student/final_center.py` | 76 | `def _ensure_hall_access(request):` |
| `apps/exams/views/student/final_center.py` | 82 | `def _room_access_ok(request, room) -> bool:` |
| `apps/exams/views/student/final_center.py` | 87 | `def _room_access_error():` |
| `apps/exams/views/student/final_center.py` | 94 | `def _entry_error_message(code):` |
| `apps/exams/views/student/lists.py` | 107 | `def _normalize_sort(raw_sort):` |
| `apps/exams/views/student/lists.py` | 112 | `def _apply_sort(queryset, sort):` |
| `apps/exams/views/student/lists.py` | 127 | `def _build_type_counts(base_qs):` |
| `apps/exams/views/student/lists.py` | 151 | `def _live_session_map(exam_ids):` |
| `apps/exams/views/student/lists.py` | 178 | `def _display_type(exam, is_live):` |
| `apps/exams/views/student/lists.py` | 191 | `def _type_label(key):` |
| `apps/exams/views/student/lists.py` | 208 | `def _build_type_tabs(counts, *, include_final_midterm=True):` |
| `apps/exams/views/student/lists.py` | 219 | `def add(key, count_key, *, always=False):` |
| `apps/exams/views/student/lists.py` | 237 | `def _build_language_modal_context(exam):` |
| `apps/exams/views/student/lists.py` | 259 | `def _annotate_exam_list_base(queryset, user):` |
| `apps/exams/views/student/lists.py` | 275 | `def _build_exam_items(page_object_list, user, request, live_map):` |
| `apps/exams/views/student/lists.py` | 328 | `def _render_exam_list(` |
| `apps/exams/views/student/lists.py` | 408 | `def assigned_student_exam_list(request):` |
| `apps/exams/views/student/lists.py` | 438 | `def student_exam_list(request):` |
| `apps/exams/views/student/lists.py` | 50 | `def _user_finished_attempt_count_sq(user):` |
| `apps/exams/views/student/lists.py` | 64 | `def _live_session_exists_sq():` |
| `apps/exams/views/student/lists.py` | 69 | `def _exclude_attempt_exhausted(queryset):` |
| `apps/exams/views/student/lists.py` | 84 | `def _exclude_expired_exams(queryset):` |
| `apps/exams/views/student/lists.py` | 90 | `def _apply_exam_type_filter(queryset, filter_type):` |
| `apps/exams/views/student/results.py` | 107 | `def _resolve_result_navigation(request, exam, return_to):` |
| `apps/exams/views/student/results.py` | 123 | `def exam_result(request, slug, attempt_id):` |
| `apps/exams/views/student/results.py` | 327 | `def student_exam_history(request):` |
| `apps/exams/views/student/results.py` | 35 | `def _is_final_exam(exam):` |
| `apps/exams/views/student/results.py` | 39 | `def _is_profile_results_request(request, return_to):` |
| `apps/exams/views/student/results.py` | 46 | `def _hide_test_answer_correctness_in_cabinet(exam, *, is_profile_results):` |
| `apps/exams/views/student/results.py` | 54 | `def _final_entry_url():` |
| `apps/exams/views/student/results.py` | 58 | `def _final_result_timeout_url(request):` |
| `apps/exams/views/student/results.py` | 63 | `def _final_result_remaining_seconds(attempt):` |
| `apps/exams/views/student/results.py` | 71 | `def _format_score_delta(value):` |
| `apps/exams/views/student/results.py` | 81 | `def _default_exam_back_url(exam):` |
| `apps/exams/views/student/results.py` | 87 | `def _coding_submission_file_items(submission):` |
| `apps/exams/views/student/script_data 2.py` | 6 | `def take_exam_script_data(remaining_seconds):` |
| `apps/exams/views/student/script_data.py` | 6 | `def take_exam_script_data(remaining_seconds):` |
| `apps/exams/views/teacher/exams/_shared.py` | 107 | `def _is_superadmin(user):` |
| `apps/exams/views/teacher/exams/_shared.py` | 111 | `def _ensure_exam_permission(request, permission):` |
| `apps/exams/views/teacher/exams/_shared.py` | 119 | `def _organization_selection_redirect(request):` |
| `apps/exams/views/teacher/exams/_shared.py` | 123 | `def _restore_superadmin_profile_organization(request):` |
| `apps/exams/views/teacher/exams/_shared.py` | 129 | `def _organization_selection_queryset():` |
| `apps/exams/views/teacher/exams/_shared.py` | 133 | `def _exam_detail_question_queryset(exam):` |
| `apps/exams/views/teacher/exams/_shared.py` | 137 | `def _positive_int(value, *, default, maximum=None):` |
| `apps/exams/views/teacher/exams/_shared.py` | 149 | `def _get_exam_detail_question_page(exam, *, offset=0, limit=DETAIL_QUESTION_PAGE_SIZE):` |
| `apps/exams/views/teacher/exams/_shared.py` | 163 | `def _resolve_selected_superadmin_organization(request):` |
| `apps/exams/views/teacher/exams/_shared.py` | 171 | `def _bind_selected_organization(request, organization):` |
| `apps/exams/views/teacher/exams/_shared.py` | 185 | `def _resolve_required_organization(request):` |
| `apps/exams/views/teacher/exams/_shared.py` | 204 | `def _get_editable_exam_or_404(request, slug):` |
| `apps/exams/views/teacher/exams/_shared.py` | 215 | `def _get_deleted_exam_or_404(request, slug):` |
| `apps/exams/views/teacher/exams/_shared.py` | 232 | `def _selected_access_entities(form):` |
| `apps/exams/views/teacher/exams/_shared.py` | 26 | `def _teacher_profile_my_exams_url():` |
| `apps/exams/views/teacher/exams/_shared.py` | 270 | `def _build_group_student_map(form):` |
| `apps/exams/views/teacher/exams/_shared.py` | 291 | `def _get_requested_course_for_exam(request):` |
| `apps/exams/views/teacher/exams/_shared.py` | 30 | `def _safe_same_origin_redirect_path(request, candidate_url):` |
| `apps/exams/views/teacher/exams/_shared.py` | 52 | `def _is_internal_exam_management_path(candidate_path):` |
| `apps/exams/views/teacher/exams/_shared.py` | 75 | `def _resolve_profile_navigation(request, *, default_section="my-exams"):` |
| `apps/exams/views/teacher/exams/actions.py` | 150 | `def toggle_exam_archive(request, slug):` |
| `apps/exams/views/teacher/exams/actions.py` | 210 | `def duplicate_exam(request, slug):` |
| `apps/exams/views/teacher/exams/actions.py` | 243 | `def deleted_exams_list(request):` |
| `apps/exams/views/teacher/exams/actions.py` | 278 | `def restore_exam(request, slug):` |
| `apps/exams/views/teacher/exams/actions.py` | 29 | `def toggle_exam_active(request, slug):` |
| `apps/exams/views/teacher/exams/actions.py` | 325 | `def permanent_delete_exam(request, slug):` |
| `apps/exams/views/teacher/exams/actions.py` | 58 | `def toggle_exam_results_visibility(request, slug):` |
| `apps/exams/views/teacher/exams/actions.py` | 88 | `def delete_exam(request, slug):` |
| `apps/exams/views/teacher/exams/attempt_grants.py` | 25 | `def _is_ajax(request):` |
| `apps/exams/views/teacher/exams/attempt_grants.py` | 31 | `def grant_extra_attempt(request, slug):` |
| `apps/exams/views/teacher/exams/attempt_grants.py` | 44 | `def _fail(error, status):` |
| `apps/exams/views/teacher/exams/attempt_grants.py` | 50 | `def _back_url():` |
| `apps/exams/views/teacher/exams/list_detail.py` | 268 | `def teacher_exam_detail(request, slug):` |
| `apps/exams/views/teacher/exams/list_detail.py` | 321 | `def teacher_exam_detail_questions_page(request, slug):` |
| `apps/exams/views/teacher/exams/list_detail.py` | 42 | `def teacher_exam_list(request):` |
| `apps/exams/views/teacher/exams/list_detail.py` | 51 | `def createAndEditExamView(request, slug=None):` |
| `apps/exams/views/teacher/exams/lookups.py` | 108 | `def user_search(request):` |
| `apps/exams/views/teacher/exams/lookups.py` | 165 | `def invigilator_search(request):` |
| `apps/exams/views/teacher/exams/lookups.py` | 221 | `def assigned_student_count(request):` |
| `apps/exams/views/teacher/exams/lookups.py` | 252 | `def exam_available_question_count(request, slug):` |
| `apps/exams/views/teacher/exams/lookups.py` | 28 | `def _page_bounds(request):` |
| `apps/exams/views/teacher/exams/lookups.py` | 46 | `def _paginate(qs, offset, limit, serializer):` |
| `apps/exams/views/teacher/exams/lookups.py` | 54 | `def subject_search(request):` |
| `apps/exams/views/teacher/exams/lookups.py` | 74 | `def _org_user_queryset(request, organization):` |
| `apps/exams/views/teacher/exams/lookups.py` | 88 | `def group_search(request):` |
| `apps/exams/views/teacher/extract_jobs.py` | 129 | `def start_text_extraction(request):` |
| `apps/exams/views/teacher/extract_jobs.py` | 184 | `def text_extraction_status(request, job_id):` |
| `apps/exams/views/teacher/extract_jobs.py` | 191 | `def start_export_job(request, *, export_name, params):` |
| `apps/exams/views/teacher/extract_jobs.py` | 229 | `def _serve_export_file(job):` |
| `apps/exams/views/teacher/extract_jobs.py` | 247 | `def export_job_waiting(request, job_id):` |
| `apps/exams/views/teacher/extract_jobs.py` | 267 | `def export_job_download(request, job_id):` |
| `apps/exams/views/teacher/extract_jobs.py` | 28 | `def _job_payload(job):` |
| `apps/exams/views/teacher/extract_jobs.py` | 39 | `def _ensure_job_progress(job, runner):` |
| `apps/exams/views/teacher/extract_jobs.py` | 74 | `def start_ai_generation_job(request, *, payload, uploaded, service_error_message):` |
| `apps/exams/views/teacher/groups.py` | 118 | `def _group_form_for_request(request, organization, data=None, instance=None):` |
| `apps/exams/views/teacher/groups.py` | 129 | `def _create_group_template_context(request, organization, form):` |
| `apps/exams/views/teacher/groups.py` | 142 | `def teacher_group_list(request):` |
| `apps/exams/views/teacher/groups.py` | 163 | `def teacher_create_group(request):` |
| `apps/exams/views/teacher/groups.py` | 19 | `def _is_superadmin(user):` |
| `apps/exams/views/teacher/groups.py` | 212 | `def teacher_update_group(request, group_id):` |
| `apps/exams/views/teacher/groups.py` | 23 | `def _ensure_group_manager(user):` |
| `apps/exams/views/teacher/groups.py` | 272 | `def teacher_delete_group(request, group_id):` |
| `apps/exams/views/teacher/groups.py` | 301 | `def teacher_remove_student_from_group(request, group_id, student_id):` |
| `apps/exams/views/teacher/groups.py` | 332 | `def teacher_add_student_to_group(request, group_id, student_id):` |
| `apps/exams/views/teacher/groups.py` | 370 | `def create_student_group(request):` |
| `apps/exams/views/teacher/groups.py` | 41 | `def _user_can_create_group(request):` |
| `apps/exams/views/teacher/groups.py` | 58 | `def _ensure_group_creator(request):` |
| `apps/exams/views/teacher/groups.py` | 64 | `def _can_multi_assign_teachers(user):` |
| `apps/exams/views/teacher/groups.py` | 72 | `def _resolve_next_url(request):` |
| `apps/exams/views/teacher/groups.py` | 85 | `def _get_required_organization(request):` |
| `apps/exams/views/teacher/groups.py` | 97 | `def _group_queryset_for_actor(request, organization):` |
| `apps/exams/views/teacher/languages.py` | 36 | `def _manager_url(exam):` |
| `apps/exams/views/teacher/languages.py` | 40 | `def _build_variant_rows(exam):` |
| `apps/exams/views/teacher/languages.py` | 53 | `def _empty_analysis():` |
| `apps/exams/views/teacher/languages.py` | 64 | `def _variant_language_options(variant_rows):` |
| `apps/exams/views/teacher/languages.py` | 69 | `def _language_workbench_context(exam, variant_rows, selected_language):` |
| `apps/exams/views/teacher/languages.py` | 88 | `def exam_language_manager(request, slug):` |
| `apps/exams/views/teacher/question_bank/_helpers 2.py` | 106 | `def _default_exam_language(exam):` |
| `apps/exams/views/teacher/question_bank/_helpers 2.py` | 119 | `def _normalize_exam_language(value, exam):` |
| `apps/exams/views/teacher/question_bank/_helpers 2.py` | 127 | `def _test_workbench_context(exam, navigation_query, *, selected_language=None):` |
| `apps/exams/views/teacher/question_bank/_helpers 2.py` | 171 | `def _parse_written_questions(content_text):` |
| `apps/exams/views/teacher/question_bank/_helpers 2.py` | 191 | `def _question_bank_title_context(exam):` |
| `apps/exams/views/teacher/question_bank/_helpers 2.py` | 204 | `def _optional_non_negative_int(value):` |
| `apps/exams/views/teacher/question_bank/_helpers 2.py` | 215 | `def _parse_selected_question_indices(post_data):` |
| `apps/exams/views/teacher/question_bank/_helpers 2.py` | 219 | `def _parse_points_payload(post_data):` |
| `apps/exams/views/teacher/question_bank/_helpers 2.py` | 223 | `def _sync_written_block_questions(block, question_texts, *, language=None, language_variant=None):` |
| `apps/exams/views/teacher/question_bank/_helpers 2.py` | 23 | `def _safe_same_origin_redirect_path(request, candidate_url):` |
| `apps/exams/views/teacher/question_bank/_helpers 2.py` | 322 | `def _question_bank_warning_label(warning_type):` |
| `apps/exams/views/teacher/question_bank/_helpers 2.py` | 326 | `def _question_bank_feedback(warning_type):` |
| `apps/exams/views/teacher/question_bank/_helpers 2.py` | 333 | `def _split_end_question_source_blocks(raw_text):` |
| `apps/exams/views/teacher/question_bank/_helpers 2.py` | 352 | `def _question_bank_source_diagnostics(raw_text, parsed):` |
| `apps/exams/views/teacher/question_bank/_helpers 2.py` | 396 | `def _format_int_list(values, limit=40):` |
| `apps/exams/views/teacher/question_bank/_helpers 2.py` | 406 | `def _warning_reference_text(warning):` |
| `apps/exams/views/teacher/question_bank/_helpers 2.py` | 45 | `def _is_internal_exam_management_path(candidate_path):` |
| `apps/exams/views/teacher/question_bank/_helpers 2.py` | 68 | `def _resolve_question_bank_navigation(request):` |
| `apps/exams/views/teacher/question_bank/_helpers 2.py` | 99 | `def _append_navigation_query(path, navigation_query):` |
| `apps/exams/views/teacher/question_bank/_helpers.py` | 106 | `def _default_exam_language(exam):` |
| `apps/exams/views/teacher/question_bank/_helpers.py` | 119 | `def _normalize_exam_language(value, exam):` |
| `apps/exams/views/teacher/question_bank/_helpers.py` | 127 | `def _test_workbench_context(exam, navigation_query, *, selected_language=None):` |
| `apps/exams/views/teacher/question_bank/_helpers.py` | 171 | `def _parse_written_questions(content_text):` |
| `apps/exams/views/teacher/question_bank/_helpers.py` | 191 | `def _question_bank_title_context(exam):` |
| `apps/exams/views/teacher/question_bank/_helpers.py` | 204 | `def _optional_non_negative_int(value):` |
| `apps/exams/views/teacher/question_bank/_helpers.py` | 215 | `def _parse_selected_question_indices(post_data):` |
| `apps/exams/views/teacher/question_bank/_helpers.py` | 219 | `def _parse_points_payload(post_data):` |
| `apps/exams/views/teacher/question_bank/_helpers.py` | 223 | `def _sync_written_block_questions(block, question_texts, *, language=None, language_variant=None):` |
| `apps/exams/views/teacher/question_bank/_helpers.py` | 23 | `def _safe_same_origin_redirect_path(request, candidate_url):` |
| `apps/exams/views/teacher/question_bank/_helpers.py` | 322 | `def _question_bank_warning_label(warning_type):` |
| `apps/exams/views/teacher/question_bank/_helpers.py` | 326 | `def _question_bank_feedback(warning_type):` |
| `apps/exams/views/teacher/question_bank/_helpers.py` | 333 | `def _split_end_question_source_blocks(raw_text):` |
| `apps/exams/views/teacher/question_bank/_helpers.py` | 352 | `def _question_bank_source_diagnostics(raw_text, parsed):` |
| `apps/exams/views/teacher/question_bank/_helpers.py` | 396 | `def _format_int_list(values, limit=40):` |
| `apps/exams/views/teacher/question_bank/_helpers.py` | 406 | `def _warning_reference_text(warning):` |
| `apps/exams/views/teacher/question_bank/_helpers.py` | 45 | `def _is_internal_exam_management_path(candidate_path):` |
| `apps/exams/views/teacher/question_bank/_helpers.py` | 68 | `def _resolve_question_bank_navigation(request):` |
| `apps/exams/views/teacher/question_bank/_helpers.py` | 99 | `def _append_navigation_query(path, navigation_query):` |
| `apps/exams/views/teacher/question_bank/_reports.py` | 21 | `def _tx(message):` |
| `apps/exams/views/teacher/question_bank/_reports.py` | 258 | `def _build_question_bank_report_docx(` |
| `apps/exams/views/teacher/question_bank/_reports.py` | 25 | `def _excel_sheet_title(message):` |
| `apps/exams/views/teacher/question_bank/_reports.py` | 32 | `def _build_question_bank_report_xlsx(` |
| `apps/exams/views/teacher/question_bank/_views_create.py` | 120 | `def process_question_bank(request, slug):` |
| `apps/exams/views/teacher/question_bank/_views_create.py` | 32 | `def ai_generate_question_bank(request, slug):` |
| `apps/exams/views/teacher/question_bank/_views_create.py` | 77 | `def create_question_bank(request, slug):` |
| `apps/exams/views/teacher/question_bank/_views_misc.py` | 35 | `def test_question_bank_template_download(request, slug):` |
| `apps/exams/views/teacher/question_bank/_views_misc.py` | 52 | `def exam_questions_word_export(request, slug):` |
| `apps/exams/views/teacher/question_bank/_views_misc.py` | 94 | `def test_question_bank(request, slug):` |
| `apps/exams/views/teacher/question_library/_shared.py` | 167 | `def _render_bank_question_form_html(request, *, bank, form, editing=False, question=None):` |
| `apps/exams/views/teacher/question_library/_shared.py` | 175 | `def _exam_compatible_question_type(exam):` |
| `apps/exams/views/teacher/question_library/_shared.py` | 180 | `def _first_or_default_block(exam):` |
| `apps/exams/views/teacher/question_library/_shared.py` | 196 | `def _bank_language_stats(bank, *, question_type=None):` |
| `apps/exams/views/teacher/question_library/_shared.py` | 67 | `def _normalize_format(value):` |
| `apps/exams/views/teacher/question_library/_shared.py` | 72 | `def _is_modal_request(request):` |
| `apps/exams/views/teacher/question_library/_shared.py` | 80 | `def _empty_analysis():` |
| `apps/exams/views/teacher/question_library/_shared.py` | 91 | `def _save_bank_questions(*, bank, parsed, selected, language, q_format, points_payload, created_by, math_token=""):` |
| `apps/exams/views/teacher/question_library/crud.py` | 116 | `def question_bank_detail(request, bank_id):` |
| `apps/exams/views/teacher/question_library/crud.py` | 28 | `def question_bank_list(request):` |
| `apps/exams/views/teacher/question_library/crud.py` | 63 | `def question_bank_update(request, bank_id):` |
| `apps/exams/views/teacher/question_library/crud.py` | 95 | `def question_bank_delete(request, bank_id):` |
| `apps/exams/views/teacher/question_library/export.py` | 21 | `def question_bank_template_download(request, bank_id):` |
| `apps/exams/views/teacher/question_library/export.py` | 36 | `def question_bank_word_export(request, bank_id):` |
| `apps/exams/views/teacher/question_library/picker.py` | 31 | `def exam_bank_picker(request, slug):` |
| `apps/exams/views/teacher/question_library/questions.py` | 148 | `def ai_generate_bank_questions(request, bank_id):` |
| `apps/exams/views/teacher/question_library/questions.py` | 182 | `def bank_question_add(request, bank_id):` |
| `apps/exams/views/teacher/question_library/questions.py` | 228 | `def bank_question_edit(request, bank_id, question_id):` |
| `apps/exams/views/teacher/question_library/questions.py` | 36 | `def question_bank_bulk_add(request, bank_id):` |
| `apps/exams/views/teacher/questions/_shared.py` | 100 | `def _resequence_exam_questions(exam):` |
| `apps/exams/views/teacher/questions/_shared.py` | 113 | `def _question_form_blocks(exam):` |
| `apps/exams/views/teacher/questions/_shared.py` | 127 | `def _question_post_data_with_default_block(request, created_default_block):` |
| `apps/exams/views/teacher/questions/_shared.py` | 136 | `def _render_question_form_html(request, *, exam, form, editing=False, question=None, navigation_query=""):` |
| `apps/exams/views/teacher/questions/_shared.py` | 13 | `def _is_question_modal_request(request):` |
| `apps/exams/views/teacher/questions/_shared.py` | 17 | `def _safe_same_origin_redirect_path(request, candidate_url):` |
| `apps/exams/views/teacher/questions/_shared.py` | 39 | `def _is_internal_exam_management_path(candidate_path):` |
| `apps/exams/views/teacher/questions/_shared.py` | 62 | `def _resolve_question_bank_navigation(request):` |
| `apps/exams/views/teacher/questions/_shared.py` | 93 | `def _append_navigation_query(path, navigation_query):` |
| `apps/exams/views/teacher/questions/bank.py` | 33 | `def teacher_questions_bank(request, slug):` |
| `apps/exams/views/teacher/questions/crud.py` | 160 | `def edit_exam_question(request, slug, question_id):` |
| `apps/exams/views/teacher/questions/crud.py` | 273 | `def delete_exam_question(request, slug, question_id):` |
| `apps/exams/views/teacher/questions/crud.py` | 32 | `def add_exam_question(request, slug):` |
| `apps/exams/views/teacher/results/_attempt_views.py` | 195 | `def teacher_check_attempt(request, slug, attempt_id):` |
| `apps/exams/views/teacher/results/_attempt_views.py` | 344 | `def ai_grade_answer(request, slug, attempt_id):` |
| `apps/exams/views/teacher/results/_attempt_views.py` | 390 | `def teacher_pending_attempts(request):` |
| `apps/exams/views/teacher/results/_attempt_views.py` | 44 | `def delete_exam_attempts(request, slug):` |
| `apps/exams/views/teacher/results/_attempt_views.py` | 90 | `def teacher_view_attempt(request, slug, attempt_id):` |
| `apps/exams/views/teacher/results/_export_builder.py` | 28 | `def build_exam_results_xlsx_export(exam, attempts_list):` |
| `apps/exams/views/teacher/results/_helpers.py` | 121 | `def _append_query_params(url, **params):` |
| `apps/exams/views/teacher/results/_helpers.py` | 129 | `def _safe_same_origin_redirect_path(request, candidate_url):` |
| `apps/exams/views/teacher/results/_helpers.py` | 151 | `def _resolve_profile_navigation(request, *, default_section="my-exams"):` |
| `apps/exams/views/teacher/results/_helpers.py` | 180 | `def _build_attempt_timing_context(attempt):` |
| `apps/exams/views/teacher/results/_helpers.py` | 199 | `def _parse_filter_date(raw_value):` |
| `apps/exams/views/teacher/results/_helpers.py` | 209 | `def _resolve_attempt_action_state(attempt, *, can_view_name, review_window_seconds, identity_window_seconds):` |
| `apps/exams/views/teacher/results/_helpers.py` | 22 | `def _user_display_name(user):` |
| `apps/exams/views/teacher/results/_helpers.py` | 245 | `def _build_anonymous_name(*, attempt_id: int, user_id: int, exam_id: int) -> str:` |
| `apps/exams/views/teacher/results/_helpers.py` | 255 | `def _available_groups_for_exam(exam):` |
| `apps/exams/views/teacher/results/_helpers.py` | 26 | `def _coding_submission_file_items(submission):` |
| `apps/exams/views/teacher/results/_helpers.py` | 272 | `def _attempt_time_limit_seconds(attempt):` |
| `apps/exams/views/teacher/results/_helpers.py` | 280 | `def _attempt_effective_finish(attempt, *, now=None):` |
| `apps/exams/views/teacher/results/_helpers.py` | 306 | `def _attempt_effective_duration(attempt, effective_finish):` |
| `apps/exams/views/teacher/results/_helpers.py` | 318 | `def _appeal_bonus_map_for(attempts):` |
| `apps/exams/views/teacher/results/_helpers.py` | 325 | `def _apply_appeal_bonus(test_result, bonus):` |
| `apps/exams/views/teacher/results/_helpers.py` | 332 | `def _expire_overdue_attempts(exam, *, now=None):` |
| `apps/exams/views/teacher/results/_helpers.py` | 355 | `def _apply_results_filters(exam, request):` |
| `apps/exams/views/teacher/results/_helpers.py` | 363 | `def _apply_results_filters_from_params(exam, params):` |
| `apps/exams/views/teacher/results/_helpers.py` | 52 | `def _sync_coding_answers_from_final_submissions(attempt):` |
| `apps/exams/views/teacher/results/_helpers.py` | 78 | `def _build_answer_review_item(answer):` |
| `apps/exams/views/teacher/results/_results_views.py` | 342 | `def export_exam_results_xlsx(request, slug):` |
| `apps/exams/views/teacher/results/_results_views.py` | 42 | `def teacher_exam_results(request, slug):` |
| `apps/exams/views/teacher/statistics.py` | 159 | `def _attempt_score(a):` |
| `apps/exams/views/teacher/statistics.py` | 168 | `def _attempt_raw_score(a):` |
| `apps/exams/views/teacher/statistics.py` | 28 | `def _parse_int(raw, default=None):` |
| `apps/exams/views/teacher/statistics.py` | 35 | `def _build_score_distribution(scores, bucket_limit=6):` |
| `apps/exams/views/teacher/statistics.py` | 58 | `def _resolve_navigation(request, exam, *, default_section="my-exams"):` |
| `apps/exams/views/teacher/statistics.py` | 83 | `def teacher_exam_statistics(request, slug):` |
| `apps/exams/views/teacher/submission_inbox.py` | 101 | `def _resolve_groups(form_state, groups):` |
| `apps/exams/views/teacher/submission_inbox.py` | 111 | `def annotate_preview_flags(questions):` |
| `apps/exams/views/teacher/submission_inbox.py` | 120 | `def _preview_context(raw_text):` |
| `apps/exams/views/teacher/submission_inbox.py` | 130 | `def question_submission_create(request):` |
| `apps/exams/views/teacher/submission_inbox.py` | 294 | `def ai_generate_submission_questions(request):` |
| `apps/exams/views/teacher/submission_inbox.py` | 326 | `def question_submission_detail(request, submission_id):` |
| `apps/exams/views/teacher/submission_inbox.py` | 37 | `def _profile_section_url(section):` |
| `apps/exams/views/teacher/submission_inbox.py` | 416 | `def question_submission_delete(request, submission_id):` |
| `apps/exams/views/teacher/submission_inbox.py` | 41 | `def _require_organization(request):` |
| `apps/exams/views/teacher/submission_inbox.py` | 441 | `def _detail_context(submission, *, can_edit, is_reviewer):` |
| `apps/exams/views/teacher/submission_inbox.py` | 469 | `def question_submission_inbox(request):` |
| `apps/exams/views/teacher/submission_inbox.py` | 502 | `def question_submission_review(request, submission_id):` |
| `apps/exams/views/teacher/submission_inbox.py` | 50 | `def _normalize_language(raw_value):` |
| `apps/exams/views/teacher/submission_inbox.py` | 528 | `def question_submission_decide(request, submission_id):` |
| `apps/exams/views/teacher/submission_inbox.py` | 55 | `def _form_state(request):` |
| `apps/exams/views/teacher/submission_inbox.py` | 72 | `def _teacher_groups(request, organization):` |
| `apps/exams/views/teacher/submission_inbox.py` | 85 | `def _teacher_subjects(request, organization, *, groups=None):` |
| `apps/exams/views/teacher/supervision/_shared.py` | 18 | `def _ensure_organization_context(request):` |
| `apps/exams/views/teacher/supervision/_shared.py` | 26 | `def _ensure_supervision_access(request):` |
| `apps/exams/views/teacher/supervision/_shared.py` | 46 | `def _supervision_exam_queryset(request, organization):` |
| `apps/exams/views/teacher/supervision/_shared.py` | 53 | `def _ensure_supervision_feature_enabled():` |
| `apps/exams/views/teacher/supervision/_shared.py` | 58 | `def _supervision_disabled_json(*, status=403):` |
| `apps/exams/views/teacher/supervision/_shared.py` | 69 | `def _get_scoped_exam_or_404(request, org, exam_id):` |
| `apps/exams/views/teacher/supervision/_shared.py` | 82 | `def _parse_date_param(request):` |
| `apps/exams/views/teacher/supervision/live.py` | 28 | `def exam_live_monitor(request, exam_id):` |
| `apps/exams/views/teacher/supervision/live.py` | 60 | `def exam_live_monitor_poll_api(request, exam_id):` |
| `apps/exams/views/teacher/supervision/live.py` | 76 | `def attempt_live_snapshot_api(request, attempt_id):` |
| `apps/exams/views/teacher/supervision/monitor.py` | 118 | `def supervision_monitor(request):` |
| `apps/exams/views/teacher/supervision/monitor.py` | 278 | `def supervision_detail(request, attempt_id):` |
| `apps/exams/views/teacher/supervision/monitor.py` | 320 | `def teacher_resume_api(request, attempt_id):` |
| `apps/exams/views/teacher/supervision/monitor.py` | 38 | `def log_incident_api(request, attempt_id):` |
| `apps/exams/views/teacher/supervision/monitor.py` | 394 | `def teacher_stop_api(request, attempt_id):` |
| `apps/exams/views/teacher/supervision/monitor.py` | 446 | `def teacher_lock_api(request, attempt_id):` |
| `apps/exams/views/teacher/supervision/monitor.py` | 94 | `def supervision_status_api(request, attempt_id):` |
| `apps/live_exam/api/v1/views.py` | 18 | `def _versioned(response: JsonResponse) -> JsonResponse:` |
| `apps/live_exam/api/v1/views.py` | 24 | `def live_state_json_v1(request: HttpRequest, pin: str) -> JsonResponse:` |
| `apps/live_exam/apps.py` | 4 | `class LiveExamConfig(AppConfig):` |
| `apps/live_exam/auth.py` | 120 | `def authenticate_player_token(token: str \| None, *, pin: str) -> tuple[dict[str, Any] \| None, LivePlayer \| None]:` |
| `apps/live_exam/auth.py` | 143 | `def get_player_from_token(token: str \| None, *, pin: str) -> LivePlayer \| None:` |
| `apps/live_exam/auth.py` | 148 | `def get_request_player(request, *, pin: str) -> LivePlayer \| None:` |
| `apps/live_exam/auth.py` | 152 | `def authorize_socket_connection(` |
| `apps/live_exam/auth.py` | 24 | `def clean_nickname(name: str) -> str:` |
| `apps/live_exam/auth.py` | 30 | `def get_client_id(request) -> str:` |
| `apps/live_exam/auth.py` | 35 | `def _resolve_session_pin(session_or_pin=None, *, pin: str \| None = None, session=None) -> str:` |
| `apps/live_exam/auth.py` | 50 | `def build_player_token(` |
| `apps/live_exam/auth.py` | 76 | `def _load_signed_player_token_payload(token: str) -> dict[str, Any] \| None:` |
| `apps/live_exam/auth.py` | 85 | `def load_player_token_payload(` |
| `apps/live_exam/cache.py` | 30 | `def get_cached_session_settings(session) -> dict[str, Any]:` |
| `apps/live_exam/cache.py` | 50 | `def get_cached_exam_question_ids(session) -> list[int]:` |
| `apps/live_exam/cache.py` | 71 | `def warm_session_settings_cache(session_pk: int) -> None:` |
| `apps/live_exam/constants.py` | 63 | `def build_wait_room_catalog() -> dict[str, object]:` |
| `apps/live_exam/consumers.py` | 104 | `class LiveLobbyConsumer(LiveSessionSocketAuthMixin, AsyncJsonWebsocketConsumer):` |
| `apps/live_exam/consumers.py` | 112 | `async def connect(self):` |
| `apps/live_exam/consumers.py` | 148 | `async def disconnect(self, close_code):` |
| `apps/live_exam/consumers.py` | 151 | `async def lobby_event(self, event):` |
| `apps/live_exam/consumers.py` | 157 | `def _get_lobby_state(self, pin: str) -> dict:` |
| `apps/live_exam/consumers.py` | 169 | `class LivePlayConsumer(LiveSessionSocketAuthMixin, AsyncJsonWebsocketConsumer):` |
| `apps/live_exam/consumers.py` | 179 | `async def connect(self):` |
| `apps/live_exam/consumers.py` | 219 | `async def disconnect(self, close_code):` |
| `apps/live_exam/consumers.py` | 224 | `async def receive_json(self, data, **kwargs):` |
| `apps/live_exam/consumers.py` | 321 | `def _rate_limit_key(self) -> str:` |
| `apps/live_exam/consumers.py` | 330 | `async def play_event(self, event):` |
| `apps/live_exam/consumers.py` | 335 | `def _get_answer_progress(self, pin: str, question_id: int) -> dict:` |
| `apps/live_exam/consumers.py` | 341 | `def _get_reveal_payload(self, pin: str, question_id: int) -> dict:` |
| `apps/live_exam/consumers.py` | 348 | `def _get_player_reveal_payload(self, pin: str, question_id: int) -> dict:` |
| `apps/live_exam/consumers.py` | 355 | `def _save_answer_and_score(self, pin, player_id, client_id, question_id, option_ids, answer_ms):` |
| `apps/live_exam/consumers.py` | 45 | `def _get_scope_ip(scope) -> str:` |
| `apps/live_exam/consumers.py` | 53 | `def _get_connect_rate_identity(scope, pin: str) -> str:` |
| `apps/live_exam/consumers.py` | 84 | `class LiveSessionSocketAuthMixin:` |
| `apps/live_exam/consumers.py` | 86 | `def _authorize_connection(` |
| `apps/live_exam/domain/session.py` | 118 | `def set_question_phase_override(` |
| `apps/live_exam/domain/session.py` | 136 | `def clear_question_phase_override(session: LiveSession) -> bool:` |
| `apps/live_exam/domain/session.py` | 147 | `def question_time_limit(session: LiveSession, exam_question: ExamQuestion) -> int:` |
| `apps/live_exam/domain/session.py` | 164 | `def question_intro_seconds(session: LiveSession, exam_question: ExamQuestion \| None = None) -> float:` |
| `apps/live_exam/domain/session.py` | 168 | `def question_get_ready_seconds(session: LiveSession, *, idx: int) -> float:` |
| `apps/live_exam/domain/session.py` | 172 | `def result_phase_seconds(session: LiveSession \| None = None) -> float:` |
| `apps/live_exam/domain/session.py` | 176 | `def leaderboard_phase_seconds(session: LiveSession \| None = None) -> float:` |
| `apps/live_exam/domain/session.py` | 180 | `def build_question_phase_times(` |
| `apps/live_exam/domain/session.py` | 200 | `def build_reveal_phase_times(session: LiveSession, *, revealed_at):` |
| `apps/live_exam/domain/session.py` | 206 | `def question_points(session: LiveSession, exam_question: ExamQuestion) -> int:` |
| `apps/live_exam/domain/session.py` | 218 | `def get_question_text(exam_question: ExamQuestion) -> str:` |
| `apps/live_exam/domain/session.py` | 226 | `def get_option_text(option: Any) -> str:` |
| `apps/live_exam/domain/session.py` | 234 | `def get_option_label(option: Any) -> str:` |
| `apps/live_exam/domain/session.py` | 241 | `def detect_multi(exam_question: ExamQuestion) -> tuple[bool, int, list[int]]:` |
| `apps/live_exam/domain/session.py` | 24 | `def safe_int(value: Any, default: int = 0) -> int:` |
| `apps/live_exam/domain/session.py` | 31 | `def get_selected_question_ids(session: LiveSession) -> list[int]:` |
| `apps/live_exam/domain/session.py` | 42 | `def get_exam_question_ids(session: LiveSession) -> list[int]:` |
| `apps/live_exam/domain/session.py` | 46 | `def get_total_questions(session: LiveSession) -> int:` |
| `apps/live_exam/domain/session.py` | 53 | `def get_question_by_index(session: LiveSession, index: int) -> ExamQuestion \| None:` |
| `apps/live_exam/domain/session.py` | 71 | `def get_current_exam_question(session: LiveSession) -> ExamQuestion \| None:` |
| `apps/live_exam/domain/session.py` | 75 | `def get_active_question(session: LiveSession) -> ExamQuestion \| None:` |
| `apps/live_exam/domain/session.py` | 86 | `def get_question_phase_override(session: LiveSession, *, question_id: int \| None = None) -> dict[str, Any] \| None:` |
| `apps/live_exam/migrations/0001_initial.py` | 10 | `class Migration(migrations.Migration):` |
| `apps/live_exam/migrations/0002_liveanswer_liveans_session_question_idx.py` | 6 | `class Migration(migrations.Migration):` |
| `apps/live_exam/models.py` | 117 | `def join_url_path(self):` |
| `apps/live_exam/models.py` | 120 | `def get_exam_questions(self):` |
| `apps/live_exam/models.py` | 126 | `class LivePlayer(models.Model):` |
| `apps/live_exam/models.py` | 143 | `class Meta:` |
| `apps/live_exam/models.py` | 146 | `def __str__(self):` |
| `apps/live_exam/models.py` | 150 | `class LiveAnswerQuerySet(models.QuerySet):` |
| `apps/live_exam/models.py` | 152 | `def _normalize_kwargs(kwargs):` |
| `apps/live_exam/models.py` | 159 | `def filter(self, *args, **kwargs):` |
| `apps/live_exam/models.py` | 162 | `def exclude(self, *args, **kwargs):` |
| `apps/live_exam/models.py` | 165 | `def get(self, *args, **kwargs):` |
| `apps/live_exam/models.py` | 169 | `class LiveAnswer(models.Model):` |
| `apps/live_exam/models.py` | 189 | `class Meta:` |
| `apps/live_exam/models.py` | 22 | `def generate_pin():` |
| `apps/live_exam/models.py` | 26 | `class LiveSession(models.Model):` |
| `apps/live_exam/models.py` | 65 | `def _ensure_unique_pin(self):` |
| `apps/live_exam/models.py` | 97 | `def save(self, *args, **kwargs):` |
| `apps/live_exam/scoring.py` | 113 | `def get_answer_progress(*, pin: str, question_id: int) -> dict[str, int]:` |
| `apps/live_exam/scoring.py` | 128 | `def _save_answer_and_score_impl(` |
| `apps/live_exam/scoring.py` | 27 | `def score_multi_fraction(chosen_ids: list[int], correct_ids: list[int], *, mode: str = "strict") -> float:` |
| `apps/live_exam/scoring.py` | 321 | `def _legacy_answer_ms(session: LiveSession, question: ExamQuestion, submitted_at) -> int:` |
| `apps/live_exam/scoring.py` | 335 | `def save_answer_and_score(` |
| `apps/live_exam/scoring.py` | 45 | `def _round_awarded_points(value: float \| Decimal) -> int:` |
| `apps/live_exam/scoring.py` | 55 | `def _kahoot_time_factor(*, answer_ms: int, total_ms: int) -> float:` |
| `apps/live_exam/scoring.py` | 70 | `def calculate_answer_score(` |
| `apps/live_exam/serializers.py` | 107 | `def serialize_answer_distribution(session: LiveSession, question_id: int) -> dict[str, Any]:` |
| `apps/live_exam/serializers.py` | 139 | `def serialize_question_results(session: LiveSession, question_id: int, limit: int = 50) -> list[dict[str, Any]]:` |
| `apps/live_exam/serializers.py` | 173 | `def serialize_player_question_result(` |
| `apps/live_exam/serializers.py` | 216 | `def options_seed(pin: str, question_id: int, started_at: datetime) -> int:` |
| `apps/live_exam/serializers.py` | 221 | `def build_options(exam_question, *, seed: int \| None = None, randomize: bool = True) -> list[dict[str, Any]]:` |
| `apps/live_exam/serializers.py` | 255 | `def serialize_question(` |
| `apps/live_exam/serializers.py` | 29 | `def serialize_player_identity(player: LivePlayer) -> dict[str, Any]:` |
| `apps/live_exam/serializers.py` | 38 | `def serialize_players(session: LiveSession, limit: int = 200) -> list[dict[str, Any]]:` |
| `apps/live_exam/serializers.py` | 42 | `def serialize_top(session: LiveSession, limit: int = 10) -> list[dict[str, Any]]:` |
| `apps/live_exam/serializers.py` | 62 | `def serialize_top_before_question(session: LiveSession, question_id: int, limit: int = 10) -> list[dict[str, Any]]:` |
| `apps/live_exam/services.py` | 153 | `def advance_to_next(session: LiveSession) -> dict:` |
| `apps/live_exam/services.py` | 199 | `def reveal_current(session: LiveSession) -> dict:` |
| `apps/live_exam/services.py` | 224 | `def finish_session(session: LiveSession) -> None:` |
| `apps/live_exam/services.py` | 235 | `def toggle_session_lock(session: LiveSession, *, locked: bool \| None = None) -> bool:` |
| `apps/live_exam/services.py` | 258 | `def remove_player(session: LiveSession, player_id: int) -> bool:` |
| `apps/live_exam/services.py` | 50 | `def create_live_session(exam, host_user) -> LiveSession:` |
| `apps/live_exam/services.py` | 55 | `def start_game(session: LiveSession, *, question_count: int \| None = None) -> dict:` |
| `apps/live_exam/session_settings.py` | 121 | `def normalize_session_setting_updates(` |
| `apps/live_exam/session_settings.py` | 163 | `def normalize_session_settings(raw: dict[str, Any] \| None) -> dict[str, Any]:` |
| `apps/live_exam/session_settings.py` | 169 | `def get_session_settings(session) -> dict[str, Any]:` |
| `apps/live_exam/session_settings.py` | 173 | `def update_session_settings(` |
| `apps/live_exam/session_settings.py` | 200 | `def session_join_path(session) -> str:` |
| `apps/live_exam/session_settings.py` | 205 | `def generate_guest_nickname() -> str:` |
| `apps/live_exam/session_settings.py` | 81 | `def default_session_settings() -> dict[str, Any]:` |
| `apps/live_exam/session_settings.py` | 85 | `def _coerce_bool(value: Any, default: bool) -> bool:` |
| `apps/live_exam/session_settings.py` | 99 | `def allowed_max_participants_for_user(user) -> int:` |
| `apps/live_exam/tests/test_answer_integrity.py` | 121 | `def test_option_not_belonging_to_question_is_rejected(self):` |
| `apps/live_exam/tests/test_answer_integrity.py` | 130 | `def test_valid_correct_answer_scores_and_persists(self):` |
| `apps/live_exam/tests/test_answer_integrity.py` | 30 | `class LiveAnswerIntegrityTest(TestCase):` |
| `apps/live_exam/tests/test_answer_integrity.py` | 31 | `def setUp(self):` |
| `apps/live_exam/tests/test_answer_integrity.py` | 55 | `def _add_player(self, suffix: str) -> LivePlayer:` |
| `apps/live_exam/tests/test_answer_integrity.py` | 63 | `def _activate(self, *, ends_offset_seconds: int = 19) -> None:` |
| `apps/live_exam/tests/test_answer_integrity.py` | 82 | `def _submit(self, player: LivePlayer, option_ids: list[int]):` |
| `apps/live_exam/tests/test_answer_integrity.py` | 92 | `def test_submission_after_deadline_is_rejected(self):` |
| `apps/live_exam/tests/test_answer_integrity.py` | 99 | `def test_duplicate_answer_is_idempotent_and_does_not_double_score(self):` |
| `apps/live_exam/tests/test_architecture.py` | 4 | `class LiveExamArchitectureModulesTest(SimpleTestCase):` |
| `apps/live_exam/tests/test_architecture.py` | 5 | `def test_refactored_modules_are_importable(self):` |
| `apps/live_exam/tests/test_consumers.py` | 1020 | `class WebSocketOriginValidationTest(TransactionTestCase):` |
| `apps/live_exam/tests/test_consumers.py` | 1027 | `def setUp(self):` |
| `apps/live_exam/tests/test_consumers.py` | 1070 | `def _player_headers(self):` |
| `apps/live_exam/tests/test_consumers.py` | 1076 | `def _viewer_headers(self, client_id: str):` |
| `apps/live_exam/tests/test_consumers.py` | 1082 | `def _player_headers_for(self, *, player_id: int, client_id: str):` |
| `apps/live_exam/tests/test_consumers.py` | 108 | `def test_lobby_ws_accepts_authenticated_player(self):` |
| `apps/live_exam/tests/test_consumers.py` | 1096 | `def test_foreign_origin_lobby_connection_is_rejected(self):` |
| `apps/live_exam/tests/test_consumers.py` | 1099 | `async def scenario():` |
| `apps/live_exam/tests/test_consumers.py` | 109 | `async def scenario():` |
| `apps/live_exam/tests/test_consumers.py` | 1111 | `def test_foreign_origin_play_connection_is_rejected(self):` |
| `apps/live_exam/tests/test_consumers.py` | 1114 | `async def scenario():` |
| `apps/live_exam/tests/test_consumers.py` | 1129 | `def test_player_cannot_send_non_answer_commands(self):` |
| `apps/live_exam/tests/test_consumers.py` | 1132 | `async def scenario():` |
| `apps/live_exam/tests/test_consumers.py` | 1152 | `def test_player_answer_accepted_on_valid_origin(self):` |
| `apps/live_exam/tests/test_consumers.py` | 1160 | `async def scenario():` |
| `apps/live_exam/tests/test_consumers.py` | 1191 | `class WebSocketHostRoleIsolationTest(TransactionTestCase):` |
| `apps/live_exam/tests/test_consumers.py` | 1199 | `def setUp(self):` |
| `apps/live_exam/tests/test_consumers.py` | 1222 | `def _session_headers_for(self, user):` |
| `apps/live_exam/tests/test_consumers.py` | 1234 | `def test_non_host_teacher_rejected_on_play_websocket(self):` |
| `apps/live_exam/tests/test_consumers.py` | 1242 | `async def scenario():` |
| `apps/live_exam/tests/test_consumers.py` | 1259 | `def test_host_ws_connection_cannot_submit_answers(self):` |
| `apps/live_exam/tests/test_consumers.py` | 1267 | `async def scenario():` |
| `apps/live_exam/tests/test_consumers.py` | 126 | `def test_lobby_ws_delivers_reaction_events(self):` |
| `apps/live_exam/tests/test_consumers.py` | 127 | `async def scenario():` |
| `apps/live_exam/tests/test_consumers.py` | 1294 | `class ForgedWebSocketCommandTest(TransactionTestCase):` |
| `apps/live_exam/tests/test_consumers.py` | 1303 | `def setUp(self):` |
| `apps/live_exam/tests/test_consumers.py` | 1343 | `def _player_headers(self):` |
| `apps/live_exam/tests/test_consumers.py` | 1349 | `def _assert_forged_command_ignored(self, payload, label=""):` |
| `apps/live_exam/tests/test_consumers.py` | 1352 | `async def scenario():` |
| `apps/live_exam/tests/test_consumers.py` | 1373 | `def test_forged_start_game_ignored(self):` |
| `apps/live_exam/tests/test_consumers.py` | 1376 | `def test_forged_next_question_ignored(self):` |
| `apps/live_exam/tests/test_consumers.py` | 1379 | `def test_forged_reveal_answer_ignored(self):` |
| `apps/live_exam/tests/test_consumers.py` | 1385 | `def test_forged_finish_session_ignored(self):` |
| `apps/live_exam/tests/test_consumers.py` | 1388 | `def test_forged_kick_player_ignored(self):` |
| `apps/live_exam/tests/test_consumers.py` | 1394 | `def test_forged_change_state_ignored(self):` |
| `apps/live_exam/tests/test_consumers.py` | 1400 | `def test_forged_publish_scoreboard_ignored(self):` |
| `apps/live_exam/tests/test_consumers.py` | 1416 | `class WebSocketRateLimitTest(TransactionTestCase):` |
| `apps/live_exam/tests/test_consumers.py` | 1422 | `def setUp(self):` |
| `apps/live_exam/tests/test_consumers.py` | 1463 | `def _player_headers(self):` |
| `apps/live_exam/tests/test_consumers.py` | 1469 | `def _viewer_headers(self, client_id: str):` |
| `apps/live_exam/tests/test_consumers.py` | 1475 | `def _player_headers_for(self, *, player_id: int, client_id: str):` |
| `apps/live_exam/tests/test_consumers.py` | 1489 | `def test_connect_flood_lobby_is_blocked(self):` |
| `apps/live_exam/tests/test_consumers.py` | 1492 | `async def scenario():` |
| `apps/live_exam/tests/test_consumers.py` | 1513 | `def test_connect_flood_play_is_blocked(self):` |
| `apps/live_exam/tests/test_consumers.py` | 1516 | `async def scenario():` |
| `apps/live_exam/tests/test_consumers.py` | 1539 | `def test_lobby_connects_for_distinct_clients_sharing_same_ip(self):` |
| `apps/live_exam/tests/test_consumers.py` | 1542 | `async def scenario():` |
| `apps/live_exam/tests/test_consumers.py` | 1568 | `def test_play_connects_for_distinct_players_sharing_same_ip(self):` |
| `apps/live_exam/tests/test_consumers.py` | 1583 | `async def scenario():` |
| `apps/live_exam/tests/test_consumers.py` | 1607 | `def test_message_flood_is_blocked(self):` |
| `apps/live_exam/tests/test_consumers.py` | 1611 | `async def scenario():` |
| `apps/live_exam/tests/test_consumers.py` | 162 | `def test_play_ws_accepts_authenticated_player(self):` |
| `apps/live_exam/tests/test_consumers.py` | 163 | `async def scenario():` |
| `apps/live_exam/tests/test_consumers.py` | 1642 | `def test_answer_flood_is_blocked(self):` |
| `apps/live_exam/tests/test_consumers.py` | 1650 | `async def scenario():` |
| `apps/live_exam/tests/test_consumers.py` | 177 | `def test_play_ws_accepts_host_session_auth(self):` |
| `apps/live_exam/tests/test_consumers.py` | 180 | `async def scenario():` |
| `apps/live_exam/tests/test_consumers.py` | 194 | `def test_expired_player_token_rejected(self):` |
| `apps/live_exam/tests/test_consumers.py` | 205 | `async def scenario():` |
| `apps/live_exam/tests/test_consumers.py` | 222 | `def test_websocket_rejects_invalid_origin(self):` |
| `apps/live_exam/tests/test_consumers.py` | 229 | `async def scenario():` |
| `apps/live_exam/tests/test_consumers.py` | 247 | `def test_player_token_pin_mismatch_rejected(self):` |
| `apps/live_exam/tests/test_consumers.py` | 266 | `async def scenario():` |
| `apps/live_exam/tests/test_consumers.py` | 282 | `def test_player_cannot_see_correct_answers_in_websocket(self):` |
| `apps/live_exam/tests/test_consumers.py` | 291 | `async def scenario():` |
| `apps/live_exam/tests/test_consumers.py` | 340 | `def test_duplicate_answer_prevented(self):` |
| `apps/live_exam/tests/test_consumers.py` | 368 | `async def scenario():` |
| `apps/live_exam/tests/test_consumers.py` | 37 | `class LiveExamConsumerAuthTest(TransactionTestCase):` |
| `apps/live_exam/tests/test_consumers.py` | 38 | `def setUp(self):` |
| `apps/live_exam/tests/test_consumers.py` | 415 | `def test_answer_after_time_expires_rejected(self):` |
| `apps/live_exam/tests/test_consumers.py` | 441 | `async def scenario():` |
| `apps/live_exam/tests/test_consumers.py` | 480 | `class LiveExamAnswerSubmissionConsumerTest(TransactionTestCase):` |
| `apps/live_exam/tests/test_consumers.py` | 481 | `def setUp(self):` |
| `apps/live_exam/tests/test_consumers.py` | 568 | `def _player_headers(self, player):` |
| `apps/live_exam/tests/test_consumers.py` | 576 | `def _host_session_headers(self):` |
| `apps/live_exam/tests/test_consumers.py` | 582 | `def _host_and_player_headers(self, player):` |
| `apps/live_exam/tests/test_consumers.py` | 599 | `def test_play_ws_rejects_non_current_question_answers(self):` |
| `apps/live_exam/tests/test_consumers.py` | 600 | `async def scenario():` |
| `apps/live_exam/tests/test_consumers.py` | 625 | `def test_play_ws_rejects_late_answers(self):` |
| `apps/live_exam/tests/test_consumers.py` | 631 | `async def scenario():` |
| `apps/live_exam/tests/test_consumers.py` | 656 | `def test_play_ws_rejects_answers_during_intro_window(self):` |
| `apps/live_exam/tests/test_consumers.py` | 662 | `async def scenario():` |
| `apps/live_exam/tests/test_consumers.py` | 687 | `def test_play_ws_rejects_cross_exam_answers(self):` |
| `apps/live_exam/tests/test_consumers.py` | 688 | `async def scenario():` |
| `apps/live_exam/tests/test_consumers.py` | 68 | `def _player_headers(self, *, pin=None):` |
| `apps/live_exam/tests/test_consumers.py` | 713 | `def test_play_ws_reveals_immediately_after_all_players_answer(self):` |
| `apps/live_exam/tests/test_consumers.py` | 721 | `async def scenario():` |
| `apps/live_exam/tests/test_consumers.py` | 76 | `def _host_session_headers(self):` |
| `apps/live_exam/tests/test_consumers.py` | 812 | `def test_answer_progress_reaches_host_not_players(self):` |
| `apps/live_exam/tests/test_consumers.py` | 822 | `async def scenario():` |
| `apps/live_exam/tests/test_consumers.py` | 82 | `def test_lobby_ws_allows_viewer_without_auth(self):` |
| `apps/live_exam/tests/test_consumers.py` | 83 | `async def scenario():` |
| `apps/live_exam/tests/test_consumers.py` | 871 | `def test_host_reveal_payload_contains_results_field(self):` |
| `apps/live_exam/tests/test_consumers.py` | 875 | `async def scenario():` |
| `apps/live_exam/tests/test_consumers.py` | 924 | `def test_play_ws_prefers_player_cookie_when_host_session_is_also_present(self):` |
| `apps/live_exam/tests/test_consumers.py` | 927 | `async def scenario():` |
| `apps/live_exam/tests/test_consumers.py` | 956 | `def test_play_ws_duplicate_answer_is_idempotent(self):` |
| `apps/live_exam/tests/test_consumers.py` | 959 | `async def scenario():` |
| `apps/live_exam/tests/test_consumers.py` | 98 | `def test_play_ws_rejects_missing_auth(self):` |
| `apps/live_exam/tests/test_consumers.py` | 99 | `async def scenario():` |
| `apps/live_exam/tests/test_models.py` | 135 | `def test_legacy_shorter_pin_still_fits_field(self):` |
| `apps/live_exam/tests/test_models.py` | 140 | `class LiveSessionPinIntegrityRetryTest(TestCase):` |
| `apps/live_exam/tests/test_models.py` | 146 | `def _make_exam_and_teacher(self):` |
| `apps/live_exam/tests/test_models.py` | 178 | `def test_integrity_error_triggers_pin_retry(self):` |
| `apps/live_exam/tests/test_models.py` | 17 | `class GeneratePinTest(TestCase):` |
| `apps/live_exam/tests/test_models.py` | 192 | `def _raise_once_then_succeed(self_inner, *args, **kwargs):` |
| `apps/live_exam/tests/test_models.py` | 207 | `def test_repeated_integrity_error_raises_after_max_tries(self):` |
| `apps/live_exam/tests/test_models.py` | 20 | `def test_pin_uses_correct_length(self):` |
| `apps/live_exam/tests/test_models.py` | 25 | `def test_pin_is_eight_digits(self):` |
| `apps/live_exam/tests/test_models.py` | 31 | `def test_pin_contains_only_allowed_characters(self):` |
| `apps/live_exam/tests/test_models.py` | 39 | `def test_pin_avoids_ambiguous_characters(self):` |
| `apps/live_exam/tests/test_models.py` | 45 | `def test_pin_uses_secrets_module(self):` |
| `apps/live_exam/tests/test_models.py` | 55 | `def test_pins_are_unique_across_many_calls(self):` |
| `apps/live_exam/tests/test_models.py` | 62 | `class LiveSessionPinFieldTest(TestCase):` |
| `apps/live_exam/tests/test_models.py` | 73 | `def test_pin_field_max_length_matches_constant(self):` |
| `apps/live_exam/tests/test_models.py` | 83 | `def test_pin_field_max_length_is_eight(self):` |
| `apps/live_exam/tests/test_models.py` | 89 | `def test_create_live_session_with_eight_char_pin(self):` |
| `apps/live_exam/tests/test_reveal_gating.py` | 34 | `class LiveRevealGatingTest(TestCase):` |
| `apps/live_exam/tests/test_reveal_gating.py` | 35 | `def setUp(self):` |
| `apps/live_exam/tests/test_reveal_gating.py` | 67 | `def _player_payload(self):` |
| `apps/live_exam/tests/test_reveal_gating.py` | 72 | `def _host_payload(self):` |
| `apps/live_exam/tests/test_reveal_gating.py` | 77 | `def test_player_reveal_never_includes_per_player_results(self):` |
| `apps/live_exam/tests/test_reveal_gating.py` | 83 | `def test_player_reveal_exposes_correct_ids_only_at_reveal_stage(self):` |
| `apps/live_exam/tests/test_reveal_gating.py` | 90 | `def test_host_reveal_includes_results_and_correct_ids(self):` |
| `apps/live_exam/tests/test_reveal_gating.py` | 95 | `def test_player_and_host_payloads_do_not_leak_extra_answer_fields(self):` |
| `apps/live_exam/tests/test_round_scenario.py` | 202 | `def test_multi_choice_round_can_award_partial_points_for_partially_wrong_answers(self):` |
| `apps/live_exam/tests/test_round_scenario.py` | 20 | `class LiveExamRoundScenarioTest(TestCase):` |
| `apps/live_exam/tests/test_round_scenario.py` | 21 | `def setUp(self):` |
| `apps/live_exam/tests/test_round_scenario.py` | 40 | `def _make_active_single_choice_session(self):` |
| `apps/live_exam/tests/test_round_scenario.py` | 94 | `def test_ten_player_round_scoring_counts_distribution_and_reveal_are_consistent(self):` |
| `apps/live_exam/tests/test_score_integrity.py` | 164 | `def _make_single_question_session(self):` |
| `apps/live_exam/tests/test_score_integrity.py` | 186 | `def test_option_ids_from_another_question_are_rejected(self):` |
| `apps/live_exam/tests/test_score_integrity.py` | 200 | `def test_understated_answer_ms_is_clamped_to_server_elapsed_time(self):` |
| `apps/live_exam/tests/test_score_integrity.py` | 22 | `class LiveScorePayloadIntegrityTest(TestCase):` |
| `apps/live_exam/tests/test_score_integrity.py` | 29 | `def setUp(self):` |
| `apps/live_exam/tests/test_score_integrity.py` | 46 | `def _activate_question(self, session, question, idx):` |
| `apps/live_exam/tests/test_score_integrity.py` | 65 | `def test_wrong_answer_mid_round_must_not_zero_other_scores(self):` |
| `apps/live_exam/tests/test_scoring.py` | 116 | `def test_player_reveal_payload_includes_correct_option_ids_at_reveal(self):` |
| `apps/live_exam/tests/test_scoring.py` | 122 | `def test_player_reveal_payload_omits_per_player_results(self):` |
| `apps/live_exam/tests/test_scoring.py` | 127 | `def test_host_reveal_payload_includes_correct_option_ids_and_results(self):` |
| `apps/live_exam/tests/test_scoring.py` | 134 | `def test_reveal_payload_uses_session_question_end_timestamp_by_default(self):` |
| `apps/live_exam/tests/test_scoring.py` | 143 | `class LiveExamLowPointScoringTest(TestCase):` |
| `apps/live_exam/tests/test_scoring.py` | 146 | `def setUp(self):` |
| `apps/live_exam/tests/test_scoring.py` | 184 | `def test_calculate_answer_score_rounds_half_up_for_one_point_question(self):` |
| `apps/live_exam/tests/test_scoring.py` | 196 | `def test_calculate_answer_score_rewards_faster_correct_answer(self):` |
| `apps/live_exam/tests/test_scoring.py` | 218 | `def test_save_answer_and_score_does_not_keep_correct_one_point_answer_at_zero(self):` |
| `apps/live_exam/tests/test_scoring.py` | 256 | `def test_save_answer_and_score_awards_full_question_points(self):` |
| `apps/live_exam/tests/test_scoring.py` | 293 | `class LiveExamSaveAnswerDuplicateTest(TestCase):` |
| `apps/live_exam/tests/test_scoring.py` | 296 | `def setUp(self):` |
| `apps/live_exam/tests/test_scoring.py` | 30 | `class LiveExamPayloadSecurityTest(TestCase):` |
| `apps/live_exam/tests/test_scoring.py` | 33 | `def setUp(self):` |
| `apps/live_exam/tests/test_scoring.py` | 351 | `def test_save_answer_prevents_duplicate_answer(self):` |
| `apps/live_exam/tests/test_scoring.py` | 383 | `class LiveExamAnswerWindowEnforcementTest(TestCase):` |
| `apps/live_exam/tests/test_scoring.py` | 386 | `def setUp(self):` |
| `apps/live_exam/tests/test_scoring.py` | 425 | `def _make_session_and_player(self, *, question_started_offset_s, question_ends_offset_s):` |
| `apps/live_exam/tests/test_scoring.py` | 442 | `def test_answer_rejected_when_answer_window_has_not_opened_yet(self):` |
| `apps/live_exam/tests/test_scoring.py` | 462 | `def test_answer_rejected_after_question_ends_at(self):` |
| `apps/live_exam/tests/test_scoring.py` | 482 | `def test_answer_accepted_within_valid_window(self):` |
| `apps/live_exam/tests/test_scoring.py` | 502 | `class LiveExamLockedSessionTest(TestCase):` |
| `apps/live_exam/tests/test_scoring.py` | 505 | `def setUp(self):` |
| `apps/live_exam/tests/test_scoring.py` | 531 | `def test_join_is_rejected_when_session_is_locked(self):` |
| `apps/live_exam/tests/test_scoring.py` | 546 | `def test_join_succeeds_when_session_is_unlocked(self):` |
| `apps/live_exam/tests/test_scoring.py` | 565 | `class ScoringRequiredNamedTests(TestCase):` |
| `apps/live_exam/tests/test_scoring.py` | 573 | `def setUp(self):` |
| `apps/live_exam/tests/test_scoring.py` | 611 | `def _make_active_session_and_player(self):` |
| `apps/live_exam/tests/test_scoring.py` | 630 | `def test_duplicate_answer_prevented(self):` |
| `apps/live_exam/tests/test_scoring.py` | 663 | `def test_answer_after_time_expires_rejected(self):` |
| `apps/live_exam/tests/test_scoring.py` | 73 | `def test_build_options_does_not_expose_is_correct(self):` |
| `apps/live_exam/tests/test_scoring.py` | 80 | `def test_build_options_uses_display_order_labels_and_shapes(self):` |
| `apps/live_exam/tests/test_scoring.py` | 93 | `def test_serialize_question_does_not_expose_correct_option_ids(self):` |
| `apps/live_exam/tests/test_services.py` | 20 | `class LiveExamSerializerTransportTest(TestCase):` |
| `apps/live_exam/tests/test_services.py` | 21 | `def setUp(self):` |
| `apps/live_exam/tests/test_services.py` | 53 | `def test_serialize_player_identity_includes_accessory(self):` |
| `apps/live_exam/tests/test_services.py` | 58 | `def test_serialize_players_includes_accessory(self):` |
| `apps/live_exam/tests/test_services.py` | 63 | `def test_serialize_top_includes_accessory(self):` |
| `apps/live_exam/tests/test_services.py` | 68 | `def test_build_lobby_state_payload_includes_accessory(self):` |
| `apps/live_exam/tests/test_services.py` | 73 | `def test_build_reaction_event_payload_includes_player_identity(self):` |
| `apps/live_exam/tests/test_session_settings.py` | 11 | `def test_show_questions_on_devices_can_still_be_disabled_explicitly(self):` |
| `apps/live_exam/tests/test_session_settings.py` | 6 | `class LiveSessionSettingsDefaultsTest(SimpleTestCase):` |
| `apps/live_exam/tests/test_session_settings.py` | 7 | `def test_show_questions_on_devices_is_enabled_by_default(self):` |
| `apps/live_exam/tests/test_views.py` | 1006 | `def test_state_json_includes_player_answer_summary(self):` |
| `apps/live_exam/tests/test_views.py` | 1037 | `def test_state_json_reveal_includes_leaderboard_transition_meta(self):` |
| `apps/live_exam/tests/test_views.py` | 105 | `def test_helper_functions_in_helpers_module(self):` |
| `apps/live_exam/tests/test_views.py` | 1079 | `def test_state_json_finished_includes_finished_at(self):` |
| `apps/live_exam/tests/test_views.py` | 1095 | `class LiveStateRateLimitTest(TestCase):` |
| `apps/live_exam/tests/test_views.py` | 1096 | `def setUp(self):` |
| `apps/live_exam/tests/test_views.py` | 1130 | `def test_state_json_blocks_after_rate_limit(self):` |
| `apps/live_exam/tests/test_views.py` | 1140 | `class LivePlayerProtectedViewsTest(TestCase):` |
| `apps/live_exam/tests/test_views.py` | 1143 | `def setUp(self):` |
| `apps/live_exam/tests/test_views.py` | 1168 | `def _authenticate_player(self, client=None):` |
| `apps/live_exam/tests/test_views.py` | 1184 | `def test_wait_room_requires_player_token(self):` |
| `apps/live_exam/tests/test_views.py` | 1190 | `def test_wait_room_shows_player_context_for_authenticated_player(self):` |
| `apps/live_exam/tests/test_views.py` | 1201 | `def test_wait_room_redirects_to_player_screen_after_game_starts(self):` |
| `apps/live_exam/tests/test_views.py` | 1212 | `def test_player_screen_requires_valid_player_token(self):` |
| `apps/live_exam/tests/test_views.py` | 1219 | `class LiveWaitRoomInteractionTest(TestCase):` |
| `apps/live_exam/tests/test_views.py` | 1220 | `def setUp(self):` |
| `apps/live_exam/tests/test_views.py` | 1256 | `def test_wait_room_profile_update_success(self):` |
| `apps/live_exam/tests/test_views.py` | 1273 | `def test_wait_room_profile_update_rejects_empty_nickname(self):` |
| `apps/live_exam/tests/test_views.py` | 1281 | `def test_wait_room_profile_update_truncates_long_nickname(self):` |
| `apps/live_exam/tests/test_views.py` | 1289 | `def test_wait_room_profile_update_rejects_invalid_avatar(self):` |
| `apps/live_exam/tests/test_views.py` | 1297 | `def test_wait_room_profile_update_rejects_invalid_accessory(self):` |
| `apps/live_exam/tests/test_views.py` | 1305 | `def test_wait_room_profile_update_rejects_duplicate_nickname(self):` |
| `apps/live_exam/tests/test_views.py` | 1321 | `def test_wait_room_profile_update_requires_player_token(self):` |
| `apps/live_exam/tests/test_views.py` | 1329 | `def test_wait_room_reaction_accepts_known_reaction(self):` |
| `apps/live_exam/tests/test_views.py` | 1338 | `def test_wait_room_reaction_rejects_invalid_reaction(self):` |
| `apps/live_exam/tests/test_views.py` | 1346 | `def test_wait_room_template_includes_state_polling_url(self):` |
| `apps/live_exam/tests/test_views.py` | 1351 | `def test_player_screen_template_includes_http_fallback_urls(self):` |
| `apps/live_exam/tests/test_views.py` | 1368 | `def test_answer_submit_saves_answer_for_authenticated_player(self):` |
| `apps/live_exam/tests/test_views.py` | 1399 | `def test_answer_submit_does_not_broadcast_personal_answer_state_to_other_players(self):` |
| `apps/live_exam/tests/test_views.py` | 1451 | `def test_answer_submit_requires_authenticated_player_token(self):` |
| `apps/live_exam/tests/test_views.py` | 1463 | `class LiveWaitRoomReactionRateLimitTest(TestCase):` |
| `apps/live_exam/tests/test_views.py` | 1464 | `def setUp(self):` |
| `apps/live_exam/tests/test_views.py` | 147 | `class LiveSessionCreationTest(TestCase):` |
| `apps/live_exam/tests/test_views.py` | 1498 | `def test_wait_room_reaction_rate_limit_blocks_second_request(self):` |
| `apps/live_exam/tests/test_views.py` | 150 | `def setUp(self):` |
| `apps/live_exam/tests/test_views.py` | 1513 | `class HelperFunctionsTest(TestCase):` |
| `apps/live_exam/tests/test_views.py` | 1516 | `def test_safe_int(self):` |
| `apps/live_exam/tests/test_views.py` | 1525 | `def test_clean_nickname(self):` |
| `apps/live_exam/tests/test_views.py` | 1533 | `def test_score_multi_fraction_strict(self):` |
| `apps/live_exam/tests/test_views.py` | 1546 | `def test_score_multi_fraction_partial(self):` |
| `apps/live_exam/tests/test_views.py` | 1560 | `class URLPatternTest(TestCase):` |
| `apps/live_exam/tests/test_views.py` | 1563 | `def setUp(self):` |
| `apps/live_exam/tests/test_views.py` | 1587 | `def test_all_urls_resolve(self):` |
| `apps/live_exam/tests/test_views.py` | 1615 | `class LiveExamFrontendAssetHardeningTest(TestCase):` |
| `apps/live_exam/tests/test_views.py` | 1616 | `def setUp(self):` |
| `apps/live_exam/tests/test_views.py` | 1641 | `def test_host_lobby_uses_local_chart_bundle(self):` |
| `apps/live_exam/tests/test_views.py` | 1651 | `def test_host_presentation_uses_local_chart_bundle(self):` |
| `apps/live_exam/tests/test_views.py` | 1667 | `class HostOrgRBACTest(TestCase):` |
| `apps/live_exam/tests/test_views.py` | 1673 | `def setUp(self):` |
| `apps/live_exam/tests/test_views.py` | 1713 | `def _host_urls(self):` |
| `apps/live_exam/tests/test_views.py` | 1720 | `def _host_post_urls(self):` |
| `apps/live_exam/tests/test_views.py` | 1732 | `def test_host_endpoints_require_org_context(self):` |
| `apps/live_exam/tests/test_views.py` | 1746 | `def test_cross_org_host_access_is_blocked(self):` |
| `apps/live_exam/tests/test_views.py` | 1761 | `def test_host_with_correct_org_context_is_allowed(self):` |
| `apps/live_exam/tests/test_views.py` | 1776 | `def test_missing_exam_host_permission_blocks_host_access(self):` |
| `apps/live_exam/tests/test_views.py` | 177 | `def test_create_session_requires_login(self):` |
| `apps/live_exam/tests/test_views.py` | 1803 | `class SuspendedOrgHostActionTest(TestCase):` |
| `apps/live_exam/tests/test_views.py` | 1809 | `def setUp(self):` |
| `apps/live_exam/tests/test_views.py` | 1839 | `def _assert_host_action_blocked(self, status="suspended"):` |
| `apps/live_exam/tests/test_views.py` | 183 | `def test_create_session_requires_teacher_role(self):` |
| `apps/live_exam/tests/test_views.py` | 1863 | `def test_suspended_org_blocks_host_actions(self):` |
| `apps/live_exam/tests/test_views.py` | 1867 | `def test_inactive_org_blocks_host_actions(self):` |
| `apps/live_exam/tests/test_views.py` | 1877 | `class PlayerPayloadHardeningTest(TestCase):` |
| `apps/live_exam/tests/test_views.py` | 1883 | `def setUp(self):` |
| `apps/live_exam/tests/test_views.py` | 1933 | `def _put_session_in_reveal(self):` |
| `apps/live_exam/tests/test_views.py` | 193 | `def test_create_session_requires_ownership(self):` |
| `apps/live_exam/tests/test_views.py` | 1950 | `def test_player_payload_does_not_contain_results_during_reveal(self):` |
| `apps/live_exam/tests/test_views.py` | 1962 | `def test_host_payload_contains_results_during_reveal(self):` |
| `apps/live_exam/tests/test_views.py` | 1974 | `def test_correct_option_ids_hidden_during_question_phase(self):` |
| `apps/live_exam/tests/test_views.py` | 1999 | `class PlayerTokenSecurityTest(TestCase):` |
| `apps/live_exam/tests/test_views.py` | 2004 | `def setUp(self):` |
| `apps/live_exam/tests/test_views.py` | 2024 | `def test_invalid_player_token_is_rejected_on_state_json(self):` |
| `apps/live_exam/tests/test_views.py` | 2031 | `def test_token_for_different_pin_is_rejected(self):` |
| `apps/live_exam/tests/test_views.py` | 203 | `def test_create_session_success(self):` |
| `apps/live_exam/tests/test_views.py` | 2051 | `def test_unauthenticated_wait_room_redirects_to_join(self):` |
| `apps/live_exam/tests/test_views.py` | 2057 | `def test_unauthenticated_player_screen_redirects_to_join(self):` |
| `apps/live_exam/tests/test_views.py` | 2069 | `class LiveExamPinEnumerationHardeningTest(TestCase):` |
| `apps/live_exam/tests/test_views.py` | 2078 | `def setUp(self):` |
| `apps/live_exam/tests/test_views.py` | 2085 | `def test_wrong_length_pin_returns_400(self):` |
| `apps/live_exam/tests/test_views.py` | 2091 | `def test_nonexistent_pin_returns_404_not_500(self):` |
| `apps/live_exam/tests/test_views.py` | 2099 | `def test_pin_entry_get_renders_form(self):` |
| `apps/live_exam/tests/test_views.py` | 2105 | `def test_valid_pin_redirects_to_join_page(self):` |
| `apps/live_exam/tests/test_views.py` | 2125 | `class LiveExamSessionStateHardeningTest(TestCase):` |
| `apps/live_exam/tests/test_views.py` | 2132 | `def setUp(self):` |
| `apps/live_exam/tests/test_views.py` | 2153 | `def test_state_json_returns_403_for_anonymous_without_token(self):` |
| `apps/live_exam/tests/test_views.py` | 2158 | `def test_state_json_returns_403_for_anonymous_nonexistent_session(self):` |
| `apps/live_exam/tests/test_views.py` | 2162 | `def test_state_json_returns_200_for_authenticated_host(self):` |
| `apps/live_exam/tests/test_views.py` | 2168 | `def test_qr_png_requires_authenticated_host(self):` |
| `apps/live_exam/tests/test_views.py` | 2172 | `def test_qr_png_returns_404_for_non_host(self):` |
| `apps/live_exam/tests/test_views.py` | 2180 | `def test_qr_png_returns_image_for_host(self):` |
| `apps/live_exam/tests/test_views.py` | 2188 | `def test_join_page_returns_404_for_nonexistent_session(self):` |
| `apps/live_exam/tests/test_views.py` | 2193 | `def test_wait_room_for_nonexistent_session_returns_404(self):` |
| `apps/live_exam/tests/test_views.py` | 2198 | `def test_player_cannot_skip_to_screen_without_token(self):` |
| `apps/live_exam/tests/test_views.py` | 2205 | `class LiveExamHostActionHardeningTest(TestCase):` |
| `apps/live_exam/tests/test_views.py` | 2208 | `def setUp(self):` |
| `apps/live_exam/tests/test_views.py` | 221 | `def test_org_admin_author_can_create_session(self):` |
| `apps/live_exam/tests/test_views.py` | 2230 | `def test_host_start_session_rejected_for_non_org_member(self):` |
| `apps/live_exam/tests/test_views.py` | 2237 | `def test_host_finish_rejected_for_anonymous(self):` |
| `apps/live_exam/tests/test_views.py` | 2248 | `class HostOwnershipEnforcementTest(TestCase):` |
| `apps/live_exam/tests/test_views.py` | 2259 | `def setUp(self):` |
| `apps/live_exam/tests/test_views.py` | 2301 | `def _all_host_post_urls(self):` |
| `apps/live_exam/tests/test_views.py` | 2314 | `def test_non_host_colleague_blocked_from_all_host_post_actions(self):` |
| `apps/live_exam/tests/test_views.py` | 2328 | `def test_non_host_colleague_blocked_from_host_lobby(self):` |
| `apps/live_exam/tests/test_views.py` | 2333 | `def test_non_host_colleague_blocked_from_host_presentation(self):` |
| `apps/live_exam/tests/test_views.py` | 2344 | `class StateTransitionGuardTest(TestCase):` |
| `apps/live_exam/tests/test_views.py` | 2350 | `def setUp(self):` |
| `apps/live_exam/tests/test_views.py` | 2384 | `def _set_state(self, state):` |
| `apps/live_exam/tests/test_views.py` | 2390 | `def test_start_game_rejected_when_already_in_question(self):` |
| `apps/live_exam/tests/test_views.py` | 2396 | `def test_start_game_rejected_when_in_reveal(self):` |
| `apps/live_exam/tests/test_views.py` | 2402 | `def test_start_game_rejected_when_finished(self):` |
| `apps/live_exam/tests/test_views.py` | 2410 | `def test_reveal_rejected_from_lobby(self):` |
| `apps/live_exam/tests/test_views.py` | 2416 | `def test_reveal_rejected_from_reveal(self):` |
| `apps/live_exam/tests/test_views.py` | 2422 | `def test_reveal_rejected_from_finished(self):` |
| `apps/live_exam/tests/test_views.py` | 2430 | `def test_next_question_rejected_from_lobby(self):` |
| `apps/live_exam/tests/test_views.py` | 2436 | `def test_next_question_rejected_from_finished(self):` |
| `apps/live_exam/tests/test_views.py` | 2444 | `def test_finish_rejected_when_already_finished(self):` |
| `apps/live_exam/tests/test_views.py` | 246 | `def test_create_session_redirects_when_exam_is_passive(self):` |
| `apps/live_exam/tests/test_views.py` | 259 | `class LiveSessionResultsViewTest(TestCase):` |
| `apps/live_exam/tests/test_views.py` | 262 | `def setUp(self):` |
| `apps/live_exam/tests/test_views.py` | 353 | `def test_session_detail_uses_local_chart_bundle_and_distribution_data(self):` |
| `apps/live_exam/tests/test_views.py` | 375 | `def test_session_detail_falls_back_to_answered_questions_when_selection_is_missing(self):` |
| `apps/live_exam/tests/test_views.py` | 38 | `def _create_org_role_and_membership(user, org, permissions=None):` |
| `apps/live_exam/tests/test_views.py` | 394 | `def test_live_results_back_and_detail_links_preserve_original_return_to(self):` |
| `apps/live_exam/tests/test_views.py` | 417 | `def test_live_session_detail_back_link_preserves_original_return_to(self):` |
| `apps/live_exam/tests/test_views.py` | 438 | `def test_live_results_page_renders_translated_english_copy(self):` |
| `apps/live_exam/tests/test_views.py` | 452 | `def test_live_session_detail_page_renders_translated_english_copy(self):` |
| `apps/live_exam/tests/test_views.py` | 470 | `class LiveJoinTest(TestCase):` |
| `apps/live_exam/tests/test_views.py` | 473 | `def setUp(self):` |
| `apps/live_exam/tests/test_views.py` | 498 | `def test_join_page_accessible(self):` |
| `apps/live_exam/tests/test_views.py` | 505 | `def test_join_page_is_never_cached(self):` |
| `apps/live_exam/tests/test_views.py` | 511 | `def test_join_page_exposes_remembered_player_context(self):` |
| `apps/live_exam/tests/test_views.py` | 537 | `def test_pin_entry_page_accessible(self):` |
| `apps/live_exam/tests/test_views.py` | 549 | `def test_pin_entry_page_is_never_cached(self):` |
| `apps/live_exam/tests/test_views.py` | 555 | `def test_pin_entry_normalizes_mixed_case_alphanumeric_pin(self):` |
| `apps/live_exam/tests/test_views.py` | 565 | `def test_pin_entry_accepts_legacy_shorter_pin(self):` |
| `apps/live_exam/tests/test_views.py` | 575 | `def test_pin_entry_resolves_unique_prefix_to_active_session(self):` |
| `apps/live_exam/tests/test_views.py` | 585 | `def test_pin_entry_resolves_ambiguous_glyphs_to_unique_session(self):` |
| `apps/live_exam/tests/test_views.py` | 595 | `def test_pin_entry_does_not_resolve_ambiguous_prefix(self):` |
| `apps/live_exam/tests/test_views.py` | 607 | `def test_join_page_redirects_prefix_to_canonical_full_pin(self):` |
| `apps/live_exam/tests/test_views.py` | 617 | `def test_pin_entry_redirects_to_join_page_for_prefilled_valid_pin(self):` |
| `apps/live_exam/tests/test_views.py` | 627 | `def test_pin_entry_redirects_to_join_page_for_valid_pin(self):` |
| `apps/live_exam/tests/test_views.py` | 633 | `def test_pin_entry_shows_error_for_unknown_pin(self):` |
| `apps/live_exam/tests/test_views.py` | 641 | `def test_join_enter_requires_nickname(self):` |
| `apps/live_exam/tests/test_views.py` | 651 | `def test_join_enter_success(self):` |
| `apps/live_exam/tests/test_views.py` | 668 | `def test_join_enter_assigns_random_avatar_and_accessory_when_not_provided(self):` |
| `apps/live_exam/tests/test_views.py` | 67 | `def _set_active_org(client, org):` |
| `apps/live_exam/tests/test_views.py` | 683 | `def test_join_enter_locked_session(self):` |
| `apps/live_exam/tests/test_views.py` | 696 | `def test_join_enter_rejects_duplicate_nickname_from_another_client(self):` |
| `apps/live_exam/tests/test_views.py` | 716 | `class LiveJoinRateLimitTest(TestCase):` |
| `apps/live_exam/tests/test_views.py` | 717 | `def setUp(self):` |
| `apps/live_exam/tests/test_views.py` | 739 | `def test_pin_entry_blocks_repeated_invalid_attempts(self):` |
| `apps/live_exam/tests/test_views.py` | 74 | `class LiveExamViewsImportTest(TestCase):` |
| `apps/live_exam/tests/test_views.py` | 752 | `def test_join_enter_blocks_after_rate_limit(self):` |
| `apps/live_exam/tests/test_views.py` | 770 | `class LiveStateAPITest(TestCase):` |
| `apps/live_exam/tests/test_views.py` | 773 | `def setUp(self):` |
| `apps/live_exam/tests/test_views.py` | 77 | `def test_all_views_importable(self):` |
| `apps/live_exam/tests/test_views.py` | 816 | `def _authenticate_player(self, client=None):` |
| `apps/live_exam/tests/test_views.py` | 832 | `def test_state_json_requires_player_token(self):` |
| `apps/live_exam/tests/test_views.py` | 839 | `def test_state_json_hides_question_until_published(self):` |
| `apps/live_exam/tests/test_views.py` | 853 | `def test_state_json_returns_published_question_for_authenticated_player(self):` |
| `apps/live_exam/tests/test_views.py` | 871 | `def test_state_json_includes_question_phase_timestamps(self):` |
| `apps/live_exam/tests/test_views.py` | 894 | `def test_state_json_includes_server_time_for_client_clock_sync(self):` |
| `apps/live_exam/tests/test_views.py` | 910 | `def test_state_json_uses_question_phase_override_when_present(self):` |
| `apps/live_exam/tests/test_views.py` | 945 | `def test_state_json_allows_host_session_access(self):` |
| `apps/live_exam/tests/test_views.py` | 961 | `def test_host_can_skip_question_intro_to_open_answers(self):` |
| `apps/live_exam/tests/test_views.py` | 990 | `def test_state_json_reveal_includes_correct_options(self):` |
| `apps/live_exam/transport.py` | 122 | `def build_lobby_state_payload(session, *, limit: int = 200) -> dict[str, Any]:` |
| `apps/live_exam/transport.py` | 134 | `def build_reaction_event_payload(*, player, reaction_key: str, emoji: str, created_at=None) -> dict[str, Any]:` |
| `apps/live_exam/transport.py` | 146 | `def build_answer_progress_payload(*, question_id: int, answered_count: int, total_players: int) -> dict[str, Any]:` |
| `apps/live_exam/transport.py` | 156 | `def build_question_payload(session, exam_question, *, idx: int, total: int):` |
| `apps/live_exam/transport.py` | 182 | `def build_question_phase_payload(` |
| `apps/live_exam/transport.py` | 210 | `def build_reveal_payload(` |
| `apps/live_exam/transport.py` | 249 | `def build_player_reveal_payload(` |
| `apps/live_exam/transport.py` | 291 | `def build_finished_payload(session, *, finished_at=None, limit: int = 50) -> dict[str, Any]:` |
| `apps/live_exam/transport.py` | 37 | `def get_public_base_url(request) -> str:` |
| `apps/live_exam/transport.py` | 50 | `def build_join_url(request, session) -> str:` |
| `apps/live_exam/transport.py` | 57 | `def broadcast(pin: str, payload: dict[str, Any], group_suffix: str) -> None:` |
| `apps/live_exam/transport.py` | 82 | `def broadcast_host(pin: str, payload: dict[str, Any]) -> None:` |
| `apps/live_exam/transport.py` | 87 | `def broadcast_players(pin: str, payload: dict[str, Any]) -> None:` |
| `apps/live_exam/transport.py` | 92 | `def broadcast_play(pin: str, payload: dict[str, Any]) -> None:` |
| `apps/live_exam/transport.py` | 98 | `def parse_answer_submission(data: dict[str, Any]) -> tuple[bool, Any]:` |
| `apps/live_exam/views/api.py` | 183 | `def live_answer_submit(request, pin):` |
| `apps/live_exam/views/api.py` | 57 | `def live_state_json(request, pin):` |
| `apps/live_exam/views/host/_shared.py` | 15 | `def _ensure_host_org_permission(request, exam_organization) -> None:` |
| `apps/live_exam/views/host/_shared.py` | 42 | `def _host_session_context(request, session: LiveSession, *, auto_fullscreen: str = "0") -> dict[str, object]:` |
| `apps/live_exam/views/host/game.py` | 191 | `def host_next_question(request, pin):` |
| `apps/live_exam/views/host/game.py` | 249 | `def host_skip_question_intro(request, pin):` |
| `apps/live_exam/views/host/game.py` | 308 | `def host_reveal(request, pin):` |
| `apps/live_exam/views/host/game.py` | 347 | `def host_finish(request, pin):` |
| `apps/live_exam/views/host/game.py` | 384 | `def host_toggle_lock(request, pin):` |
| `apps/live_exam/views/host/game.py` | 406 | `def host_remove_player(request, pin):` |
| `apps/live_exam/views/host/game.py` | 441 | `def host_update_settings(request, pin):` |
| `apps/live_exam/views/host/game.py` | 53 | `def host_start_game(request, pin):` |
| `apps/live_exam/views/host/session.py` | 104 | `def live_host_presentation(request, pin):` |
| `apps/live_exam/views/host/session.py` | 28 | `def live_create_session_by_slug(request, slug):` |
| `apps/live_exam/views/host/session.py` | 91 | `def live_host_lobby(request, pin):` |
| `apps/live_exam/views/player/_shared.py` | 121 | `def _nickname_conflict_message() -> str:` |
| `apps/live_exam/views/player/_shared.py` | 126 | `def _random_join_avatar_key() -> str:` |
| `apps/live_exam/views/player/_shared.py` | 130 | `def _random_join_accessory_key() -> str:` |
| `apps/live_exam/views/player/_shared.py` | 135 | `def _nickname_is_taken(` |
| `apps/live_exam/views/player/_shared.py` | 151 | `def _live_client_id_key(request) -> str:` |
| `apps/live_exam/views/player/_shared.py` | 155 | `def _ensure_live_client_cookie(request, response):` |
| `apps/live_exam/views/player/_shared.py` | 169 | `def _broadcast_lobby_state(session: LiveSession) -> None:` |
| `apps/live_exam/views/player/_shared.py` | 27 | `def _pin_entry_copy() -> dict[str, str]:` |
| `apps/live_exam/views/player/_shared.py` | 32 | `def _pin_entry_theme_key(pin_value: str, raw_theme: str \| None = None) -> str:` |
| `apps/live_exam/views/player/_shared.py` | 41 | `def _join_resume_copy(nickname: str) -> dict[str, str]:` |
| `apps/live_exam/views/player/_shared.py` | 50 | `def _normalize_pin(raw_pin: str \| None) -> str:` |
| `apps/live_exam/views/player/_shared.py` | 63 | `def _candidate_pin_variants(pin_value: str) -> tuple[str, ...]:` |
| `apps/live_exam/views/player/_shared.py` | 83 | `def _resolve_live_session(raw_pin: str \| None) -> tuple[str, LiveSession \| None]:` |
| `apps/live_exam/views/player/join.py` | 139 | `def live_join_page(request, pin):` |
| `apps/live_exam/views/player/join.py` | 162 | `def live_join_enter(request, pin):` |
| `apps/live_exam/views/player/join.py` | 306 | `def live_qr_png(request, pin):` |
| `apps/live_exam/views/player/join.py` | 61 | `def live_pin_entry(request):` |
| `apps/live_exam/views/player/wait.py` | 122 | `def live_wait_reaction(request, pin):` |
| `apps/live_exam/views/player/wait.py` | 181 | `def live_player_screen(request, pin):` |
| `apps/live_exam/views/player/wait.py` | 38 | `def live_wait_room(request, pin):` |
| `apps/live_exam/views/player/wait.py` | 64 | `def live_wait_profile_update(request, pin):` |
| `apps/live_exam/views/results.py` | 111 | `def _session_questions(exam: Exam, session: LiveSession) -> list[ExamQuestion]:` |
| `apps/live_exam/views/results.py` | 128 | `def _truncate_question_text(value: str \| None, limit: int) -> str:` |
| `apps/live_exam/views/results.py` | 136 | `def teacher_live_exam_results(request, slug):` |
| `apps/live_exam/views/results.py` | 168 | `def teacher_live_session_detail(request, slug, pin):` |
| `apps/live_exam/views/results.py` | 25 | `def _ensure_teacher_access(request, exam):` |
| `apps/live_exam/views/results.py` | 36 | `def _build_score_distribution(scores, bucket_limit=6):` |
| `apps/live_exam/views/results.py` | 61 | `def _resolve_exam_navigation(request, exam, *, default_section="my-exams"):` |
| `apps/live_exam/views/results.py` | 89 | `def _session_question_ids(session: LiveSession) -> list[int]:` |
| `apps/trial_exams/admin.py` | 101 | `def file_link(self, obj: TrialExamRequest) -> str:` |
| `apps/trial_exams/admin.py` | 114 | `def status_pill(self, obj: TrialExamRequest) -> str:` |
| `apps/trial_exams/admin.py` | 131 | `def reply_action(self, obj: TrialExamRequest) -> str:` |
| `apps/trial_exams/admin.py` | 158 | `def mark_as_handled(self, request, queryset):` |
| `apps/trial_exams/admin.py` | 20 | `class TrialExamRequestAdmin(admin.ModelAdmin):` |
| `apps/trial_exams/admin.py` | 79 | `def has_add_permission(self, request):` |
| `apps/trial_exams/admin.py` | 82 | `def has_delete_permission(self, request, obj=None):` |
| `apps/trial_exams/admin.py` | 87 | `def get_urls(self):` |
| `apps/trial_exams/admin_views.py` | 37 | `class TrialReplyForm(forms.Form):` |
| `apps/trial_exams/admin_views.py` | 58 | `def reply_to_trial_request(request: HttpRequest, pk: int) -> HttpResponse:` |
| `apps/trial_exams/apps.py` | 4 | `class TrialExamsConfig(AppConfig):` |
| `apps/trial_exams/forms.py` | 107 | `def clean_subject_name(self) -> str:` |
| `apps/trial_exams/forms.py` | 115 | `def clean_questions_file(self):` |
| `apps/trial_exams/forms.py` | 130 | `def clean_website(self) -> str:` |
| `apps/trial_exams/forms.py` | 33 | `def _max_upload_mb() -> int:` |
| `apps/trial_exams/forms.py` | 37 | `class TrialExamRequestForm(forms.ModelForm):` |
| `apps/trial_exams/forms.py` | 50 | `class Meta:` |
| `apps/trial_exams/forms.py` | 99 | `def clean_full_name(self) -> str:` |
| `apps/trial_exams/migrations/0001_initial.py` | 10 | `class Migration(migrations.Migration):` |
| `apps/trial_exams/models.py` | 131 | `class Meta:` |
| `apps/trial_exams/models.py` | 141 | `def __str__(self) -> str:` |
| `apps/trial_exams/models.py` | 145 | `def has_been_replied(self) -> bool:` |
| `apps/trial_exams/models.py` | 149 | `def reply_delivery_failed(self) -> bool:` |
| `apps/trial_exams/models.py` | 153 | `def reply_delivery_pending(self) -> bool:` |
| `apps/trial_exams/models.py` | 28 | `def trial_questions_upload_path(instance: "TrialExamRequest", filename: str) -> str:` |
| `apps/trial_exams/models.py` | 38 | `class TrialExamRequest(models.Model):` |
| `apps/trial_exams/services.py` | 111 | `def _notify_superadmins(request_obj: TrialExamRequest) -> None:` |
| `apps/trial_exams/services.py` | 141 | `def dispatch_trial_notifications(request_obj: TrialExamRequest) -> None:` |
| `apps/trial_exams/services.py` | 144 | `def _runner() -> None:` |
| `apps/trial_exams/services.py` | 164 | `def _send_reply_email(request_obj: TrialExamRequest, reply_body: str, reply_from: str) -> tuple[bool, str]:` |
| `apps/trial_exams/services.py` | 189 | `def send_reply_to_trial_request(` |
| `apps/trial_exams/services.py` | 231 | `def _runner() -> None:` |
| `apps/trial_exams/services.py` | 270 | `def create_trial_exam_request(*, form, request) -> TrialExamRequest:` |
| `apps/trial_exams/services.py` | 294 | `def _extract_client_ip(request) -> str \| None:` |
| `apps/trial_exams/services.py` | 45 | `def _resolve_notify_address() -> str:` |
| `apps/trial_exams/services.py` | 54 | `def _admin_links(request_obj: TrialExamRequest) -> tuple[str, str]:` |
| `apps/trial_exams/services.py` | 61 | `def _profile_detail_url(request_obj: TrialExamRequest) -> str:` |
| `apps/trial_exams/services.py` | 67 | `def _file_download_url(request_obj: TrialExamRequest) -> str:` |
| `apps/trial_exams/services.py` | 77 | `def _send_owner_notification(request_obj: TrialExamRequest) -> bool:` |
| `apps/trial_exams/tests/conftest.py` | 13 | `def create_user(django_user_model):` |
| `apps/trial_exams/tests/conftest.py` | 16 | `def _create_user(username="testuser", email="test@example.com", password="<test-value-masked>", **kwargs):` |
| `apps/trial_exams/tests/conftest.py` | 23 | `def pdf_upload():` |
| `apps/trial_exams/tests/conftest.py` | 26 | `def _make(name="questions.pdf", content=_MINIMAL_PDF, content_type="application/pdf"):` |
| `apps/trial_exams/tests/conftest.py` | 33 | `def valid_post_data():` |
| `apps/trial_exams/tests/test_forms.py` | 14 | `def _files(pdf):` |
| `apps/trial_exams/tests/test_forms.py` | 18 | `def test_valid_form(valid_post_data, pdf_upload):` |
| `apps/trial_exams/tests/test_forms.py` | 23 | `def test_missing_file_is_rejected(valid_post_data):` |
| `apps/trial_exams/tests/test_forms.py` | 29 | `def test_non_pdf_extension_is_rejected(valid_post_data):` |
| `apps/trial_exams/tests/test_forms.py` | 36 | `def test_fake_pdf_mime_is_rejected(valid_post_data):` |
| `apps/trial_exams/tests/test_forms.py` | 44 | `def test_honeypot_blocks_bots(valid_post_data, pdf_upload):` |
| `apps/trial_exams/tests/test_forms.py` | 50 | `def test_short_name_is_rejected(valid_post_data, pdf_upload):` |
| `apps/trial_exams/tests/test_forms.py` | 57 | `def test_short_subject_is_rejected(valid_post_data, pdf_upload):` |
| `apps/trial_exams/tests/test_forms.py` | 64 | `def test_link_in_name_is_rejected(valid_post_data, pdf_upload):` |
| `apps/trial_exams/tests/test_services.py` | 14 | `class _DummyRequest:` |
| `apps/trial_exams/tests/test_services.py` | 15 | `def __init__(self, user):` |
| `apps/trial_exams/tests/test_services.py` | 20 | `def _bound_form(valid_post_data, pdf):` |
| `apps/trial_exams/tests/test_services.py` | 26 | `def test_create_persists_and_randomises_filename(monkeypatch, create_user, valid_post_data, pdf_upload):` |
| `apps/trial_exams/tests/test_services.py` | 45 | `def test_send_reply_marks_added(monkeypatch, create_user, valid_post_data, pdf_upload):` |
| `apps/trial_exams/tests/test_services.py` | 70 | `def test_send_reply_rejects_unknown_inbox(monkeypatch, create_user, valid_post_data, pdf_upload):` |
| `apps/trial_exams/tests/test_views.py` | 15 | `def test_get_requires_login(client):` |
| `apps/trial_exams/tests/test_views.py` | 21 | `def test_get_renders_for_logged_in_user(client, create_user):` |
| `apps/trial_exams/tests/test_views.py` | 30 | `def test_post_creates_request_and_redirects(monkeypatch, client, create_user, valid_post_data, pdf_upload):` |
| `apps/trial_exams/tests/test_views.py` | 45 | `def test_post_without_file_is_invalid(monkeypatch, client, create_user, valid_post_data):` |
| `apps/trial_exams/views.py` | 40 | `def _client_ip(request: HttpRequest) -> str:` |
| `apps/trial_exams/views.py` | 47 | `def _initial_from_user(request: HttpRequest) -> dict:` |
| `apps/trial_exams/views.py` | 56 | `def trial_exam_request_page(request: HttpRequest) -> HttpResponse:` |
