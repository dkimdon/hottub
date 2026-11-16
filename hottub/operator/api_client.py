"""Client for the two operator endpoints of the hot tub API.  Standard library only."""

import json
import urllib.error
import urllib.request


class ApiError(Exception):
    """The API could not be reached or refused the request."""


class ApiClient:
    def __init__(self, base_url: str, operator_key: str, timeout: float = 15.0):
        if not base_url.startswith("https://"):
            # The operator key travels in a header; never send it in the clear.
            raise ValueError("The API URL must start with https://")
        self.base_url = base_url.rstrip("/")
        self.operator_key = operator_key
        self.timeout = timeout

    def get_desired(self) -> dict:
        """Return {"desired": {...} | None, "desired_version": int | None}."""
        return self._request("GET", "/operator/desired")

    def report(self, tub, panel_change: bool = False, desired_version=None) -> dict:
        """Report the tub's state (None = could not reach the tub).

        Returns {"adopted": bool, "desired": ..., "desired_version": ...}.
        """
        body = {"tub": tub}
        if panel_change:
            body["panel_change"] = True
            body["desired_version"] = desired_version
        return self._request("PUT", "/operator/report", body)

    def _request(self, method: str, path: str, body=None) -> dict:
        request = urllib.request.Request(
            self.base_url + path,
            method=method,
            data=None if body is None else json.dumps(body).encode(),
            headers={
                "X-Operator-Key": self.operator_key,
                "Content-Type": "application/json",
                "User-Agent": "hottub-operator",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as e:
            detail = e.read(500).decode("utf-8", errors="replace")
            raise ApiError(f"{method} {path} failed: HTTP {e.code} {detail}") from None
        except (OSError, ValueError) as e:
            # URLError and timeouts are OSErrors; ValueError is bad JSON.
            raise ApiError(f"{method} {path} failed: {e}") from None
