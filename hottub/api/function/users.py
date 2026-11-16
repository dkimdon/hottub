"""User administration — admins manage the people who may use the tub.

Users live in the Cognito user pool.  Admins are the members of the pool's
"admin" group.  There is no self-registration: the only ways to get an
account are an admin creating one here, or scripts/manage_users.py.

Every route in this module requires the caller to be an admin; that is
enforced in handler.py before these functions run.
"""

import os
import re

import boto3
from botocore.exceptions import ClientError

from common import ApiError, json_body, respond

COGNITO = boto3.client("cognito-idp")
USER_POOL_ID = os.environ["USER_POOL_ID"]
ADMIN_GROUP = "admin"

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_USERNAME = re.compile(r"^[\w.@+-]{1,128}$")


def is_admin(username: str) -> bool:
    """Check group membership with Cognito rather than trusting the token.

    A token keeps saying "admin" for up to an hour after the user has been
    removed from the group; asking Cognito makes removal take effect at once.
    """
    try:
        groups = COGNITO.admin_list_groups_for_user(UserPoolId=USER_POOL_ID, Username=username)
    except ClientError as e:
        if _code(e) == "UserNotFoundException":
            return False
        raise
    return any(g["GroupName"] == ADMIN_GROUP for g in groups["Groups"])


def list_users(event, user):
    admins = set()
    for page in COGNITO.get_paginator("list_users_in_group").paginate(
        UserPoolId=USER_POOL_ID, GroupName=ADMIN_GROUP
    ):
        admins.update(u["Username"] for u in page["Users"])

    users = []
    for page in COGNITO.get_paginator("list_users").paginate(UserPoolId=USER_POOL_ID):
        users.extend(_user_view(u, u["Username"] in admins) for u in page["Users"])
    users.sort(key=lambda u: u["email"].lower())
    return respond(200, {"users": users})


def create_user(event, user):
    body = json_body(event)
    email = body.get("email")
    if not isinstance(email, str) or len(email) > 254 or not _EMAIL.match(email.strip()):
        raise ApiError(400, "'email' must be a valid email address")
    email = email.strip().lower()
    make_admin = body.get("admin", False)
    if not isinstance(make_admin, bool):
        raise ApiError(400, "'admin' must be true or false")

    try:
        created = COGNITO.admin_create_user(
            UserPoolId=USER_POOL_ID,
            Username=email,
            UserAttributes=[
                {"Name": "email", "Value": email},
                {"Name": "email_verified", "Value": "true"},
            ],
            DesiredDeliveryMediums=["EMAIL"],
        )["User"]
    except ClientError as e:
        if _code(e) == "UsernameExistsException":
            raise ApiError(409, "A user with that email address already exists")
        raise

    if make_admin:
        COGNITO.admin_add_user_to_group(
            UserPoolId=USER_POOL_ID, Username=created["Username"], GroupName=ADMIN_GROUP
        )
    print(f"{user['email']} created user {email} (admin={make_admin})")
    return respond(201, {"user": _user_view(created, make_admin)})


def delete_user(event, user):
    username = _target(event)
    if username == user["username"]:
        raise ApiError(400, "You cannot delete your own account")
    with _not_found():
        COGNITO.admin_delete_user(UserPoolId=USER_POOL_ID, Username=username)
    print(f"{user['email']} deleted user {username}")
    return respond(200, {"deleted": username})


def update_user(event, user):
    """Grant or revoke admin rights."""
    username = _target(event)
    make_admin = json_body(event).get("admin")
    if not isinstance(make_admin, bool):
        raise ApiError(400, "'admin' must be true or false")
    if not make_admin and username == user["username"]:
        # Guarantees there is always at least one admin left.
        raise ApiError(400, "You cannot remove your own admin rights")

    change = COGNITO.admin_add_user_to_group if make_admin else COGNITO.admin_remove_user_from_group
    with _not_found():
        change(UserPoolId=USER_POOL_ID, Username=username, GroupName=ADMIN_GROUP)
    print(f"{user['email']} set admin={make_admin} for user {username}")
    return respond(200, {"username": username, "admin": make_admin})


def reset_password(event, user):
    """Email the user what they need to set a new password.

    Someone who has never signed in gets a fresh invitation with a new
    temporary password.  Anyone else gets a verification code, which they
    enter on the sign-in page's "Forgot password" form.
    """
    username = _target(event)
    with _not_found():
        target = COGNITO.admin_get_user(UserPoolId=USER_POOL_ID, Username=username)
        if target["UserStatus"] == "FORCE_CHANGE_PASSWORD":
            COGNITO.admin_create_user(
                UserPoolId=USER_POOL_ID,
                Username=username,
                MessageAction="RESEND",
                DesiredDeliveryMediums=["EMAIL"],
            )
            sent = "invitation"
        else:
            COGNITO.admin_reset_user_password(UserPoolId=USER_POOL_ID, Username=username)
            sent = "code"
    print(f"{user['email']} reset password for user {username} ({sent})")
    return respond(200, {"username": username, "sent": sent})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _target(event) -> str:
    username = (event.get("pathParameters") or {}).get("username", "")
    if not _USERNAME.match(username):
        raise ApiError(400, "Invalid username")
    return username


def _user_view(cognito_user: dict, admin: bool) -> dict:
    attributes = cognito_user.get("Attributes") or cognito_user.get("UserAttributes") or []
    email = next((a["Value"] for a in attributes if a["Name"] == "email"), "")
    created = cognito_user.get("UserCreateDate")
    return {
        "username": cognito_user["Username"],
        "email": email,
        "admin": admin,
        # CONFIRMED, FORCE_CHANGE_PASSWORD (invited, never signed in),
        # RESET_REQUIRED (password reset pending)
        "status": cognito_user.get("UserStatus"),
        "created_at": created.strftime("%Y-%m-%dT%H:%M:%SZ") if created else None,
    }


def _code(error: ClientError) -> str:
    return error.response["Error"]["Code"]


class _not_found:
    """Turn Cognito's UserNotFoundException into a 404."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if isinstance(exc, ClientError) and _code(exc) == "UserNotFoundException":
            raise ApiError(404, "No such user") from None
        return False
