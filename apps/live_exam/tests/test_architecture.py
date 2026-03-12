from django.test import SimpleTestCase


class LiveExamArchitectureModulesTest(SimpleTestCase):
    def test_refactored_modules_are_importable(self):
        from apps.live_exam import auth, scoring, serializers, transport
        from apps.live_exam.domain import session

        self.assertTrue(hasattr(auth, "authorize_socket_connection"))
        self.assertTrue(hasattr(auth, "get_client_id"))
        self.assertTrue(hasattr(session, "get_question_by_index"))
        self.assertTrue(hasattr(session, "get_total_questions"))
        self.assertTrue(hasattr(scoring, "save_answer_and_score"))
        self.assertTrue(hasattr(scoring, "score_multi_fraction"))
        self.assertTrue(hasattr(serializers, "serialize_question"))
        self.assertTrue(hasattr(serializers, "serialize_players"))
        self.assertTrue(hasattr(serializers, "serialize_player_identity"))
        self.assertTrue(hasattr(transport, "build_question_payload"))
        self.assertTrue(hasattr(transport, "build_reveal_payload"))
        self.assertTrue(hasattr(transport, "build_reaction_event_payload"))
