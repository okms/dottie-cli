import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from dottie_cli.domain import (
    DottieService,
    build_generated_private_note,
    compose_answer_value,
    merge_private_note,
)


class DomainTests(unittest.TestCase):
    def test_merge_private_note_preserves_existing_text(self) -> None:
        existing = "Eksisterende notat"
        generated = "Nytt notat"
        merged = merge_private_note(existing, generated)
        self.assertEqual(merged, "Eksisterende notat\n\nNytt notat")

    def test_merge_private_note_is_idempotent_for_same_generated_text(self) -> None:
        generated = "Maskinblokk"
        merged = merge_private_note(f"Manuelt notat\n\n{generated}", generated)
        self.assertEqual(merged, f"Manuelt notat\n\n{generated}")

    def test_merge_private_note_is_idempotent_for_same_generated_marker(self) -> None:
        existing = (
            "Manuelt notat\n\n"
            "Notat fra forrige samtale (2026-04-01)\n"
            "[dottie-cli recurring-meeting:99 index:1]\n\n"
            "Maal\nForrige svar"
        )
        generated = (
            "Notat fra forrige samtale (2026-04-01)\n"
            "[dottie-cli recurring-meeting:99 index:1]\n\n"
            "Maal\nOppdatert forrige svar"
        )

        merged = merge_private_note(existing, generated)

        self.assertEqual(merged, existing)

    def test_follow_up_note_contains_all_answer_bullets(self) -> None:
        note = build_generated_private_note(
            current_index=0,
            current_question="Oppfolging",
            previous_answer="irrelevant",
            previous_answers=[
                {"index": 3, "question": "Trivsel", "answer": "Bra"},
                {"index": 1, "question": "Maal", "answer": "To konkrete ting"},
            ],
            previous_meeting={"id": 99, "date": "2026-04-01T09:00:00Z"},
        )
        self.assertIn("Oppsummering fra forrige samtale (2026-04-01)", note)
        self.assertIn("- Maal: To konkrete ting", note)
        self.assertIn("- Trivsel: Bra", note)

    def test_prepare_note_sync_appends_to_existing_manual_private_note(self) -> None:
        client = Mock()
        client.token_bundle = SimpleNamespace(claims={"app_uid": 42})
        client.get.side_effect = [
            [{"id": 7, "name": "Employee Name"}],
            [
                {"id": 10, "employeeId": 7, "responsibleEmployeeId": 42, "status": 1, "date": "2026-04-01T09:00:00Z"},
                {"id": 11, "employeeId": 7, "responsibleEmployeeId": 42, "status": 0, "date": "2026-05-01T09:00:00Z"},
            ],
            [
                {"id": 200, "index": 1, "question": "Maal", "answer": "Forrige svar"},
            ],
            [
                {
                    "id": 300,
                    "index": 1,
                    "question": "Maal",
                    "privateNote": "Manuelt notat fra leder",
                    "version": "v1",
                },
            ],
        ]

        service = DottieService(client)
        preview = service.prepare_note_sync("Employee Name")

        self.assertEqual(len(preview.patches), 1)
        patch = preview.patches[0]
        self.assertEqual(patch["property"], "privateNote")
        self.assertIn("Manuelt notat fra leder", patch["value"])
        self.assertIn("Notat fra forrige samtale (2026-04-01)", patch["value"])
        self.assertIn("Maal\nForrige svar", patch["value"])
        self.assertTrue(patch["value"].startswith("Manuelt notat fra leder\n\n"))

    def test_prepare_note_sync_rejects_missing_upcoming_meeting(self) -> None:
        client = Mock()
        client.token_bundle = SimpleNamespace(claims={"app_uid": 42})
        client.get.side_effect = [
            [{"id": 7, "name": "Employee Name"}],
            [
                {"id": 10, "employeeId": 7, "responsibleEmployeeId": 42, "status": 1, "date": "2026-04-01T09:00:00Z"},
            ],
        ]

        service = DottieService(client)
        with self.assertRaisesRegex(ValueError, "No upcoming recurring meeting found"):
            service.prepare_note_sync("Employee Name")

    def test_prepare_note_sync_rejects_missing_completed_meeting(self) -> None:
        client = Mock()
        client.token_bundle = SimpleNamespace(claims={"app_uid": 42})
        client.get.side_effect = [
            [{"id": 7, "name": "Employee Name"}],
            [
                {"id": 11, "employeeId": 7, "responsibleEmployeeId": 42, "status": 0, "date": "2026-05-01T09:00:00Z"},
            ],
        ]

        service = DottieService(client)
        with self.assertRaisesRegex(ValueError, "No completed recurring meeting found"):
            service.prepare_note_sync("Employee Name")

    def test_prepare_note_sync_ignores_blank_leader_feedback(self) -> None:
        client = Mock()
        client.token_bundle = SimpleNamespace(claims={"app_uid": 42})
        client.get.side_effect = [
            [{"id": 7, "name": "Employee Name"}],
            [
                {"id": 10, "employeeId": 7, "responsibleEmployeeId": 42, "status": 1, "date": "2026-04-01T09:00:00Z"},
                {"id": 11, "employeeId": 7, "responsibleEmployeeId": 42, "status": 0, "date": "2026-05-01T09:00:00Z"},
            ],
            [
                {"id": 200, "index": 1, "question": "Maal", "answer": ""},
            ],
            [
                {
                    "id": 301,
                    "index": 16,
                    "question": "Tilbakemelding",
                    "privateNote": "",
                    "answer": None,
                    "version": "v2",
                },
            ],
        ]

        service = DottieService(client)
        preview = service.prepare_note_sync("Employee Name", leader_feedback="   ")

        self.assertEqual(preview.patches, [])

    def test_conversation_history_rejects_ambiguous_employee_query(self) -> None:
        client = Mock()
        client.token_bundle = SimpleNamespace(claims={"app_uid": 42})
        client.get.return_value = [
            {"id": 7, "name": "Alex Hansen"},
            {"id": 8, "name": "Alex Johansen"},
        ]

        service = DottieService(client)
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            service.conversation_history("Alex")

    def test_conversation_history_falls_back_to_employee_scope_for_self(self) -> None:
        client = Mock()
        client.token_bundle = SimpleNamespace(claims={"app_uid": 42})
        client.get.side_effect = [
            [{"id": 42, "name": "Me"}],
            [],
            [
                {"id": 11, "employeeId": 42, "responsibleEmployeeId": 99, "status": 1, "date": "2026-04-01T09:00:00Z"},
                {"id": 12, "employeeId": 42, "responsibleEmployeeId": 99, "status": 0, "date": "2026-05-01T09:00:00Z"},
            ],
            [{"id": 200, "index": 1, "question": "Q1", "answer": "A1"}],
            [{"id": 201, "index": 16, "question": "Q2", "answer": "A2"}],
        ]

        service = DottieService(client)
        employee, meetings, answers_by_meeting = service.conversation_history("Me")

        self.assertEqual(employee["id"], 42)
        self.assertEqual([item["id"] for item in meetings], [11, 12])
        self.assertEqual(answers_by_meeting[11][0]["answer"], "A1")
        self.assertEqual(answers_by_meeting[12][0]["answer"], "A2")
        self.assertEqual(
            client.get.call_args_list[1].kwargs["query"],
            {"ResponsibleEmployeeId": 42, "EmployeeId": [42]},
        )
        self.assertEqual(
            client.get.call_args_list[2].kwargs["query"],
            {"EmployeeId": [42]},
        )

    def test_upcoming_conversation_falls_back_to_employee_scope_for_self(self) -> None:
        client = Mock()
        client.token_bundle = SimpleNamespace(claims={"app_uid": 42})
        client.get.side_effect = [
            [{"id": 42, "name": "Me"}],
            [],
            [
                {"id": 12, "employeeId": 42, "responsibleEmployeeId": 99, "status": 0, "date": "2026-05-01T09:00:00Z"},
            ],
            [
                {"id": 201, "index": 16, "question": "Q2", "answer": "A2"},
            ],
        ]

        service = DottieService(client)
        employee, meeting, answers = service.upcoming_conversation("Me")

        self.assertEqual(employee["id"], 42)
        self.assertEqual(meeting["id"], 12)
        self.assertEqual(answers[0]["answer"], "A2")

    def test_upcoming_conversation_rejects_missing_upcoming_meeting(self) -> None:
        client = Mock()
        client.token_bundle = SimpleNamespace(claims={"app_uid": 42})
        client.get.side_effect = [
            [{"id": 7, "name": "Employee Name"}],
            [
                {"id": 10, "employeeId": 7, "responsibleEmployeeId": 42, "status": 1, "date": "2026-04-01T09:00:00Z"},
            ],
        ]

        service = DottieService(client)
        with self.assertRaisesRegex(ValueError, "No upcoming recurring meeting found"):
            service.upcoming_conversation("Employee Name")

    def test_team_falls_back_to_recurring_meeting_responsibility(self) -> None:
        client = Mock()
        client.token_bundle = SimpleNamespace(claims={"app_uid": 42})
        client.get.side_effect = [
            [],
            [
                {"employeeId": 8, "responsibleEmployeeId": 42, "status": 1, "date": "2026-04-01T09:00:00Z"},
                {"employeeId": 7, "responsibleEmployeeId": 42, "status": 0, "date": "2026-05-01T09:00:00Z"},
                {"employeeId": 8, "responsibleEmployeeId": 42, "status": 0, "date": "2026-06-01T09:00:00Z"},
            ],
            [
                {"id": 8, "name": "Zed Employee"},
                {"id": 7, "name": "Alpha Employee"},
            ],
        ]

        service = DottieService(client)
        team = service.team()

        self.assertEqual([item["id"] for item in team], [7, 8])
        self.assertEqual([item["name"] for item in team], ["Alpha Employee", "Zed Employee"])

    def test_absence_overview_uses_leave_interval_query_endpoint(self) -> None:
        client = Mock()
        client.token_bundle = SimpleNamespace(claims={"app_uid": 42})
        client.get.side_effect = [
            [{"id": 42, "name": "Me"}],
            {"id": 42, "name": "Me"},
        ]
        client.post.return_value = [
            {"employeeName": "Me", "dateStart": "2026-01-01T00:00:00Z", "leaveRequestId": 10},
        ]

        service = DottieService(client)
        result = service.absence_overview(from_date="2026-01-01", to_date="2026-12-31", include_self=True)

        self.assertEqual(result[0]["leaveRequestId"], 10)
        client.post.assert_called_once_with(
            "/LeaveInterval/Query",
            body={
                "employeeId": [42],
                "from": "2026-01-01",
                "to": "2026-12-31",
            },
        )


class ComposeAnswerValueTests(unittest.TestCase):
    def test_appends_footer_with_blank_line(self) -> None:
        result = compose_answer_value("Min tekst", existing=None, footer="signatur")
        self.assertEqual(result, "Min tekst\n\nsignatur")

    def test_skips_footer_when_already_present_in_new_text(self) -> None:
        result = compose_answer_value("Ferdig tekst\n\nsignatur", existing=None, footer="signatur")
        self.assertEqual(result, "Ferdig tekst\n\nsignatur")

    def test_uses_only_footer_when_new_text_is_empty(self) -> None:
        result = compose_answer_value("", existing="eksisterende", footer="signatur")
        self.assertEqual(result, "signatur")

    def test_returns_text_verbatim_when_footer_is_blank(self) -> None:
        result = compose_answer_value("Min tekst", existing="noe annet", footer="")
        self.assertEqual(result, "Min tekst")


class PrepareAnswerUpdatesTests(unittest.TestCase):
    def _service_for_self(self, answer_rows: list[dict]) -> DottieService:
        client = Mock()
        client.token_bundle = SimpleNamespace(claims={"app_uid": 42})
        client.get.side_effect = [
            {"id": 42, "name": "Me"},
            [
                {"id": 11, "employeeId": 42, "responsibleEmployeeId": 99, "status": 0, "date": "2026-05-01T09:00:00Z"},
            ],
            answer_rows,
        ]
        return DottieService(client)

    def test_patches_include_footer_and_skip_when_unchanged(self) -> None:
        rows = [
            {"id": 300, "index": 1, "question": "Q1", "answer": None, "version": "v1"},
            {"id": 301, "index": 10, "question": "Q10", "answer": "gammelt svar", "version": "v2"},
        ]
        service = self._service_for_self(rows)

        preview = service.prepare_answer_updates(
            None,
            self_only=True,
            updates=[
                {"index": 1, "text": "ny statistikk", "property": "answer"},
                {"index": 10, "text": "gammelt svar", "property": "answer"},
            ],
            footer="sign",
        )

        self.assertEqual(len(preview.patches), 2)
        patch_by_index = {patch["index"]: patch for patch in preview.patches}
        self.assertEqual(patch_by_index[1]["value"], "ny statistikk\n\nsign")
        self.assertEqual(patch_by_index[1]["property"], "answer")
        self.assertEqual(patch_by_index[10]["value"], "gammelt svar\n\nsign")

    def test_skips_updates_that_produce_identical_value(self) -> None:
        rows = [
            {"id": 300, "index": 1, "question": "Q1", "answer": "eksisterende\n\nsign", "version": "v1"},
        ]
        service = self._service_for_self(rows)

        preview = service.prepare_answer_updates(
            None,
            self_only=True,
            updates=[{"index": 1, "text": "eksisterende", "property": "answer"}],
            footer="sign",
        )

        self.assertEqual(preview.patches, [])
        self.assertEqual(len(preview.skipped), 1)
        self.assertEqual(preview.skipped[0]["reason"], "value-unchanged")

    def test_raises_for_unknown_index(self) -> None:
        rows = [
            {"id": 300, "index": 1, "question": "Q1", "answer": None, "version": "v1"},
        ]
        service = self._service_for_self(rows)

        with self.assertRaisesRegex(ValueError, "no answer row at index 99"):
            service.prepare_answer_updates(
                None,
                self_only=True,
                updates=[{"index": 99, "text": "oops", "property": "answer"}],
                footer=None,
            )

    def test_rejects_unknown_property(self) -> None:
        rows = [
            {"id": 300, "index": 1, "question": "Q1", "answer": None, "version": "v1"},
        ]
        service = self._service_for_self(rows)

        with self.assertRaisesRegex(ValueError, "Unsupported property"):
            service.prepare_answer_updates(
                None,
                self_only=True,
                updates=[{"index": 1, "text": "x", "property": "weird"}],
                footer=None,
            )

    def test_rejects_non_string_text(self) -> None:
        rows = [
            {"id": 300, "index": 1, "question": "Q1", "answer": None, "version": "v1"},
        ]
        service = self._service_for_self(rows)

        with self.assertRaisesRegex(ValueError, "text.*string"):
            service.prepare_answer_updates(
                None,
                self_only=True,
                updates=[{"index": 1, "text": 123, "property": "answer"}],
                footer=None,
            )


if __name__ == "__main__":
    unittest.main()
