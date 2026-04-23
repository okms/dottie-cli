from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_TOKEN_PATH = Path.home() / ".dottie-token"


class TokenError(RuntimeError):
    pass


@dataclass(frozen=True)
class TokenBundle:
    token: str
    claims: dict[str, object]
    path: Path | None = None


def _decode_segment(segment: str) -> dict[str, object]:
    padding = "=" * (-len(segment) % 4)
    raw = base64.urlsafe_b64decode(segment + padding)
    return json.loads(raw.decode("utf-8"))


def decode_jwt_claims(token: str) -> dict[str, object]:
    parts = token.split(".")
    if len(parts) != 3:
        raise TokenError("Token does not look like a JWT.")
    try:
        return _decode_segment(parts[1])
    except Exception as exc:  # pragma: no cover - narrow decode failures are enough
        raise TokenError("Could not decode JWT payload.") from exc


def is_dottie_app_token(claims: dict[str, object]) -> bool:
    return any(claim in claims for claim in ("app_uid", "app_tid", "app_auth_role", "app_uname"))


def load_token(path: Path | None = None) -> TokenBundle:
    env_token = os.environ.get("DOTTIE_TOKEN", "").strip()
    if env_token:
        claims = decode_jwt_claims(env_token)
        if not is_dottie_app_token(claims):
            raise TokenError("DOTTIE_TOKEN is not a Dottie app token.")
        return TokenBundle(token=env_token, claims=claims, path=None)

    token_path = path or DEFAULT_TOKEN_PATH
    if not token_path.exists():
        raise TokenError(
            f"No token found at {token_path}. Use `dottie token bookmarklet` or "
            "`dottie token console-snippet` to capture a live app token first."
        )

    token = token_path.read_text(encoding="utf-8").strip()
    if not token:
        raise TokenError(f"Token file {token_path} is empty.")

    claims = decode_jwt_claims(token)
    if not is_dottie_app_token(claims):
        raise TokenError(
            f"Token in {token_path} is not a Dottie app token. Capture the Authorization token "
            "used against api.dottie.no instead of a generic identity token."
        )
    return TokenBundle(token=token, claims=claims, path=token_path)


def current_employee_id(bundle: TokenBundle) -> int:
    value = bundle.claims.get("app_uid")
    if value is None:
        raise TokenError("Token is missing app_uid, so the CLI cannot resolve the current employee.")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise TokenError(f"Invalid app_uid in token: {value!r}") from exc

