from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .auth import TokenBundle


BASE_URL = "https://api.dottie.no/api"


class DottieAPIError(RuntimeError):
    pass


@dataclass
class DottieClient:
    token_bundle: TokenBundle
    timeout: float = 30.0
    base_url: str = BASE_URL

    def request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        body: Any | None = None,
    ) -> Any:
        url = f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"
        if query:
            items: list[tuple[str, str]] = []
            for key, value in query.items():
                if value is None:
                    continue
                if isinstance(value, (list, tuple)):
                    for entry in value:
                        items.append((key, str(entry)))
                else:
                    items.append((key, str(value)))
            if items:
                url = f"{url}?{urlencode(items)}"

        payload = None
        if body is not None:
            payload = json.dumps(body).encode("utf-8")

        request = Request(
            url,
            data=payload,
            method=method.upper(),
            headers={
                "Accept": "application/json, text/plain, */*",
                "Authorization": f"Bearer {self.token_bundle.token}",
                "Content-Type": "application/json",
                "Origin": "https://app.dottie.no",
                "Referer": "https://app.dottie.no/",
            },
        )

        try:
            with urlopen(request, timeout=self.timeout) as response:
                data = response.read()
        except HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="replace")
            if exc.code == 401:
                raise DottieAPIError(
                    "Dottie rejected the token with 401 Unauthorized. Refresh the live app token "
                    "and write it back to ~/.dottie-token."
                ) from exc
            raise DottieAPIError(f"HTTP {exc.code} for {method.upper()} {path}: {body_text}") from exc
        except URLError as exc:
            raise DottieAPIError(f"Network error for {method.upper()} {path}: {exc}") from exc

        if not data:
            return None
        try:
            return json.loads(data.decode("utf-8"))
        except json.JSONDecodeError:
            return data.decode("utf-8", errors="replace")

    def get(self, path: str, *, query: dict[str, Any] | None = None) -> Any:
        return self.request("GET", path, query=query)

    def post(self, path: str, *, query: dict[str, Any] | None = None, body: Any | None = None) -> Any:
        return self.request("POST", path, query=query, body=body)

    def patch(self, path: str, *, body: Any) -> Any:
        return self.request("PATCH", path, body=body)

