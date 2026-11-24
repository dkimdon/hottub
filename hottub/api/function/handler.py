"""Hot tub control API — Lambda entry point.

Invoked by an API Gateway HTTP API (payload format 2.0) and, once a night,
by an EventBridge schedule.

Routes                                Who may call
------                                ------------
GET    /tub                           any signed-in user
PUT    /tub/setpoint                  any signed-in user
GET    /history                       any signed-in user
GET    /users                         admin
POST   /users                         admin
PATCH  /users/{username}              admin
DELETE /users/{username}              admin
POST   /users/{username}/reset-password   admin
GET    /operator/desired              the operator
PUT    /operator/report               the operator

Signed-in users are authenticated by API Gateway's JWT authorizer (a Cognito
token) before this code runs.  The operator authenticates with a shared
secret in the X-Operator-Key header, checked here.
"""

import hmac
import os

import history
import tub
import users
from common import ApiError, respond

USER, ADMIN, OPERATOR = "user", "admin", "operator"

ROUTES = {
    "GET /tub":                               (USER, tub.get_tub),
    "PUT /tub/setpoint":                      (USER, tub.put_setpoint),
    "PUT /tub/timer":                         (USER, tub.put_timer),
    "DELETE /tub/timer":                      (USER, tub.delete_timer),
    "GET /history":                           (USER, history.get_history),
    "GET /users":                             (ADMIN, users.list_users),
    "POST /users":                            (ADMIN, users.create_user),
    "PATCH /users/{username}":                (ADMIN, users.update_user),
    "DELETE /users/{username}":               (ADMIN, users.delete_user),
    "POST /users/{username}/reset-password":  (ADMIN, users.reset_password),
    "GET /operator/desired":                  (OPERATOR, tub.get_desired),
    "PUT /operator/report":                   (OPERATOR, tub.put_report),
}


def handler(event, context):
    if event.get("source") == "hottub.schedule":
        return tub.auto_off()

    route = event.get("routeKey", "")
    try:
        access, fn = ROUTES.get(route, (None, None))
        if fn is None:
            raise ApiError(404, "Not found")
        return fn(event, _authorize(event, access))
    except ApiError as e:
        return respond(e.status, {"error": e.message})
    except Exception as e:
        print(f"Unhandled error on {route}: {type(e).__name__}: {e}")
        return respond(500, {"error": "Internal server error"})


def _authorize(event, access):
    """Return the caller's identity, or raise 401/403."""
    if access == OPERATOR:
        supplied = (event.get("headers") or {}).get("x-operator-key", "")
        expected = os.environ.get("OPERATOR_KEY", "")
        # Refuse everything if no key is configured, rather than accept "".
        if not expected or not hmac.compare_digest(supplied.encode(), expected.encode()):
            raise ApiError(401, "Invalid operator key")
        return None

    claims = (
        (event.get("requestContext") or {}).get("authorizer", {}).get("jwt", {}).get("claims")
    )
    # API Gateway rejects requests without a valid token before we get here;
    # this guards against a route being deployed without its authorizer.
    username = claims and (claims.get("cognito:username") or claims.get("username"))
    if not username:
        raise ApiError(401, "Not signed in")
    user = {"username": username, "email": claims.get("email") or username}

    if access == ADMIN and not users.is_admin(username):
        raise ApiError(403, "Administrator access required")
    return user
