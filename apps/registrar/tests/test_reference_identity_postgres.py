"""PostgreSQL raw-write conformance for registrar reference identity."""

import uuid

from django.db import IntegrityError, connection, transaction

import pytest

from apps.registrar import transfer
from apps.registrar.models import (
    ComponentScore,
    CourseOffering,
    Curriculum,
    Program,
    StudentAcademicRecord,
)
from core.rls import bypass_rls

from .test_reference_identity import ReferenceIdentityValidationTests

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(connection.vendor != "postgresql", reason="PostgreSQL triggers are required."),
]


class PostgresReferenceIdentityTests(ReferenceIdentityValidationTests):
    def _rejects(self, operation):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                operation()

    def test_raw_always_immutable_reference_matrix_is_rejected(self):
        with bypass_rls():
            alternatives = self._alternatives()
            rows = self._identity_rows(alternatives)
            cases = (
                lambda: type(self.enrollment)
                .objects.filter(pk=self.enrollment.pk)
                .update(offering=alternatives["offering"]),
                lambda: type(rows["lesson"])
                .objects.filter(pk=rows["lesson"].pk)
                .update(offering=alternatives["offering"]),
                lambda: type(rows["mark"]).objects.filter(pk=rows["mark"].pk).update(lesson=rows["second_lesson"]),
                lambda: type(rows["mark"])
                .objects.filter(pk=rows["mark"].pk)
                .update(enrollment=alternatives["enrollment"]),
                lambda: type(rows["scheme"])
                .objects.filter(pk=rows["scheme"].pk)
                .update(offering=alternatives["offering"]),
                lambda: type(rows["slot"]).objects.filter(pk=rows["slot"].pk).update(offering=alternatives["offering"]),
                lambda: type(rows["component_score"])
                .objects.filter(pk=rows["component_score"].pk)
                .update(component=rows["second_component"]),
                lambda: type(rows["component_score"])
                .objects.filter(pk=rows["component_score"].pk)
                .update(enrollment=alternatives["enrollment"]),
                lambda: type(rows["criterion_score"])
                .objects.filter(pk=rows["criterion_score"].pk)
                .update(component=rows["second_component"]),
                lambda: type(rows["criterion_score"])
                .objects.filter(pk=rows["criterion_score"].pk)
                .update(criterion=rows["second_criterion"]),
                lambda: type(rows["criterion_score"])
                .objects.filter(pk=rows["criterion_score"].pk)
                .update(enrollment=alternatives["enrollment"]),
                lambda: type(rows["topic"])
                .objects.filter(pk=rows["topic"].pk)
                .update(offering=alternatives["offering"]),
                lambda: type(rows["selfwork_mark"])
                .objects.filter(pk=rows["selfwork_mark"].pk)
                .update(topic=rows["second_topic"]),
                lambda: type(rows["selfwork_mark"])
                .objects.filter(pk=rows["selfwork_mark"].pk)
                .update(enrollment=alternatives["enrollment"]),
                lambda: type(rows["coursework"])
                .objects.filter(pk=rows["coursework"].pk)
                .update(enrollment=alternatives["enrollment"]),
                lambda: type(rows["final_grade"])
                .objects.filter(pk=rows["final_grade"].pk)
                .update(enrollment=alternatives["enrollment"]),
                lambda: type(rows["resit"])
                .objects.filter(pk=rows["resit"].pk)
                .update(enrollment=alternatives["enrollment"]),
                lambda: type(rows["second_criterion"])
                .objects.filter(pk=rows["second_criterion"].pk)
                .update(rubric=alternatives["rubric"]),
            )
            for index, operation in enumerate(cases):
                with self.subTest(case=index):
                    self._rejects(operation)

    def test_raw_conditional_parent_identity_matrix(self):
        with bypass_rls():
            alternatives = self._alternatives()
            ComponentScore.objects.create(
                organization=self.org,
                component=self.component,
                enrollment=self.enrollment,
                score=0,
                entered_by=self.teacher,
            )
            second_program = Program.objects.create(
                organization=self.org,
                code="IDENTITY-PG-P2",
                name="Identity PG second program",
            )
            protected = (
                lambda: CourseOffering.objects.filter(pk=self.offering.pk).update(subject=alternatives["subject"]),
                lambda: CourseOffering.objects.filter(pk=self.offering.pk).update(period=alternatives["period"]),
                lambda: CourseOffering.objects.filter(pk=self.offering.pk).update(group=alternatives["group"]),
                lambda: type(self.component)
                .objects.filter(pk=self.component.pk)
                .update(offering=alternatives["offering"]),
                lambda: type(self.component).objects.filter(pk=self.component.pk).update(rubric=alternatives["rubric"]),
                lambda: Curriculum.objects.filter(pk=self.curriculum.pk).update(program=second_program),
            )
            for index, operation in enumerate(protected):
                with self.subTest(case=index):
                    self._rejects(operation)

            self.assertEqual(
                type(alternatives["component"])
                .objects.filter(pk=alternatives["component"].pk)
                .update(rubric=self.rubric),
                1,
            )
            empty_curriculum = Curriculum.objects.create(
                organization=self.org,
                program=self.program,
                admission_year=2031,
            )
            self.assertEqual(
                Curriculum.objects.filter(pk=empty_curriculum.pk).update(program=second_program),
                1,
            )

    def test_raw_group_update_rejects_missing_and_mismatched_bindings(self):
        with bypass_rls():
            alternatives = self._alternatives()
            self._rejects(
                lambda: StudentAcademicRecord.objects.filter(pk=self.record.pk).update(group=alternatives["group"])
            )

            valid = {
                "evidence": str(uuid.uuid4()),
                "record": str(self.record.pk),
                "old": str(self.group.pk),
                "new": str(alternatives["group"].pk),
                "actor": str(self.owner.pk),
                "txid": None,
            }
            variants = (
                {},
                {"record": str(uuid.uuid4())},
                {"old": str(uuid.uuid4())},
                {"new": str(uuid.uuid4())},
                {"actor": "not-an-actor"},
                {"txid": "0"},
            )
            for override in variants:
                values = {**valid, **override}

                def forged(values=values):
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "SELECT set_config('app.registrar_group_transfer_evidence', %s, true), "
                            "set_config('app.registrar_group_transfer_record', %s, true), "
                            "set_config('app.registrar_group_transfer_old_group', %s, true), "
                            "set_config('app.registrar_group_transfer_new_group', %s, true), "
                            "set_config('app.registrar_group_transfer_actor', %s, true), "
                            "set_config('app.registrar_group_transfer_txid', "
                            "COALESCE(%s, pg_current_xact_id()::text), true)",
                            [
                                values["evidence"],
                                values["record"],
                                values["old"],
                                values["new"],
                                values["actor"],
                                values["txid"],
                            ],
                        )
                    StudentAcademicRecord.objects.filter(pk=self.record.pk).update(group=alternatives["group"])

                with self.subTest(binding=override):
                    self._rejects(forged)

    def test_sanctioned_transfer_clears_all_transaction_bindings(self):
        with bypass_rls():
            alternatives = self._alternatives()
            transfer.transfer_student_group(
                record=self.record,
                new_group=alternatives["group"],
                period=self.period,
                by_user=self.owner,
            )
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT current_setting(name, true) FROM unnest(ARRAY["
                    "'app.registrar_group_transfer_evidence', "
                    "'app.registrar_group_transfer_record', "
                    "'app.registrar_group_transfer_old_group', "
                    "'app.registrar_group_transfer_new_group', "
                    "'app.registrar_group_transfer_actor', "
                    "'app.registrar_group_transfer_txid']) AS name"
                )
                values = [row[0] for row in cursor.fetchall()]
            self.assertEqual(values, ["", "", "", "", "", ""])

    def test_restricted_role_raw_group_update_is_rejected(self):
        with bypass_rls():
            alternatives = self._alternatives()
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.bypass_rls', 'off', true)")
            cursor.execute("SELECT set_config('app.current_org_id', %s, true)", [str(self.org.pk)])
            cursor.execute("SELECT set_config('app.current_user_id', %s, true)", [str(self.owner.pk)])
            cursor.execute("SET LOCAL ROLE rls_app_role")
        try:

            def exact_forgery():
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT set_config('app.registrar_group_transfer_evidence', %s, true), "
                        "set_config('app.registrar_group_transfer_record', %s, true), "
                        "set_config('app.registrar_group_transfer_old_group', %s, true), "
                        "set_config('app.registrar_group_transfer_new_group', %s, true), "
                        "set_config('app.registrar_group_transfer_actor', %s, true), "
                        "set_config('app.registrar_group_transfer_txid', "
                        "pg_current_xact_id()::text, true)",
                        [
                            str(uuid.uuid4()),
                            str(self.record.pk),
                            str(self.group.pk),
                            str(alternatives["group"].pk),
                            str(self.owner.pk),
                        ],
                    )
                StudentAcademicRecord.objects.filter(pk=self.record.pk).update(group=alternatives["group"])

            self._rejects(exact_forgery)
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")
                cursor.execute("SELECT set_config('app.bypass_rls', 'on', true)")

    def test_restricted_direct_transition_without_finalize_cannot_commit(self):
        with bypass_rls():
            alternatives = self._alternatives()
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.bypass_rls', 'off', true)")
            cursor.execute("SELECT set_config('app.current_org_id', %s, true)", [str(self.org.pk)])
            cursor.execute("SELECT set_config('app.current_user_id', %s, true)", [str(self.owner.pk)])
            cursor.execute("SET LOCAL ROLE rls_app_role")
        try:

            def pending_only():
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT public.registrar_begin_student_group_transfer(%s, %s, %s, %s, %s, %s)",
                        [
                            str(uuid.uuid4()),
                            str(self.record.pk),
                            str(self.group.pk),
                            str(alternatives["group"].pk),
                            str(self.period.pk),
                            self.owner.pk,
                        ],
                    )
                    cursor.execute("SET CONSTRAINTS registrar_group_transfer_finalize_guard IMMEDIATE")

            self._rejects(pending_only)
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")
                cursor.execute("SELECT set_config('app.bypass_rls', 'on', true)")
        self.record.refresh_from_db()
        self.assertEqual(self.record.group_id, self.group.pk)

    def test_restricted_begin_rejects_wrong_session_actor_and_tenant(self):
        with bypass_rls():
            alternatives = self._alternatives()
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.bypass_rls', 'off', true)")
            cursor.execute("SET LOCAL ROLE rls_app_role")
        try:

            def begin(*, session_org, session_actor, target_actor):
                with connection.cursor() as cursor:
                    cursor.execute("SELECT set_config('app.current_org_id', %s, true)", [session_org])
                    cursor.execute("SELECT set_config('app.current_user_id', %s, true)", [session_actor])
                    cursor.execute(
                        "SELECT public.registrar_begin_student_group_transfer(%s, %s, %s, %s, %s, %s)",
                        [
                            str(uuid.uuid4()),
                            str(self.record.pk),
                            str(self.group.pk),
                            str(alternatives["group"].pk),
                            str(self.period.pk),
                            target_actor,
                        ],
                    )

            self._rejects(
                lambda: begin(
                    session_org=str(self.org.pk),
                    session_actor=str(self.owner.pk),
                    target_actor=self.teacher.pk,
                )
            )
            self._rejects(
                lambda: begin(
                    session_org=str(uuid.uuid4()),
                    session_actor=str(self.owner.pk),
                    target_actor=self.owner.pk,
                )
            )
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")
                cursor.execute("SELECT set_config('app.bypass_rls', 'on', true)")
        self.record.refresh_from_db()
        self.assertEqual(self.record.group_id, self.group.pk)

    def test_restricted_role_can_use_complete_sanctioned_transfer_service(self):
        with bypass_rls():
            alternatives = self._alternatives()
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.bypass_rls', 'off', true)")
            cursor.execute("SELECT set_config('app.current_org_id', %s, true)", [str(self.org.pk)])
            cursor.execute("SELECT set_config('app.current_user_id', %s, true)", [str(self.owner.pk)])
            cursor.execute("SET LOCAL ROLE rls_app_role")
        try:
            result = transfer.transfer_student_group(
                record=self.record,
                new_group=alternatives["group"],
                period=self.period,
                by_user=self.owner,
            )
            self.assertEqual(result["moved"], 1)
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")
                cursor.execute("SELECT set_config('app.bypass_rls', 'on', true)")
        self.record.refresh_from_db()
        self.assertEqual(self.record.group_id, alternatives["group"].pk)

    def test_guard_functions_are_hardened_and_trigger_matrix_is_complete(self):
        guard_functions = {
            "registrar_guard_group_transfer_evidence",
            "registrar_guard_group_transfer_finalized",
            "registrar_guard_group_transfer_no_truncate",
            "registrar_guard_reference_identity",
            "registrar_guard_conditional_parent_identity",
            "registrar_guard_student_group_transfer",
        }
        transition_functions = {
            "registrar_begin_student_group_transfer",
            "registrar_finalize_student_group_transfer",
        }
        functions = guard_functions | transition_functions
        expected_immutable_tables = {
            "registrar_enrollment",
            "registrar_lesson",
            "registrar_lessonmark",
            "registrar_assessmentscheme",
            "registrar_scheduleslot",
            "registrar_componentscore",
            "registrar_criterionscore",
            "registrar_selfworktopic",
            "registrar_selfworkmark",
            "registrar_coursework",
            "registrar_finalgrade",
            "registrar_resitrecord",
            "registrar_rubriccriterion",
        }
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT proname, prosecdef, proconfig, "
                "has_function_privilege('rls_app_role', oid, 'EXECUTE') "
                "FROM pg_proc WHERE pronamespace = 'public'::regnamespace "
                "AND proname = ANY(%s)",
                [list(functions)],
            )
            hardened = cursor.fetchall()
            cursor.execute(
                "SELECT c.relname FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
                "WHERE NOT t.tgisinternal AND t.tgname = 'registrar_reference_identity_guard'"
            )
            immutable_tables = {row[0] for row in cursor.fetchall()}
            cursor.execute(
                "SELECT tgname, count(*) FROM pg_trigger WHERE NOT tgisinternal "
                "AND tgname = ANY(%s) GROUP BY tgname",
                [
                    [
                        "registrar_conditional_parent_identity_guard",
                        "registrar_group_transfer_evidence_guard",
                        "registrar_group_transfer_finalize_guard",
                        "registrar_group_transfer_truncate_guard",
                        "registrar_student_group_transfer_guard",
                    ]
                ],
            )
            trigger_counts = dict(cursor.fetchall())
            cursor.execute(
                "SELECT has_table_privilege('rls_app_role', "
                "'public.registrar_grouptransferevidence', privilege) "
                "FROM unnest(ARRAY['INSERT', 'UPDATE', 'DELETE', 'TRUNCATE']) privilege"
            )
            evidence_write_privileges = [row[0] for row in cursor.fetchall()]
        self.assertEqual({row[0] for row in hardened}, functions)
        for name, security_definer, config, restricted_execute in hardened:
            self.assertTrue(security_definer)
            self.assertIn("search_path=pg_catalog, public", config)
            self.assertEqual(restricted_execute, name in transition_functions)
        self.assertEqual(immutable_tables, expected_immutable_tables)
        self.assertEqual(trigger_counts["registrar_conditional_parent_identity_guard"], 3)
        self.assertEqual(trigger_counts["registrar_student_group_transfer_guard"], 1)
        self.assertEqual(trigger_counts["registrar_group_transfer_evidence_guard"], 1)
        self.assertEqual(trigger_counts["registrar_group_transfer_finalize_guard"], 1)
        self.assertEqual(trigger_counts["registrar_group_transfer_truncate_guard"], 1)
        self.assertEqual(evidence_write_privileges, [False, False, False, False])
