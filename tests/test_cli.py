import argparse
import io
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import Mock, patch

from dottie_cli.cli import build_parser, handle_conversations, main


class CliArgumentTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
