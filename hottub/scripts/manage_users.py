#!/usr/bin/env python3
"""Manage hot tub users from the command line.

Day to day, admins manage users in the web UI.  This tool exists for what
the UI cannot do: creating the very first admin, and recovering if every
admin is locked out.

    python scripts/manage_users.py list test
    python scripts/manage_users.py create test someone@example.com
    python scripts/manage_users.py create test someone@example.com --admin
    python scripts/manage_users.py make-admin test someone@example.com
    python scripts/manage_users.py remove-admin test someone@example.com
    python scripts/manage_users.py set-password test someone@example.com
    python scripts/manage_users.py delete test someone@example.com

"create" emails the person a temporary password.  "set-password" asks for
the new password without showing it.

Requires boto3 and AWS credentials.  The region defaults to us-west-2;
override with --region or HOTTUB_REGION.
"""

import argparse
import getpass
import os
import sys

import boto3

ADMIN_GROUP = "admin"


class Pool:
    def __init__(self, env: str, region: str):
        stack = boto3.client("cloudformation", region_name=region).describe_stacks(
            StackName=f"hottub-{env}"
        )["Stacks"][0]
        self.id = next(o["OutputValue"] for o in stack["Outputs"] if o["OutputKey"] == "UserPoolId")
        self.cognito = boto3.client("cognito-idp", region_name=region)

    def call(self, operation: str, **kwargs):
        return getattr(self.cognito, operation)(UserPoolId=self.id, **kwargs)

    def pages(self, operation: str, **kwargs):
        paginator = self.cognito.get_paginator(operation)
        for page in paginator.paginate(UserPoolId=self.id, **kwargs):
            yield from page["Users"]


def cmd_list(pool, args):
    admins = {u["Username"] for u in pool.pages("list_users_in_group", GroupName=ADMIN_GROUP)}
    rows = []
    for u in pool.pages("list_users"):
        email = next((a["Value"] for a in u["Attributes"] if a["Name"] == "email"), "")
        rows.append((email, "admin" if u["Username"] in admins else "", u["UserStatus"]))
    if not rows:
        print("No users.")
        return
    for email, admin, status in sorted(rows):
        print(f"{email:<40} {admin:<6} {status}")


def cmd_create(pool, args):
    pool.call(
        "admin_create_user",
        Username=args.email,
        UserAttributes=[
            {"Name": "email", "Value": args.email},
            {"Name": "email_verified", "Value": "true"},
        ],
        DesiredDeliveryMediums=["EMAIL"],
    )
    print(f"Created {args.email}; a temporary password has been emailed.")
    if args.admin:
        cmd_make_admin(pool, args)


def cmd_make_admin(pool, args):
    pool.call("admin_add_user_to_group", Username=args.email, GroupName=ADMIN_GROUP)
    print(f"{args.email} is now an admin.")


def cmd_remove_admin(pool, args):
    pool.call("admin_remove_user_from_group", Username=args.email, GroupName=ADMIN_GROUP)
    print(f"{args.email} is no longer an admin.")


def cmd_set_password(pool, args):
    password = getpass.getpass(f"New password for {args.email}: ")
    if password != getpass.getpass("Again: "):
        sys.exit("Passwords do not match.")
    pool.call("admin_set_user_password", Username=args.email, Password=password, Permanent=True)
    print(f"Password updated for {args.email}.")


def cmd_delete(pool, args):
    pool.call("admin_delete_user", Username=args.email)
    print(f"Deleted {args.email}.")


COMMANDS = {
    "list": cmd_list,
    "create": cmd_create,
    "make-admin": cmd_make_admin,
    "remove-admin": cmd_remove_admin,
    "set-password": cmd_set_password,
    "delete": cmd_delete,
}


def main():
    parser = argparse.ArgumentParser(description="Manage hot tub users")
    parser.add_argument("command", choices=COMMANDS)
    parser.add_argument("env", choices=["test", "live"])
    parser.add_argument("email", nargs="?")
    parser.add_argument("--admin", action="store_true", help="with create: also make them an admin")
    parser.add_argument("--region", default=os.environ.get("HOTTUB_REGION", "us-west-2"))
    args = parser.parse_args()
    if args.command != "list" and not args.email:
        parser.error(f"{args.command} needs an email address")

    try:
        COMMANDS[args.command](Pool(args.env, args.region), args)
    except Exception as e:
        sys.exit(f"Error: {e}")


if __name__ == "__main__":
    main()
