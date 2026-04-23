import io
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError

from dottie_cli.api import DottieAPIError, DottieClient


class ApiTests(unittest.TestCase):
    def test_request_401_raises_refresh_guidance(self) -> None:
        client = DottieClient(token_bundle=SimpleNamespace(token="secret"))
        error = HTTPError(
            url="https://api.dottie.no/api/Employee",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=io.BytesIO(b'{"message":"unauthorized"}'),
        )
        with patch("dottie_cli.api.urlopen", side_effect=error):
            with self.assertRaises(DottieAPIError) as ctx:
                client.get("/Employee")
        self.assertIn("401 Unauthorized", str(ctx.exception))
        self.assertIn("~/.dottie-token", str(ctx.exception))
        error.close()


if __name__ == "__main__":
    unittest.main()
