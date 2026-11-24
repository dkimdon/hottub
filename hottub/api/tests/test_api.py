"""Tests for the Lambda handler.

DynamoDB and Cognito are faked in-process by moto, so the real boto3 calls
and DynamoDB expressions are exercised but nothing touches AWS.

Run from api/ with:
    python -m pip install -r requirements-dev.txt
    python -m unittest discover -s tests -v
"""

import json
import os
import sys
import unittest

import boto3
from moto import mock_aws

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "function"))

OPERATOR_KEY = "test-operator-key"
MODULES = ("handler", "tub", "users", "history", "common")


class ApiTestCase(unittest.TestCase):

    def setUp(self):
        for name, value in {
            "AWS_DEFAULT_REGION": "us-west-2",
            "AWS_ACCESS_KEY_ID": "testing",
            "AWS_SECRET_ACCESS_KEY": "testing",
            "TABLE_NAME": "hottub-unit",
            "HISTORY_TABLE_NAME": "hottub-history-unit",
            "OPERATOR_KEY": OPERATOR_KEY,
        }.items():
            os.environ[name] = value

        mock = mock_aws()
        mock.start()
        self.addCleanup(mock.stop)

        boto3.client("dynamodb").create_table(
            TableName="hottub-unit",
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
        )
        boto3.client("dynamodb").create_table(
            TableName="hottub-history-unit",
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[
                {"AttributeName": "kind", "AttributeType": "S"},
                {"AttributeName": "at", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "kind", "KeyType": "HASH"},
                {"AttributeName": "at", "KeyType": "RANGE"},
            ],
        )
        self.cognito = boto3.client("cognito-idp")
        self.pool_id = self.cognito.create_user_pool(
            PoolName="hottub-unit", UsernameAttributes=["email"]
        )["UserPool"]["Id"]
        self.cognito.create_group(UserPoolId=self.pool_id, GroupName="admin")
        os.environ["USER_POOL_ID"] = self.pool_id

        # Import the function code fresh so it binds to this test's fakes.
        for name in MODULES:
            sys.modules.pop(name, None)
        import handler
        self.handler = handler.handler

        self.alice = self.make_user("alice@example.com", admin=True)
        self.bob = self.make_user("bob@example.com")

    def make_user(self, email, admin=False):
        username = self.cognito.admin_create_user(
            UserPoolId=self.pool_id,
            Username=email,
            UserAttributes=[
                {"Name": "email", "Value": email},
                {"Name": "email_verified", "Value": "true"},
            ],
        )["User"]["Username"]
        if admin:
            self.cognito.admin_add_user_to_group(
                UserPoolId=self.pool_id, Username=username, GroupName="admin"
            )
        return {"username": username, "email": email}

    def call(self, route, body=None, user=None, operator_key=None, username=None, query=None):
        """Invoke the handler the way API Gateway does; return (status, body)."""
        event = {"routeKey": route, "headers": {}, "requestContext": {}}
        if query is not None:
            event["queryStringParameters"] = query
        if body is not None:
            event["body"] = body if isinstance(body, str) else json.dumps(body)
        if user is not None:
            event["requestContext"]["authorizer"] = {"jwt": {"claims": {
                "cognito:username": user["username"],
                "email": user["email"],
            }}}
        if operator_key is not None:
            event["headers"]["x-operator-key"] = operator_key
        if username is not None:
            event["pathParameters"] = {"username": username}
        response = self.handler(event, None)
        return response["statusCode"], json.loads(response["body"])

    def operator(self, route, body=None):
        return self.call(route, body, operator_key=OPERATOR_KEY)

    def report(self, **overrides):
        tub = {
            "current_temperature": 101,
            "set_temperature": 104,
            "heating_mode": "ready",
            "temperature_range": "high",
            "heating": True,
        }
        tub.update(overrides.pop("tub", {}))
        return self.operator("PUT /operator/report", {"tub": tub, **overrides})


class TestAuthorization(ApiTestCase):

    def test_unknown_route(self):
        self.assertEqual(self.call("GET /nope", user=self.bob)[0], 404)

    def test_user_routes_require_identity(self):
        self.assertEqual(self.call("GET /tub")[0], 401)
        self.assertEqual(self.call("PUT /tub/setpoint", {"setpoint": 104})[0], 401)

    def test_operator_key_does_not_open_user_routes(self):
        self.assertEqual(self.call("GET /tub", operator_key=OPERATOR_KEY)[0], 401)

    def test_operator_routes_require_key(self):
        self.assertEqual(self.call("GET /operator/desired")[0], 401)
        self.assertEqual(self.call("GET /operator/desired", operator_key="wrong")[0], 401)
        self.assertEqual(self.call("GET /operator/desired", operator_key="")[0], 401)
        self.assertEqual(self.call("GET /operator/desired", user=self.alice)[0], 401)

    def test_unconfigured_operator_key_refuses_everything(self):
        os.environ["OPERATOR_KEY"] = ""
        self.assertEqual(self.call("GET /operator/desired", operator_key="")[0], 401)

    def test_admin_routes_refuse_ordinary_users(self):
        for route, kwargs in [
            ("GET /users", {}),
            ("POST /users", {"body": {"email": "eve@example.com"}}),
            ("PATCH /users/{username}", {"username": self.bob["username"], "body": {"admin": True}}),
            ("DELETE /users/{username}", {"username": self.alice["username"]}),
            ("POST /users/{username}/reset-password", {"username": self.alice["username"]}),
        ]:
            with self.subTest(route=route):
                self.assertEqual(self.call(route, user=self.bob, **kwargs)[0], 403)

    def test_admin_claim_in_token_is_not_trusted(self):
        # Group membership is checked with Cognito, not read from the token.
        event_user = dict(self.bob)
        status, _ = self.call("GET /users", user=event_user)
        self.assertEqual(status, 403)

    def test_revoked_admin_loses_access_immediately(self):
        self.assertEqual(self.call("GET /users", user=self.alice)[0], 200)
        self.cognito.admin_remove_user_from_group(
            UserPoolId=self.pool_id, Username=self.alice["username"], GroupName="admin"
        )
        self.assertEqual(self.call("GET /users", user=self.alice)[0], 403)


class TestSetpoint(ApiTestCase):

    def test_empty_state(self):
        status, body = self.call("GET /tub", user=self.bob)
        self.assertEqual(status, 200)
        self.assertIsNone(body["setpoint"])
        self.assertIsNone(body["current_temperature"])
        self.assertEqual(body["allowed_setpoints"], ["off", "102", "103", "104", "105", "106"])

    def test_set_and_read_back(self):
        for value in (102, 103, 104, 105, 106, "104", "off"):
            with self.subTest(value=value):
                status, body = self.call("PUT /tub/setpoint", {"setpoint": value}, user=self.bob)
                self.assertEqual(status, 200)
                self.assertEqual(body["setpoint"], str(value))
                _, state = self.call("GET /tub", user=self.alice)
                self.assertEqual(state["setpoint"], str(value))
                self.assertEqual(state["setpoint_changed_by"], "bob@example.com")
                self.assertEqual(state["setpoint_source"], "ui")

    def test_invalid_setpoints(self):
        for bad in (101, 107, 0, 104.5, True, None, "hot", "104.0", [104], {"a": 1}):
            with self.subTest(bad=bad):
                status, _ = self.call("PUT /tub/setpoint", {"setpoint": bad}, user=self.bob)
                self.assertEqual(status, 400)

    def test_invalid_bodies(self):
        for bad in ("not-json", "[]", '"x"', '{"setpoint": NaN}', "{}"):
            with self.subTest(bad=bad):
                self.assertEqual(self.call("PUT /tub/setpoint", bad, user=self.bob)[0], 400)

    def test_operator_sees_tub_controls(self):
        self.call("PUT /tub/setpoint", {"setpoint": 105}, user=self.bob)
        _, body = self.operator("GET /operator/desired")
        self.assertEqual(body["desired"], {
            "heating_mode": "ready", "temperature_range": "high", "set_temperature": 105,
        })
        self.assertEqual(body["desired_version"], 1)

        self.call("PUT /tub/setpoint", {"setpoint": "off"}, user=self.bob)
        _, body = self.operator("GET /operator/desired")
        self.assertEqual(body["desired"], {
            "heating_mode": "rest", "temperature_range": "low", "set_temperature": 50,
        })
        self.assertEqual(body["desired_version"], 2)

    def test_no_desired_state_yet(self):
        _, body = self.operator("GET /operator/desired")
        self.assertEqual(body, {"desired": None, "desired_version": None})


class TestReport(ApiTestCase):

    def test_report_is_visible_to_users(self):
        status, body = self.report()
        self.assertEqual(status, 200)
        self.assertFalse(body["adopted"])
        _, state = self.call("GET /tub", user=self.bob)
        self.assertEqual(state["current_temperature"], 101)
        self.assertTrue(state["heating"])
        self.assertEqual(state["temperature_measured_at"], body["reported_at"])
        self.assertEqual(state["tub_last_seen_at"], body["reported_at"])
        # A plain report never changes what users asked for.
        self.assertIsNone(state["setpoint"])

    def test_unknown_temperature_keeps_last_reading(self):
        self.report()
        self.report(tub={"current_temperature": None})
        _, state = self.call("GET /tub", user=self.bob)
        self.assertEqual(state["current_temperature"], 101)

    def test_tub_unreachable(self):
        status, _ = self.operator("PUT /operator/report", {"tub": None})
        self.assertEqual(status, 200)
        _, state = self.call("GET /tub", user=self.bob)
        self.assertIsNotNone(state["operator_last_seen_at"])
        self.assertIsNone(state["tub_last_seen_at"])

    def test_invalid_reports(self):
        for bad in (
            {"current_temperature": "hot"},
            {"current_temperature": True},
            {"current_temperature": 500},
            {"set_temperature": 104.5},
            {"set_temperature": None},
            {"heating_mode": "boiling"},
            {"temperature_range": "medium"},
            {"heating": "yes"},
        ):
            with self.subTest(bad=bad):
                self.assertEqual(self.report(tub=bad)[0], 400)
        self.assertEqual(self.operator("PUT /operator/report", {"tub": "x"})[0], 400)
        self.assertEqual(self.operator("PUT /operator/report", {"panel_change": True})[0], 400)


class TestMostRecentChangeWins(ApiTestCase):

    def test_panel_change_becomes_desired_state(self):
        self.call("PUT /tub/setpoint", {"setpoint": 104}, user=self.bob)
        status, body = self.report(
            tub={"set_temperature": 100}, panel_change=True, desired_version=1
        )
        self.assertEqual(status, 200)
        self.assertTrue(body["adopted"])
        self.assertEqual(body["desired"]["set_temperature"], 100)
        self.assertEqual(body["desired_version"], 2)

        _, state = self.call("GET /tub", user=self.bob)
        self.assertEqual(state["setpoint"], "100")
        self.assertEqual(state["setpoint_source"], "panel")
        self.assertIsNone(state["setpoint_changed_by"])

    def test_panel_rest_mode_shows_as_off(self):
        self.call("PUT /tub/setpoint", {"setpoint": 104}, user=self.bob)
        self.report(tub={"heating_mode": "rest"}, panel_change=True, desired_version=1)
        _, state = self.call("GET /tub", user=self.bob)
        self.assertEqual(state["setpoint"], "off")
        _, desired = self.operator("GET /operator/desired")
        # The tub's own controls are kept as they are, so the operator has
        # nothing to change.
        self.assertEqual(desired["desired"], {
            "heating_mode": "rest", "temperature_range": "high", "set_temperature": 104,
        })

    def test_ui_change_after_panel_change_wins(self):
        self.report(panel_change=True, desired_version=None)
        self.call("PUT /tub/setpoint", {"setpoint": 106}, user=self.alice)
        _, state = self.call("GET /tub", user=self.bob)
        self.assertEqual(state["setpoint"], "106")
        self.assertEqual(state["setpoint_source"], "ui")
        self.assertEqual(state["setpoint_changed_by"], "alice@example.com")

    def test_stale_panel_report_does_not_override_newer_ui_change(self):
        # The operator read version 1, then a user changed the setpoint, then
        # the operator's panel report arrives.  The user's change is newer.
        self.call("PUT /tub/setpoint", {"setpoint": 104}, user=self.bob)
        self.call("PUT /tub/setpoint", {"setpoint": 106}, user=self.alice)
        status, body = self.report(
            tub={"set_temperature": 100}, panel_change=True, desired_version=1
        )
        self.assertEqual(status, 200)
        self.assertFalse(body["adopted"])
        self.assertEqual(body["desired"]["set_temperature"], 106)
        self.assertEqual(body["desired_version"], 2)

    def test_first_report_seeds_desired_state_from_the_tub(self):
        status, body = self.report(panel_change=True, desired_version=None)
        self.assertTrue(body["adopted"])
        self.assertEqual(body["desired_version"], 1)
        # ... but only if there really is none yet.
        status, body = self.report(
            tub={"set_temperature": 99}, panel_change=True, desired_version=None
        )
        self.assertFalse(body["adopted"])
        self.assertEqual(body["desired"]["set_temperature"], 104)


class TestAutoOff(ApiTestCase):

    def auto_off(self):
        return self.handler({"source": "hottub.schedule"}, None)

    def test_turns_tub_off(self):
        self.call("PUT /tub/setpoint", {"setpoint": 104}, user=self.bob)
        self.assertEqual(self.auto_off(), {"changed": True})
        _, state = self.call("GET /tub", user=self.bob)
        self.assertEqual(state["setpoint"], "off")
        self.assertEqual(state["setpoint_source"], "schedule")
        self.assertIsNone(state["setpoint_changed_by"])

    def test_leaves_an_off_tub_alone(self):
        self.call("PUT /tub/setpoint", {"setpoint": "off"}, user=self.bob)
        self.assertEqual(self.auto_off(), {"changed": False})
        _, state = self.call("GET /tub", user=self.bob)
        self.assertEqual(state["setpoint_source"], "ui")

    def test_no_state_yet(self):
        self.assertEqual(self.auto_off(), {"changed": False})


class TestHistory(ApiTestCase):

    def history(self, **query):
        return self.call("GET /history", user=self.bob, query=query or None)

    def add_readings(self, minutes_ago_and_temperature):
        """Insert temperature readings directly, at chosen times in the past."""
        from datetime import datetime, timedelta, timezone
        table = boto3.resource("dynamodb").Table("hottub-history-unit")
        now = datetime.now(timezone.utc)
        for minutes, temperature in minutes_ago_and_temperature:
            at = (now - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")
            table.put_item(Item={
                "kind": "temperature", "at": at, "temperature": temperature, "heating": False,
            })

    def test_requires_sign_in(self):
        self.assertEqual(self.call("GET /history")[0], 401)

    def test_empty(self):
        status, body = self.history()
        self.assertEqual(status, 200)
        self.assertEqual(body["hours"], 24)
        self.assertEqual(body["temperatures"], [])
        self.assertEqual(body["changes"], [])

    def test_invalid_period(self):
        for bad in ("1", "abc", "-24", "100000"):
            self.assertEqual(self.history(hours=bad)[0], 400)

    def test_changes_are_logged_from_every_source(self):
        self.call("PUT /tub/setpoint", {"setpoint": 104}, user=self.bob)
        # History is keyed by time to the second; give each change its own.
        import time
        time.sleep(1.1)
        self.report(tub={"heating_mode": "rest"}, panel_change=True, desired_version=1)
        time.sleep(1.1)
        self.call("PUT /tub/setpoint", {"setpoint": 106}, user=self.alice)
        time.sleep(1.1)
        self.handler({"source": "hottub.schedule"}, None)

        _, body = self.history()
        changes = [(c["setpoint"], c["source"], c["changed_by"]) for c in body["changes"]]
        self.assertEqual(changes, [          # newest first
            ("off", "schedule", None),
            ("106", "ui", "alice@example.com"),
            ("off", "panel", None),
            ("104", "ui", "bob@example.com"),
        ])

    def test_reports_are_logged(self):
        self.report(tub={"current_temperature": 101, "heating": True})
        _, body = self.history()
        self.assertEqual(len(body["temperatures"]), 1)
        self.assertEqual(body["temperatures"][0]["temperature"], 101)
        self.assertTrue(body["temperatures"][0]["heating"])

    def test_unknown_temperature_is_not_logged(self):
        self.report(tub={"current_temperature": None})
        self.assertEqual(self.history()[1]["temperatures"], [])

    def test_period_limits_what_is_returned(self):
        self.add_readings([(10, 100), (60 * 30, 90), (60 * 24 * 10, 80)])
        self.assertEqual([p["temperature"] for p in self.history(hours="24")[1]["temperatures"]], [100])
        self.assertEqual(
            [p["temperature"] for p in self.history(hours="168")[1]["temperatures"]], [90, 100]
        )
        self.assertEqual(
            [p["temperature"] for p in self.history(hours="720")[1]["temperatures"]], [80, 90, 100]
        )

    def test_many_readings_are_averaged_down(self):
        # A reading every 2 minutes for a day is 720 readings.
        self.add_readings([(m, 100 + (m % 4)) for m in range(1, 1440, 2)])
        points = self.history()[1]["temperatures"]
        self.assertLessEqual(len(points), 240)
        self.assertGreater(len(points), 200)
        self.assertTrue(all(100 <= p["temperature"] <= 103 for p in points))
        self.assertEqual([p["at"] for p in points], sorted(p["at"] for p in points))

    def test_stats(self):
        from datetime import datetime, timedelta, timezone
        table = boto3.resource("dynamodb").Table("hottub-history-unit")
        now = datetime.now(timezone.utc)
        # Heating for an hour (readings every 2 minutes), then gaps of 28 and
        # 12 minutes that must not count, then 10 minutes off.
        times = [(m, True) for m in range(200, 139, -2)] + [(112, True)] + [(m, False) for m in range(100, 89, -2)]
        for minutes, heating in times:
            table.put_item(Item={"kind": "temperature", "temperature": 100, "heating": heating,
                                 "at": (now - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")})
        self.call("PUT /tub/setpoint", {"setpoint": 104}, user=self.bob)
        import time
        time.sleep(1.1)  # history keeps one change per second
        self.handler({"source": "hottub.schedule"}, None)
        stats = self.history()[1]["stats"]
        self.assertEqual(stats["heating_hours"], 1.0)
        self.assertEqual(stats["times_used"], 1)  # the turn-off does not count

    def test_history_failure_does_not_block_control(self):
        boto3.client("dynamodb").delete_table(TableName="hottub-history-unit")
        status, _ = self.call("PUT /tub/setpoint", {"setpoint": 104}, user=self.bob)
        self.assertEqual(status, 200)
        self.assertEqual(self.report()[0], 200)
        self.assertEqual(self.call("GET /tub", user=self.bob)[1]["setpoint"], "104")


class TestUsers(ApiTestCase):

    def emails(self):
        _, body = self.call("GET /users", user=self.alice)
        return {u["email"]: u for u in body["users"]}

    def test_list(self):
        users = self.emails()
        self.assertEqual(sorted(users), ["alice@example.com", "bob@example.com"])
        self.assertTrue(users["alice@example.com"]["admin"])
        self.assertFalse(users["bob@example.com"]["admin"])
        self.assertEqual(users["bob@example.com"]["username"], self.bob["username"])

    def test_create(self):
        status, body = self.call("POST /users", {"email": " Carol@Example.com "}, user=self.alice)
        self.assertEqual(status, 201)
        self.assertEqual(body["user"]["email"], "carol@example.com")
        self.assertFalse(body["user"]["admin"])
        self.assertEqual(body["user"]["status"], "FORCE_CHANGE_PASSWORD")
        self.assertIn("carol@example.com", self.emails())

    def test_create_admin(self):
        self.call("POST /users", {"email": "dan@example.com", "admin": True}, user=self.alice)
        self.assertTrue(self.emails()["dan@example.com"]["admin"])

    def test_create_duplicate(self):
        status, _ = self.call("POST /users", {"email": "bob@example.com"}, user=self.alice)
        self.assertEqual(status, 409)

    def test_create_invalid(self):
        for bad in ({}, {"email": "nope"}, {"email": 5}, {"email": "a@b.co", "admin": "yes"}):
            with self.subTest(bad=bad):
                self.assertEqual(self.call("POST /users", bad, user=self.alice)[0], 400)

    def test_grant_and_revoke_admin(self):
        bob = self.bob["username"]
        status, _ = self.call("PATCH /users/{username}", {"admin": True}, self.alice, username=bob)
        self.assertEqual(status, 200)
        self.assertEqual(self.call("GET /users", user=self.bob)[0], 200)

        self.call("PATCH /users/{username}", {"admin": False}, self.alice, username=bob)
        self.assertEqual(self.call("GET /users", user=self.bob)[0], 403)

    def test_cannot_demote_or_delete_self(self):
        me = self.alice["username"]
        status, _ = self.call("PATCH /users/{username}", {"admin": False}, self.alice, username=me)
        self.assertEqual(status, 400)
        self.assertEqual(self.call("DELETE /users/{username}", user=self.alice, username=me)[0], 400)
        self.assertTrue(self.emails()["alice@example.com"]["admin"])

    def test_delete(self):
        status, _ = self.call(
            "DELETE /users/{username}", user=self.alice, username=self.bob["username"]
        )
        self.assertEqual(status, 200)
        self.assertNotIn("bob@example.com", self.emails())

    def test_unknown_user(self):
        missing = "00000000-0000-0000-0000-000000000000"
        self.assertEqual(
            self.call("DELETE /users/{username}", user=self.alice, username=missing)[0], 404
        )
        self.assertEqual(
            self.call("PATCH /users/{username}", {"admin": True}, self.alice, username=missing)[0],
            404,
        )
        self.assertEqual(
            self.call("DELETE /users/{username}", user=self.alice, username="bad name!")[0], 400
        )

    def test_reset_password_for_confirmed_user(self):
        self.cognito.admin_set_user_password(
            UserPoolId=self.pool_id, Username=self.bob["username"],
            Password="Password-123", Permanent=True,
        )
        status, body = self.call(
            "POST /users/{username}/reset-password", user=self.alice, username=self.bob["username"]
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["sent"], "code")
        self.assertEqual(self.emails()["bob@example.com"]["status"], "RESET_REQUIRED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
