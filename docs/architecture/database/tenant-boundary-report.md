# Tenant Boundary Report

## Tenant Mexanizmi

- Request səviyyəsində tenant `apps/organizations/middleware.py — OrganizationMiddleware` ilə həll olunur.
- Middleware `request.organization`, `request.org_memberships`, `request.org_permissions` qurur.
- PostgreSQL RLS context `core/rls.py` vasitəsilə `app.current_org_id`, `app.current_user_id`, `app.bypass_rls` kimi set edilir.
- `core/rls.py` qeyri-PostgreSQL backend-lərdə no-op davranır; sqlite lokal yoxlamalarda tenant qorunması yalnız application-level filtr və test davranışı ilə təsdiqlənir.

## RLS Migration Mənbələri

| Migration | RLS policy tətbiq edilən table-lar |
| --- | --- |
| apps/organizations/migrations/0003_rls_policies.py | assignments_assignment, assignments_submission, courses_course, courses_coursegroup, courses_courseinstructor, courses_coursemembership, courses_courseresource, courses_coursetopic, exams_exam, exams_examattempt, exams_studentgroup, labs_lab, live_exam_liveanswer, live_exam_liveplayer, live_exam_livesession, notifications_studentorganizationrequest, organizations_academicperiod, organizations_membership, organizations_orgunit, organizations_role |
| apps/organizations/migrations/0004_expand_rls_scope.py | assignments_assignment_assigned_students, courses_coursegroup_members, exams_exam_allowed_groups, exams_exam_allowed_users, exams_examanswer, exams_examanswer_selected_options, exams_examanswerfile, exams_examquestion, exams_examquestionoption, exams_proctoringlog, exams_questionblock, exams_studentgroup_students, exams_studentgroup_teachers, notifications_inappnotification |
| apps/organizations/migrations/0005_notification_org_fk_rls.py | notifications_inappnotification |
| apps/organizations/migrations/0007_rls_question_bank_appeals.py | appeals_appeal, appeals_appealitem, appeals_scoreadjustment, exams_bankquestion, exams_bankquestionoption, exams_examlanguagevariant, exams_questionbank |
| apps/organizations/migrations/0012_rls_text_extraction_job.py | exams_textextractionjob |
| apps/organizations/migrations/0015_rls_final_center.py | exams_examroom, exams_examroomsession, exams_finalexamticket |
| apps/organizations/migrations/0016_rls_exam_room_computer.py | exams_examroomcomputer |
| apps/registrar/migrations/0002_rls_policies.py | registrar_curriculum, registrar_curriculumsubject, registrar_program, registrar_subject |
| apps/registrar/migrations/0004_rls_enrollment.py | registrar_courseoffering, registrar_enrollment, registrar_groupelectivechoice, registrar_studentacademicrecord |
| apps/registrar/migrations/0007_rls_gradebook.py | registrar_assessmentscheme, registrar_componentscore, registrar_gradecomponent |
| apps/registrar/migrations/0009_rls_journal.py | registrar_lesson, registrar_lessonmark |
| apps/registrar/migrations/0011_rls_scheduleslot.py | registrar_scheduleslot |
| apps/registrar/migrations/0013_rls_finals.py | registrar_finalgrade, registrar_resitrecord |
| apps/registrar/migrations/0016_rls_assessment_components.py | registrar_assessmentcomponent, registrar_componentscore |
| apps/registrar/migrations/0020_rls_rubrics.py | registrar_criterionscore, registrar_rubric, registrar_rubriccriterion |


## Table Üzrə Tenant Ownership

| Table | Model | Scope | RLS | Ownership path |
| --- | --- | --- | --- | --- |
| auth_group | auth.Group | django-system/global | no/not detected |  |
| auth_group_permissions | auth.Group_permissions | django-system/global | no/not detected |  |
| auth_permission | auth.Permission | django-system/global | no/not detected |  |
| auth_user | auth.User | django-system/global | no/not detected |  |
| django_content_type | contenttypes.ContentType | django-system/global | no/not detected |  |
| django_session | sessions.Session | django-system/global | no/not detected |  |
| blog_category | blog.Category | global-or-unclear | no/not detected |  |
| blog_subscriber | blog.Subscriber | global-or-unclear | no/not detected |  |
| exams_aiconfiguration | exams.AIConfiguration | global-or-unclear | no/not detected |  |
| organizations_country | organizations.Country | global/master-data | no/not detected |  |
| organizations_institution | organizations.Institution | global/master-data | no/not detected |  |
| accounts_userprofile | accounts.UserProfile | tenant-direct | no/not detected | accounts.UserProfile.organization -> organizations.Organization |
| ai_assistant_aiassistantlog | ai_assistant.AIAssistantLog | tenant-direct | no/not detected | ai_assistant.AIAssistantLog.organization -> organizations.Organization |
| appeals_appeal | appeals.Appeal | tenant-direct | yes | appeals.Appeal.organization -> organizations.Organization |
| audit_auditlog | audit.AuditLog | tenant-direct | no/not detected | audit.AuditLog.organization -> organizations.Organization |
| courses_course | courses.Course | tenant-direct | yes | courses.Course.organization -> organizations.Organization |
| exams_exam | exams.Exam | tenant-direct | yes | exams.Exam.organization -> organizations.Organization |
| exams_examroom | exams.ExamRoom | tenant-direct | yes | exams.ExamRoom.organization -> organizations.Organization |
| exams_examroomcomputer | exams.ExamRoomComputer | tenant-direct | yes | exams.ExamRoomComputer.organization -> organizations.Organization |
| exams_examroomsession | exams.ExamRoomSession | tenant-direct | yes | exams.ExamRoomSession.organization -> organizations.Organization |
| exams_finalexamticket | exams.FinalExamTicket | tenant-direct | yes | exams.FinalExamTicket.organization -> organizations.Organization |
| exams_questionbank | exams.QuestionBank | tenant-direct | yes | exams.QuestionBank.organization -> organizations.Organization |
| exams_questionsubmission | exams.QuestionSubmission | tenant-direct | no/not detected | exams.QuestionSubmission.organization -> organizations.Organization |
| exams_studentgroup | exams.StudentGroup | tenant-direct | yes | exams.StudentGroup.organization -> organizations.Organization |
| exams_supervisionincident | exams.SupervisionIncident | tenant-direct | no/not detected | exams.SupervisionIncident.organization -> organizations.Organization |
| exams_textextractionjob | exams.TextExtractionJob | tenant-direct | yes | exams.TextExtractionJob.organization -> organizations.Organization |
| notifications_inappnotification | notifications.InAppNotification | tenant-direct | yes | notifications.InAppNotification.organization -> organizations.Organization |
| notifications_studentorganizationrequest | notifications.StudentOrganizationRequest | tenant-direct | yes | notifications.StudentOrganizationRequest.organization -> organizations.Organization |
| organizations_academicperiod | organizations.AcademicPeriod | tenant-direct | yes | organizations.AcademicPeriod.organization -> organizations.Organization |
| organizations_membership | organizations.Membership | tenant-direct | yes | organizations.Membership.organization -> organizations.Organization |
| organizations_orgunit | organizations.OrgUnit | tenant-direct | yes | organizations.OrgUnit.organization -> organizations.Organization |
| organizations_role | organizations.Role | tenant-direct | yes | organizations.Role.organization -> organizations.Organization |
| registrar_assessmentcomponent | registrar.AssessmentComponent | tenant-direct | yes | registrar.AssessmentComponent.organization -> organizations.Organization |
| registrar_assessmentscheme | registrar.AssessmentScheme | tenant-direct | yes | registrar.AssessmentScheme.organization -> organizations.Organization |
| registrar_componentscore | registrar.ComponentScore | tenant-direct | yes | registrar.ComponentScore.organization -> organizations.Organization |
| registrar_courseoffering | registrar.CourseOffering | tenant-direct | yes | registrar.CourseOffering.organization -> organizations.Organization |
| registrar_criterionscore | registrar.CriterionScore | tenant-direct | yes | registrar.CriterionScore.organization -> organizations.Organization |
| registrar_curriculum | registrar.Curriculum | tenant-direct | yes | registrar.Curriculum.organization -> organizations.Organization |
| registrar_curriculumsubject | registrar.CurriculumSubject | tenant-direct | yes | registrar.CurriculumSubject.organization -> organizations.Organization |
| registrar_enrollment | registrar.Enrollment | tenant-direct | yes | registrar.Enrollment.organization -> organizations.Organization |
| registrar_finalgrade | registrar.FinalGrade | tenant-direct | yes | registrar.FinalGrade.organization -> organizations.Organization |
| registrar_groupelectivechoice | registrar.GroupElectiveChoice | tenant-direct | yes | registrar.GroupElectiveChoice.organization -> organizations.Organization |
| registrar_lesson | registrar.Lesson | tenant-direct | yes | registrar.Lesson.organization -> organizations.Organization |
| registrar_lessonmark | registrar.LessonMark | tenant-direct | yes | registrar.LessonMark.organization -> organizations.Organization |
| registrar_program | registrar.Program | tenant-direct | yes | registrar.Program.organization -> organizations.Organization |
| registrar_resitrecord | registrar.ResitRecord | tenant-direct | yes | registrar.ResitRecord.organization -> organizations.Organization |
| registrar_rubric | registrar.Rubric | tenant-direct | yes | registrar.Rubric.organization -> organizations.Organization |
| registrar_rubriccriterion | registrar.RubricCriterion | tenant-direct | yes | registrar.RubricCriterion.organization -> organizations.Organization |
| registrar_scheduleslot | registrar.ScheduleSlot | tenant-direct | yes | registrar.ScheduleSlot.organization -> organizations.Organization |
| registrar_studentacademicrecord | registrar.StudentAcademicRecord | tenant-direct | yes | registrar.StudentAcademicRecord.organization -> organizations.Organization |
| registrar_subject | registrar.Subject | tenant-direct | yes | registrar.Subject.organization -> organizations.Organization |
| appeals_appealitem | appeals.AppealItem | tenant-indirect | yes | appeals.AppealItem.appeal -> appeals.Appeal → appeals.Appeal.organization -> organizations.Organization |
| appeals_scoreadjustment | appeals.ScoreAdjustment | tenant-indirect | yes | appeals.ScoreAdjustment.appeal_item -> appeals.AppealItem → appeals.AppealItem.appeal -> appeals.Appeal → appeals.Appeal.organization -> organizations.Organization |
| assignments_assignment | assignments.Assignment | tenant-indirect | yes | assignments.Assignment.course -> courses.Course → courses.Course.organization -> organizations.Organization |
| assignments_assignment_assigned_students | assignments.Assignment_assigned_students | tenant-indirect | yes | assignments.Assignment_assigned_students.assignment -> assignments.Assignment → assignments.Assignment.course -> courses.Course → courses.Course.organization -> organizations.Organization |
| assignments_submission | assignments.Submission | tenant-indirect | yes | assignments.Submission.assignment -> assignments.Assignment → assignments.Assignment.course -> courses.Course → courses.Course.organization -> organizations.Organization |
| courses_coursegroup | courses.CourseGroup | tenant-indirect | yes | courses.CourseGroup.course -> courses.Course → courses.Course.organization -> organizations.Organization |
| courses_coursegroup_members | courses.CourseGroup_members | tenant-indirect | yes | courses.CourseGroup_members.coursegroup -> courses.CourseGroup → courses.CourseGroup.course -> courses.Course → courses.Course.organization -> organizations.Organization |
| courses_courseinstructor | courses.CourseInstructor | tenant-indirect | yes | courses.CourseInstructor.course -> courses.Course → courses.Course.organization -> organizations.Organization |
| courses_coursemembership | courses.CourseMembership | tenant-indirect | yes | courses.CourseMembership.course -> courses.Course → courses.Course.organization -> organizations.Organization |
| courses_courseresource | courses.CourseResource | tenant-indirect | yes | courses.CourseResource.course -> courses.Course → courses.Course.organization -> organizations.Organization |
| courses_coursetopic | courses.CourseTopic | tenant-indirect | yes | courses.CourseTopic.course -> courses.Course → courses.Course.organization -> organizations.Organization |
| exams_bankquestion | exams.BankQuestion | tenant-indirect | yes | exams.BankQuestion.bank -> exams.QuestionBank → exams.QuestionBank.organization -> organizations.Organization |
| exams_bankquestionoption | exams.BankQuestionOption | tenant-indirect | yes | exams.BankQuestionOption.question -> exams.BankQuestion → exams.BankQuestion.bank -> exams.QuestionBank → exams.QuestionBank.organization -> organizations.Organization |
| exams_codingexamquestion | exams.CodingExamQuestion | tenant-indirect | no/not detected | exams.CodingExamQuestion.question -> exams.ExamQuestion → exams.ExamQuestion.exam -> exams.Exam → exams.Exam.organization -> organizations.Organization |
| exams_codingfile | exams.CodingFile | tenant-indirect | no/not detected | exams.CodingFile.submission -> exams.CodingSubmission → exams.CodingSubmission.exam -> exams.Exam → exams.Exam.organization -> organizations.Organization |
| exams_codingsubmission | exams.CodingSubmission | tenant-indirect | no/not detected | exams.CodingSubmission.exam -> exams.Exam → exams.Exam.organization -> organizations.Organization |
| exams_codingtestcase | exams.CodingTestCase | tenant-indirect | no/not detected | exams.CodingTestCase.coding_question -> exams.CodingExamQuestion → exams.CodingExamQuestion.question -> exams.ExamQuestion → exams.ExamQuestion.exam -> exams.Exam → exams.Exam.organization -> organizations.Organization |
| exams_exam_allowed_groups | exams.Exam_allowed_groups | tenant-indirect | yes | exams.Exam_allowed_groups.exam -> exams.Exam → exams.Exam.organization -> organizations.Organization |
| exams_exam_allowed_users | exams.Exam_allowed_users | tenant-indirect | yes | exams.Exam_allowed_users.exam -> exams.Exam → exams.Exam.organization -> organizations.Organization |
| exams_examanswer | exams.ExamAnswer | tenant-indirect | yes | exams.ExamAnswer.attempt -> exams.ExamAttempt → exams.ExamAttempt.exam -> exams.Exam → exams.Exam.organization -> organizations.Organization |
| exams_examanswer_selected_options | exams.ExamAnswer_selected_options | tenant-indirect | yes | exams.ExamAnswer_selected_options.examanswer -> exams.ExamAnswer → exams.ExamAnswer.attempt -> exams.ExamAttempt → exams.ExamAttempt.exam -> exams.Exam → exams.Exam.organization -> organizations.Organization |
| exams_examanswerfile | exams.ExamAnswerFile | tenant-indirect | yes | exams.ExamAnswerFile.answer -> exams.ExamAnswer → exams.ExamAnswer.attempt -> exams.ExamAttempt → exams.ExamAttempt.exam -> exams.Exam → exams.Exam.organization -> organizations.Organization |
| exams_examattempt | exams.ExamAttempt | tenant-indirect | yes | exams.ExamAttempt.exam -> exams.Exam → exams.Exam.organization -> organizations.Organization |
| exams_examlanguagevariant | exams.ExamLanguageVariant | tenant-indirect | yes | exams.ExamLanguageVariant.exam -> exams.Exam → exams.Exam.organization -> organizations.Organization |
| exams_examquestion | exams.ExamQuestion | tenant-indirect | yes | exams.ExamQuestion.exam -> exams.Exam → exams.Exam.organization -> organizations.Organization |
| exams_examquestionoption | exams.ExamQuestionOption | tenant-indirect | yes | exams.ExamQuestionOption.question -> exams.ExamQuestion → exams.ExamQuestion.exam -> exams.Exam → exams.Exam.organization -> organizations.Organization |
| exams_examroom_invigilators | exams.ExamRoom_invigilators | tenant-indirect | no/not detected | exams.ExamRoom_invigilators.examroom -> exams.ExamRoom → exams.ExamRoom.organization -> organizations.Organization |
| exams_examroomsession_staff | exams.ExamRoomSession_staff | tenant-indirect | no/not detected | exams.ExamRoomSession_staff.examroomsession -> exams.ExamRoomSession → exams.ExamRoomSession.organization -> organizations.Organization |
| exams_examstudentpin | exams.ExamStudentPin | tenant-indirect | no/not detected | exams.ExamStudentPin.exam -> exams.Exam → exams.Exam.organization -> organizations.Organization |
| exams_examsupervisionconfig | exams.ExamSupervisionConfig | tenant-indirect | no/not detected | exams.ExamSupervisionConfig.exam -> exams.Exam → exams.Exam.organization -> organizations.Organization |
| exams_proctoringlog | exams.ProctoringLog | tenant-indirect | yes | exams.ProctoringLog.exam_attempt -> exams.ExamAttempt → exams.ExamAttempt.exam -> exams.Exam → exams.Exam.organization -> organizations.Organization |
| exams_questionblock | exams.QuestionBlock | tenant-indirect | yes | exams.QuestionBlock.exam -> exams.Exam → exams.Exam.organization -> organizations.Organization |
| exams_studentexamattemptgrant | exams.StudentExamAttemptGrant | tenant-indirect | no/not detected | exams.StudentExamAttemptGrant.exam -> exams.Exam → exams.Exam.organization -> organizations.Organization |
| exams_studentgroup_students | exams.StudentGroup_students | tenant-indirect | yes | exams.StudentGroup_students.studentgroup -> exams.StudentGroup → exams.StudentGroup.organization -> organizations.Organization |
| exams_studentgroup_subjects | exams.StudentGroup_subjects | tenant-indirect | no/not detected | exams.StudentGroup_subjects.studentgroup -> exams.StudentGroup → exams.StudentGroup.organization -> organizations.Organization |
| exams_studentgroup_teachers | exams.StudentGroup_teachers | tenant-indirect | yes | exams.StudentGroup_teachers.studentgroup -> exams.StudentGroup → exams.StudentGroup.organization -> organizations.Organization |
| labs_lab | labs.Lab | tenant-indirect | yes | labs.Lab.course -> courses.Course → courses.Course.organization -> organizations.Organization |
| labs_lab_allowed_students | labs.Lab_allowed_students | tenant-indirect | no/not detected | labs.Lab_allowed_students.lab -> labs.Lab → labs.Lab.course -> courses.Course → courses.Course.organization -> organizations.Organization |
| labs_labanswer | labs.LabAnswer | tenant-indirect | no/not detected | labs.LabAnswer.lab -> labs.Lab → labs.Lab.course -> courses.Course → courses.Course.organization -> organizations.Organization |
| labs_labassignment | labs.LabAssignment | tenant-indirect | no/not detected | labs.LabAssignment.lab -> labs.Lab → labs.Lab.course -> courses.Course → courses.Course.organization -> organizations.Organization |
| labs_labassignment_assigned_questions | labs.LabAssignment_assigned_questions | tenant-indirect | no/not detected | labs.LabAssignment_assigned_questions.labassignment -> labs.LabAssignment → labs.LabAssignment.lab -> labs.Lab → labs.Lab.course -> courses.Course → courses.Course.organization -> organizations.Organization |
| labs_labblock | labs.LabBlock | tenant-indirect | no/not detected | labs.LabBlock.lab -> labs.Lab → labs.Lab.course -> courses.Course → courses.Course.organization -> organizations.Organization |
| labs_labquestion | labs.LabQuestion | tenant-indirect | no/not detected | labs.LabQuestion.block -> labs.LabBlock → labs.LabBlock.lab -> labs.Lab → labs.Lab.course -> courses.Course → courses.Course.organization -> organizations.Organization |
| labs_labsubmission | labs.LabSubmission | tenant-indirect | no/not detected | labs.LabSubmission.assignment -> labs.LabAssignment → labs.LabAssignment.lab -> labs.Lab → labs.Lab.course -> courses.Course → courses.Course.organization -> organizations.Organization |
| live_exam_liveanswer | live_exam.LiveAnswer | tenant-indirect | yes | live_exam.LiveAnswer.session -> live_exam.LiveSession → live_exam.LiveSession.exam -> exams.Exam → exams.Exam.organization -> organizations.Organization |
| live_exam_liveplayer | live_exam.LivePlayer | tenant-indirect | yes | live_exam.LivePlayer.session -> live_exam.LiveSession → live_exam.LiveSession.exam -> exams.Exam → exams.Exam.organization -> organizations.Organization |
| live_exam_livesession | live_exam.LiveSession | tenant-indirect | yes | live_exam.LiveSession.exam -> exams.Exam → exams.Exam.organization -> organizations.Organization |
| projects_project | projects.Project | tenant-indirect | no/not detected | projects.Project.course -> courses.Course → courses.Course.organization -> organizations.Organization |
| projects_project_assigned_students | projects.Project_assigned_students | tenant-indirect | no/not detected | projects.Project_assigned_students.project -> projects.Project → projects.Project.course -> courses.Course → courses.Course.organization -> organizations.Organization |
| projects_projectsubmission | projects.ProjectSubmission | tenant-indirect | no/not detected | projects.ProjectSubmission.project -> projects.Project → projects.Project.course -> courses.Course → courses.Course.organization -> organizations.Organization |
| organizations_organization | organizations.Organization | tenant-root | no/not detected | organizations.Organization |
| accounts_emailotp | accounts.EmailOTP | user-owned/no-direct-org | no/not detected | accounts.EmailOTP.user -> auth.User |
| django_admin_log | admin.LogEntry | user-owned/no-direct-org | no/not detected | admin.LogEntry.user -> auth.User |
| assignments_notification | assignments.Notification | user-owned/no-direct-org | no/not detected | assignments.Notification.user -> auth.User |
| auth_user_groups | auth.User_groups | user-owned/no-direct-org | no/not detected | auth.User_groups.user -> auth.User |
| auth_user_user_permissions | auth.User_user_permissions | user-owned/no-direct-org | no/not detected | auth.User_user_permissions.user -> auth.User |
| blog_comment | blog.Comment | user-owned/no-direct-org | no/not detected | blog.Comment.user -> auth.User |
| blog_post | blog.Post | user-owned/no-direct-org | no/not detected | blog.Post.author -> auth.User |
| blog_postapprovallog | blog.PostApprovalLog | user-owned/no-direct-org | no/not detected | blog.PostApprovalLog.reviewer -> auth.User |
| blog_question | blog.Question | user-owned/no-direct-org | no/not detected | blog.Question.author -> auth.User |
| blog_question_visible_users | blog.Question_visible_users | user-owned/no-direct-org | no/not detected | blog.Question_visible_users.user -> auth.User |
| contact_contactmessage | contact.ContactMessage | user-owned/no-direct-org | no/not detected | contact.ContactMessage.reply_sent_by -> auth.User |
| trial_exams_trialexamrequest | trial_exams.TrialExamRequest | user-owned/no-direct-org | no/not detected | trial_exams.TrialExamRequest.user -> auth.User |


## Əsas Ownership Zəncirləri

- `organizations.Organization` → `organizations.OrgUnit` → `organizations.Membership.scope_unit`
- `organizations.Organization` → `courses.Course` → `assignments.Assignment` → `assignments.Submission`
- `organizations.Organization` → `courses.Course` → `projects.Project` / `labs.Lab`
- `organizations.Organization` → `exams.Exam` → `exams.ExamAttempt` → `exams.ExamAnswer` / `exams.CodingSubmission`
- `organizations.Organization` → `exams.ExamRoom` → `exams.ExamRoomSession` → `exams.FinalExamTicket`
- `organizations.Organization` → `registrar.Program` / `Subject` / `Curriculum` → `CourseOffering` → `Enrollment` / journal models
- `organizations.Organization` → `appeals.Appeal` → `AppealItem` → `ScoreAdjustment`

## Qeydlər

RLS statusu migration source scan nəticəsidir. `no/not detected` demək backend-də heç bir qoruma yoxdur demək deyil; həmin table application-level scoping və ya user-owned qayda ilə qoruna bilər. Risk sənədində yalnız memarlıq baxımından yoxlanmalı boşluqlar ayrıca qeyd olunub.
