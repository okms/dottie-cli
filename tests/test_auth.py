import base64
import json
import tempfile
import unittest
from pathlib import Path

from dottie_cli.auth import TokenError, current_employee_id, load_token


def make_jwt(payload: dict[str, object]) -> str:
    header = {"alg": "none", "typ": "JWT"}
    encoded_header = base64.urlsafe_b64encode(json.dumps(header).encode("utf-8")).decode("ascii").rstrip("=")
    encoded_payload = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("ascii").rstrip("=")
    return f"{encoded_header}.{encoded_payload}.signature"


class AuthTests(unittest.TestCase):
    def test_load_token_rejects_non_dottie_token_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            token_path = Path(tmpdir) / "token"
            token_path.write_text(make_jwt({"iss": "https://connect.visma.com", "sub": "abc"}), encoding="utf-8")
            with self.assertRaises(TokenError):
                load_token(token_path)

    def test_current_employee_id_requires_numeric_app_uid(self) -> None:
        bundle = type("Bundle", (), {"claims": {"app_uid": "not-a-number"}})()
        with self.assertRaises(TokenError):
            current_employee_id(bundle)


if __name__ == "__main__":
    unittest.main()

