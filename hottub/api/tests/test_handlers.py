"""Unit tests for the Lambda handler.

Mocks the DynamoDB table so no AWS credentials or network are needed.
Run from api/ with:
    python3 -m unittest tests/test_handlers.py -v
"""

import json
import os
import sys
import unittest
from decimal import Decimal
from unittest.mock import MagicMock, patch

# Make lambda/ importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambda"))

os.environ.setdefault("TABLE_NAME", "hottub-test")

_mock_table = MagicMock()

with patch("boto3.resource") as _mock_resource:
    _mock_resource.return_value.Table.return_value = _mock_table
    import tub

tub.TABLE = _mock_table


def _event(method, path, body=None, cognito_username=None):
    """Build a minimal API Gateway proxy event."""
    evt = {"httpMethod": method, "path": path, "body": json.dumps(body) if body else None}
    if cognito_username:
        evt["requestContext"] = {
            "authorizer": {"claims": {"cognito:username": cognito_username}}
        }
    return evt


def _body(response):
    return json.loads(response["body"])


class TestGetTub(unittest.TestCase):

    def test_returns_state(self):
        _mock_table.get_item.return_value = {
            "Item": {
                "pk": "tub", "sk": "state",
                "desired_setpoint": "104",
                "current_temperature": Decimal("103.5"),
            }
        }
        resp = tub.handler(_event("GET", "/tub"), None)
        self.assertEqual(resp["statusCode"], 200)
        body = _body(resp)
        self.assertEqual(body["desired_setpoint"], "104")
        self.assertAlmostEqual(body["current_temperature"], 103.5)
        # pk/sk should be stripped
        self.assertNotIn("pk", body)
        self.assertNotIn("sk", body)

    def test_returns_empty_when_no_item(self):
        _mock_table.get_item.return_value = {}
        resp = tub.handler(_event("GET", "/tub"), None)
        self.assertEqual(resp["statusCode"], 200)
        self.assertEqual(_body(resp), {})


class TestPutSetpoint(unittest.TestCase):

    def setUp(self):
        _mock_table.reset_mock()

    def test_valid_integer_setpoint(self):
        resp = tub.handler(
            _event("PUT", "/tub/setpoint", {"setpoint": 104}, cognito_username="alice"),
            None,
        )
        self.assertEqual(resp["statusCode"], 200)
        body = _body(resp)
        self.assertEqual(body["setpoint"], "104")
        self.assertEqual(body["changed_by"], "alice")
        _mock_table.update_item.assert_called_once()

    def test_valid_string_off(self):
        resp = tub.handler(
            _event("PUT", "/tub/setpoint", {"setpoint": "off"}, cognito_username="bob"),
            None,
        )
        self.assertEqual(resp["statusCode"], 200)
        self.assertEqual(_body(resp)["setpoint"], "off")

    def test_missing_setpoint_field(self):
        resp = tub.handler(_event("PUT", "/tub/setpoint", {}), None)
        self.assertEqual(resp["statusCode"], 400)

    def test_invalid_setpoint_value(self):
        for bad in (50, 107, "hot", 101, 0):
            with self.subTest(bad=bad):
                resp = tub.handler(
                    _event("PUT", "/tub/setpoint", {"setpoint": bad}), None
                )
                self.assertEqual(resp["statusCode"], 400)

    def test_boundary_setpoints(self):
        for temp in (102, 103, 104, 105, 106):
            _mock_table.reset_mock()
            resp = tub.handler(
                _event("PUT", "/tub/setpoint", {"setpoint": temp}), None
            )
            self.assertEqual(resp["statusCode"], 200, f"Expected 200 for setpoint={temp}")

    def test_invalid_json_body(self):
        evt = {"httpMethod": "PUT", "path": "/tub/setpoint", "body": "not-json"}
        resp = tub.handler(evt, None)
        self.assertEqual(resp["statusCode"], 400)

    def test_cognito_username_unknown_when_missing(self):
        resp = tub.handler(_event("PUT", "/tub/setpoint", {"setpoint": 104}), None)
        self.assertEqual(resp["statusCode"], 200)
        self.assertEqual(_body(resp)["changed_by"], "unknown")


class TestGetDesired(unittest.TestCase):

    def test_returns_desired_fields_only(self):
        _mock_table.get_item.return_value = {
            "Item": {
                "pk": "tub", "sk": "state",
                "desired_setpoint": "103",
                "setpoint_changed_at": "2024-01-01T00:00:00Z",
                "setpoint_changed_by": "alice",
                "current_temperature": Decimal("102.0"),
            }
        }
        resp = tub.handler(_event("GET", "/operator/desired"), None)
        self.assertEqual(resp["statusCode"], 200)
        body = _body(resp)
        self.assertEqual(body["desired_setpoint"], "103")
        self.assertIn("setpoint_changed_at", body)
        self.assertIn("setpoint_changed_by", body)
        self.assertNotIn("current_temperature", body)

    def test_defaults_to_off_when_empty(self):
        _mock_table.get_item.return_value = {}
        resp = tub.handler(_event("GET", "/operator/desired"), None)
        self.assertEqual(resp["statusCode"], 200)
        self.assertEqual(_body(resp)["desired_setpoint"], "off")


class TestPutReport(unittest.TestCase):

    def setUp(self):
        _mock_table.reset_mock()

    def test_report_with_temperature(self):
        resp = tub.handler(
            _event("PUT", "/operator/report", {"current_temperature": 103.5}),
            None,
        )
        self.assertEqual(resp["statusCode"], 200)
        self.assertIn("reported_at", _body(resp))
        _mock_table.update_item.assert_called_once()
        call_kwargs = _mock_table.update_item.call_args[1]
        expr = call_kwargs["UpdateExpression"]
        self.assertIn("current_temperature", expr)
        self.assertIn("temperature_measured_at", expr)
        self.assertIn("operator_last_seen_at", expr)

    def test_report_without_temperature(self):
        resp = tub.handler(_event("PUT", "/operator/report", {}), None)
        self.assertEqual(resp["statusCode"], 200)
        call_kwargs = _mock_table.update_item.call_args[1]
        expr = call_kwargs["UpdateExpression"]
        self.assertIn("operator_last_seen_at", expr)
        self.assertNotIn("current_temperature", expr)

    def test_invalid_temperature_type(self):
        resp = tub.handler(
            _event("PUT", "/operator/report", {"current_temperature": "hot"}),
            None,
        )
        self.assertEqual(resp["statusCode"], 400)

    def test_integer_temperature_accepted(self):
        resp = tub.handler(
            _event("PUT", "/operator/report", {"current_temperature": 103}),
            None,
        )
        self.assertEqual(resp["statusCode"], 200)


class TestRouting(unittest.TestCase):

    def test_unknown_route_returns_404(self):
        resp = tub.handler(_event("GET", "/unknown"), None)
        self.assertEqual(resp["statusCode"], 404)

    def test_options_returns_200(self):
        for path in ("/tub", "/tub/setpoint", "/operator/desired", "/operator/report"):
            resp = tub.handler(_event("OPTIONS", path), None)
            self.assertEqual(resp["statusCode"], 200, f"OPTIONS {path} should return 200")

    def test_cors_headers_present(self):
        _mock_table.get_item.return_value = {}
        resp = tub.handler(_event("GET", "/tub"), None)
        self.assertIn("Access-Control-Allow-Origin", resp["headers"])
        self.assertEqual(resp["headers"]["Access-Control-Allow-Origin"], "*")


class TestDecimalSerialization(unittest.TestCase):

    def test_decimal_serialized_as_float(self):
        _mock_table.get_item.return_value = {
            "Item": {"current_temperature": Decimal("103.5")}
        }
        resp = tub.handler(_event("GET", "/tub"), None)
        body = _body(resp)
        self.assertIsInstance(body["current_temperature"], float)
        self.assertAlmostEqual(body["current_temperature"], 103.5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
