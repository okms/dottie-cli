import argparse
import io
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import Mock, patch

from dottie_cli.cli import build_parser, handle_conversations, main


class CliArgumentTests(unittest.TestCase):
    def test_history_accepts_self_without_employee_name(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["conversations", "history", "--self"])

        self.assertTrue(args.self_only)
        self.assertIsNone(args.employee)

    def test_upcoming_accepts_self_without_employee_name(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["conversations", "upcoming", "--self"])

        self.assertTrue(args.self_only)
        self.assertIsNone(args.employee)

    def test_sync_notes_rejects_apply_and_dry_run_together(self) -> None:
        parser = build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(
                [
                    "conversations",
                    "sync-notes",
                    "Employee Name",
                    "--apply",
                    "--dry-run",
                ]
            )

    def test_sync_notes_preview_output_says_nothing_was_persisted(self) -> None:
        preview = SimpleNamespace(
            employee={"id": 7, "name": "Employee Name"},
            previous_meeting={"id": 10, "date": "2026-04-01T09:00:00Z"},
            current_meeting={"id": 11, "date": "2026-05-01T09:00:00Z"},
            patches=[
                {
                    "id": 99,
                    "index": 0,
                    "question": "Oppfolging",
                    "property": "privateNote",
                    "value": "Generated note block",
                    "entityId": 99,
                    "replacesVersion": None,
                }
            ],
        )
        service = Mock()
        service.prepare_note_sync.return_value = preview

        args = argparse.Namespace(
            command="conversations",
            conversation_command="sync-notes",
            employee="Employee Name",
            leader_feedback=None,
            apply=False,
            dry_run=False,
            json=False,
            token_file=None,
        )

        stdout = io.StringIO()
        with patch("dottie_cli.cli.build_service", return_value=service):
            with redirect_stdout(stdout):
                exit_code = handle_conversations(args)

        self.assertEqual(exit_code, 0)
        self.assertIn("Preview only.", stdout.getvalue())
        self.assertIn("--apply", stdout.getvalue())
        service.apply_sync.assert_not_called()

    def test_sync_notes_apply_persists_once_and_reports_patch_count(self) -> None:
        preview = SimpleNamespace(
            employee={"id": 7, "name": "Employee Name"},
            previous_meeting={"id": 10, "date": "2026-04-01T09:00:00Z"},
            current_meeting={"id": 11, "date": "2026-05-01T09:00:00Z"},
            patches=[
                {
                    "id": 99,
                    "index": 0,
                    "question": "Oppfolging",
                    "property": "privateNote",
                    "value": "Generated note block",
                    "entityId": 99,
                    "replacesVersion": None,
                },
                {
                    "id": 100,
                    "index": 16,
                    "question": "Tilbakemelding",
                    "property": "answer",
                    "value": "Bra jobbet",
                    "entityId": 100,
                    "replacesVersion": None,
                },
            ],
        )
        service = Mock()
        service.prepare_note_sync.return_value = preview

        args = argparse.Namespace(
            command="conversations",
            conversation_command="sync-notes",
            employee="Employee Name",
            leader_feedback="Bra jobbet",
            apply=True,
            dry_run=False,
            json=False,
            token_file=None,
        )

        stdout = io.StringIO()
        with patch("dottie_cli.cli.build_service", return_value=service):
            with redirect_stdout(stdout):
                exit_code = handle_conversations(args)

        self.assertEqual(exit_code, 0)
        service.apply_sync.assert_called_once_with(preview)
        self.assertIn("Applied 2 patch(es).", stdout.getvalue())
        self.assertNotIn("Preview only.", stdout.getvalue())

    def test_main_accepts_json_after_subcommand(self) -> None:
        service = Mock()
        service.team.return_value = []

        stdout = io.StringIO()
        with patch("dottie_cli.cli.build_service", return_value=service):
            with redirect_stdout(stdout):
                exit_code = main(["team", "overview", "--json"])

        self.assertEqual(exit_code, 0)
        self.assertIn('"headcount": 0', stdout.getvalue())
        self.assertIn('"organizationUnits": []', stdout.getvalue())

    def test_history_output_shows_visible_answers_for_self(self) -> None:
        service = Mock()
        service.conversation_history.return_value = (
            {"id": 42, "name": "Me"},
            [{"id": 11, "date": "2026-04-01T09:00:00Z", "status": 1, "name": "Medarbeidersamtale"}],
            {
                11: [
                    {"index": 1, "question": "Q1", "answer": "A1"},
                    {"index": 2, "question": "Q2", "answer": None},
                ]
            },
        )

        args = argparse.Namespace(
            command="conversations",
            conversation_command="history",
            employee=None,
            self_only=True,
            json=False,
            token_file=None,
        )

        stdout = io.StringIO()
        with patch("dottie_cli.cli.build_service", return_value=service):
            with redirect_stdout(stdout):
                exit_code = handle_conversations(args)

        self.assertEqual(exit_code, 0)
        self.assertIn("Employee: Me (42)", stdout.getvalue())
        self.assertIn("[1] Q1: A1", stdout.getvalue())
        self.assertNotIn("[2] Q2", stdout.getvalue())
        service.conversation_history.assert_called_once_with(None, self_only=True)

    def test_upcoming_output_shows_prefilled_visible_answers(self) -> None:
        service = Mock()
        service.upcoming_conversation.return_value = (
            {"id": 42, "name": "Me"},
            {"id": 12, "date": "2026-05-01T09:00:00Z", "status": 0, "name": "Medarbeidersamtale"},
            [
                {"index": 1, "question": "Q1", "answer": None},
                {"index": 16, "question": "Tilbakemeldinger fra leder til medarbeider", "answer": "Bra jobbet"},
            ],
        )

        args = argparse.Namespace(
            command="conversations",
            conversation_command="upcoming",
            employee=None,
            self_only=True,
            json=False,
            token_file=None,
        )

        stdout = io.StringIO()
        with patch("dottie_cli.cli.build_service", return_value=service):
            with redirect_stdout(stdout):
                exit_code = handle_conversations(args)

        self.assertEqual(exit_code, 0)
        self.assertIn("Upcoming meeting: 12 on 2026-05-01", stdout.getvalue())
        self.assertIn("[16] Tilbakemeldinger fra leder til medarbeider: Bra jobbet", stdout.getvalue())
        self.assertNotIn("No visible answers have been entered yet.", stdout.getvalue())
        service.upcoming_conversation.assert_called_once_with(None, self_only=True)


class AnswerCommandTests(unittest.TestCase):
    def test_answer_requires_target(self) -> None:
        parser = build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["conversations", "answer", "--index", "1", "--text", "x"])

    def test_answer_rejects_apply_and_dry_run_together(self) -> None:
        parser = build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(
                ["conversations", "answer", "--self", "--index", "1", "--text", "x", "--apply", "--dry-run"]
            )

    def test_answer_dry_run_preview_does_not_call_apply(self) -> None:
        preview = SimpleNamespace(
            employee={"id": 42, "name": "Me"},
            current_meeting={"id": 11, "date": "2026-05-01T09:00:00Z"},
            patches=[
                {
                    "id": 300,
                    "index": 1,
                    "question": "Q1",
                    "property": "answer",
                    "value": "ny tekst\n\nsign",
                    "entityId": 300,
                    "replacesVersion": "v1",
                    "previousValue": "",
                }
            ],
            skipped=[],
        )
        service = Mock()
        service.prepare_answer_updates.return_value = preview

        args = argparse.Namespace(
            command="conversations",
            conversation_command="answer",
            employee=None,
            self_only=True,
            index=1,
            text="ny tekst",
            answer_property="answer",
            from_file=None,
            footer="sign",
            apply=False,
            dry_run=False,
            json=False,
            token_file=None,
        )

        stdout = io.StringIO()
        with patch("dottie_cli.cli.build_service", return_value=service):
            with redirect_stdout(stdout):
                exit_code = handle_conversations(args)

        self.assertEqual(exit_code, 0)
        self.assertIn("Preview only.", stdout.getvalue())
        self.assertIn("ny tekst\n\nsign", stdout.getvalue())
        service.apply_answer_updates.assert_not_called()
        service.prepare_answer_updates.assert_called_once_with(
            None,
            self_only=True,
            updates=[{"index": 1, "text": "ny tekst", "property": "answer"}],
            footer="sign",
        )

    def test_answer_apply_invokes_apply_and_reports_count(self) -> None:
        preview = SimpleNamespace(
            employee={"id": 42, "name": "Me"},
            current_meeting={"id": 11, "date": "2026-05-01T09:00:00Z"},
            patches=[
                {
                    "id": 300, "index": 1, "question": "Q1",
                    "property": "answer", "value": "x", "entityId": 300, "replacesVersion": None,
                    "previousValue": "",
                },
                {
                    "id": 301, "index": 10, "question": "Q10",
                    "property": "answer", "value": "y", "entityId": 301, "replacesVersion": None,
                    "previousValue": "",
                },
            ],
            skipped=[],
        )
        service = Mock()
        service.prepare_answer_updates.return_value = preview

        args = argparse.Namespace(
            command="conversations",
            conversation_command="answer",
            employee=None,
            self_only=True,
            index=None,
            text=None,
            answer_property="answer",
            from_file=None,
            footer=None,
            apply=True,
            dry_run=False,
            json=False,
            token_file=None,
        )
        # inline has_inline=False without from_file => handler should error. Use from_file path.

        import json as _json
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
            tf.write(_json.dumps({"answers": [
                {"index": 1, "text": "x"},
                {"index": 10, "text": "y"},
            ]}))
            tf_path = tf.name
        from pathlib import Path as _Path
        args.from_file = _Path(tf_path)

        stdout = io.StringIO()
        with patch("dottie_cli.cli.build_service", return_value=service):
            with redirect_stdout(stdout):
                exit_code = handle_conversations(args)

        self.assertEqual(exit_code, 0)
        service.apply_answer_updates.assert_called_once_with(preview)
        self.assertIn("Applied 2 patch(es).", stdout.getvalue())

    def test_answer_shows_skipped_entries(self) -> None:
        preview = SimpleNamespace(
            employee={"id": 42, "name": "Me"},
            current_meeting={"id": 11, "date": "2026-05-01T09:00:00Z"},
            patches=[],
            skipped=[{"index": 1, "question": "Q1", "property": "answer", "reason": "value-unchanged"}],
        )
        service = Mock()
        service.prepare_answer_updates.return_value = preview

        args = argparse.Namespace(
            command="conversations",
            conversation_command="answer",
            employee=None,
            self_only=True,
            index=1,
            text="x",
            answer_property="answer",
            from_file=None,
            footer=None,
            apply=False,
            dry_run=False,
            json=False,
            token_file=None,
        )

        stdout = io.StringIO()
        with patch("dottie_cli.cli.build_service", return_value=service):
            with redirect_stdout(stdout):
                exit_code = handle_conversations(args)

        self.assertEqual(exit_code, 0)
        self.assertIn("skipped (value-unchanged)", stdout.getvalue())
        # No patches → preview-only banner suppressed
        self.assertNotIn("Preview only.", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
