import unittest

from dottie_cli.cli import build_parser


class HelpTests(unittest.TestCase):
    def test_root_help_mentions_sync_notes(self) -> None:
        parser = build_parser()
        help_text = parser.format_help()
        self.assertIn("sync-notes", help_text)
        self.assertIn("live Dottie browser session", help_text)


if __name__ == "__main__":
    unittest.main()
