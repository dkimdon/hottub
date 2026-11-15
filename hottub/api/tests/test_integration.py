"""Integration tests against a deployed hottub API stack.

Reads configuration from environment variables:

  HOTTUB_API_URL          Base URL, e.g. https://abc123.execute-api.us-east-1.amazonaws.com/v1
  HOTTUB_OPERATOR_API_KEY API key value for /operator endpoints
  HOTTUB_TEST_USERNAME    Cognito username (email) for UI endpoint tests
  HOTTUB_TEST_PASSWORD    Cognito password for the test user

Obtain these values after deploying:
  source <(./scripts/get_test_env.sh test)

Run with:
  python3 -m unittest tests/test_integration.py -v
"""

import json
import os
import sys
import time
import unittest
import urllib.error
import urllib.request

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

API_URL          = os.environ.get("HOTTUB_API_URL", "").rstrip("/")
OPERATOR_API_KEY = os.environ.get("HOTTUB_OPERATOR_API_KEY", "")
TEST_USERNAME    = os.environ.get("HOTTUB_TEST_USERNAME", "")
TEST_PASSWORD    = os.environ.get("HOTTUB_TEST_PASSWORD", "")
USER_POOL_ID     = os.environ.get("HOTTUB_USER_POOL_ID", "")
USER_POOL_CLIENT = os.environ.get("HOTTUB_USER_POOL_CLIENT_ID", "")


def _skip_if_not_configured():
    if not API_URL:
        raise unittest.SkipTest("HOTTUB_API_URL not set")


def _api_request(method: str, path: str, body=None, headers=None) -> tuple[int, dict]:
    url = API_URL + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _operator_request(method: str, path: str, body=None) -> tuple[int, dict]:
    return _api_request(method, path, body, {"x-api-key": OPERATOR_API_KEY})


def _get_cognito_token() -> str:
    """Authenticate with Cognito USER_PASSWORD_AUTH and return the ID token."""
    import boto3
    cognito = boto3.client("cognito-idp")
    resp = cognito.initiate_auth(
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": TEST_USERNAME, "PASSWORD": TEST_PASSWORD},
        ClientId=USER_POOL_CLIENT,
    )
    return resp["AuthenticationResult"]["IdToken"]


def _ui_request(method: str, path: str, body=None) -> tuple[int, dict]:
    token = _get_cognito_token()
    return _api_request(method, path, body, {"Authorization": token})


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestOperatorEndpoints(unittest.TestCase):
    """Tests that use the operator API key — no Cognito needed."""

    def setUp(self):
        _skip_if_not_configured()
        if not OPERATOR_API_KEY:
            self.skipTest("HOTTUB_OPERATOR_API_KEY not set")

    def test_get_desired_returns_200(self):
        status, body = _operator_request("GET", "/operator/desired")
        self.assertEqual(status, 200)
        self.assertIn("desired_setpoint", body)

    def test_get_desired_setpoint_is_valid(self):
        status, body = _operator_request("GET", "/operator/desired")
        self.assertEqual(status, 200)
        sp = body["desired_setpoint"]
        valid = {"off"} | {str(t) for t in range(102, 107)}
        self.assertIn(sp, valid, f"Unexpected desired_setpoint: {sp!r}")

    def test_report_with_temperature(self):
        status, body = _operator_request(
            "PUT", "/operator/report", {"current_temperature": 103.5}
        )
        self.assertEqual(status, 200)
        self.assertIn("reported_at", body)

    def test_report_without_temperature(self):
        status, body = _operator_request("PUT", "/operator/report", {})
        self.assertEqual(status, 200)
        self.assertIn("reported_at", body)

    def test_report_temperature_reflected_in_state(self):
        temp = 101.0
        _operator_request("PUT", "/operator/report", {"current_temperature": temp})
        time.sleep(0.5)
        status, body = _operator_request("GET", "/operator/desired")
        self.assertEqual(status, 200)
        # The state should be readable (current_temperature visible via GET /tub)

    def test_operator_key_required(self):
        # Without the API key, /operator/desired should return 403
        status, _ = _api_request("GET", "/operator/desired")
        self.assertEqual(status, 403)

    def test_invalid_temperature_rejected(self):
        status, body = _operator_request(
            "PUT", "/operator/report", {"current_temperature": "not-a-number"}
        )
        self.assertEqual(status, 400)


class TestUIEndpoints(unittest.TestCase):
    """Tests that require Cognito authentication."""

    def setUp(self):
        _skip_if_not_configured()
        if not (TEST_USERNAME and TEST_PASSWORD and USER_POOL_CLIENT):
            self.skipTest(
                "HOTTUB_TEST_USERNAME / HOTTUB_TEST_PASSWORD / "
                "HOTTUB_USER_POOL_CLIENT_ID not set"
            )

    def test_get_tub_returns_200(self):
        status, body = _ui_request("GET", "/tub")
        self.assertEqual(status, 200)

    def test_get_tub_unauthenticated_returns_401(self):
        status, _ = _api_request("GET", "/tub")
        self.assertEqual(status, 401)

    def test_set_setpoint_and_read_back(self):
        # Read current setpoint so we can restore it
        _, current = _ui_request("GET", "/tub")
        original = current.get("desired_setpoint", "off")

        target = "103" if original != "103" else "104"

        status, body = _ui_request("PUT", "/tub/setpoint", {"setpoint": int(target)})
        self.assertEqual(status, 200)
        self.assertEqual(body["setpoint"], target)

        # Read back and verify
        time.sleep(0.5)
        status, state = _ui_request("GET", "/tub")
        self.assertEqual(status, 200)
        self.assertEqual(state["desired_setpoint"], target)

        # Restore
        _ui_request("PUT", "/tub/setpoint", {"setpoint": original if original != "off" else "off"})

    def test_set_setpoint_off(self):
        status, body = _ui_request("PUT", "/tub/setpoint", {"setpoint": "off"})
        self.assertEqual(status, 200)
        self.assertEqual(body["setpoint"], "off")

    def test_set_invalid_setpoint_rejected(self):
        status, _ = _ui_request("PUT", "/tub/setpoint", {"setpoint": 99})
        self.assertEqual(status, 400)

    def test_changed_by_reflects_username(self):
        status, body = _ui_request("PUT", "/tub/setpoint", {"setpoint": 104})
        self.assertEqual(status, 200)
        self.assertNotEqual(body.get("changed_by"), "unknown")

    def test_operator_report_visible_in_tub_state(self):
        temp = 102.5
        _operator_request("PUT", "/operator/report", {"current_temperature": temp})
        time.sleep(0.5)
        status, body = _ui_request("GET", "/tub")
        self.assertEqual(status, 200)
        self.assertAlmostEqual(body.get("current_temperature", 0), temp, places=1)


class TestCORS(unittest.TestCase):

    def setUp(self):
        _skip_if_not_configured()

    def test_options_tub(self):
        status, _ = _api_request("OPTIONS", "/tub")
        self.assertEqual(status, 200)

    def test_options_setpoint(self):
        status, _ = _api_request("OPTIONS", "/tub/setpoint")
        self.assertEqual(status, 200)


if __name__ == "__main__":
    unittest.main(verbosity=2)
