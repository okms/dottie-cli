import unittest

from dottie_cli.domain import build_generated_private_note, merge_private_note


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


if __name__ == "__main__":
    unittest.main()
