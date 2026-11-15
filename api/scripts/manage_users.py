#!/usr/bin/env python3
"""Admin tool for managing Cognito users in a hottub stack.

Usage
-----
  # List all users
  python3 scripts/manage_users.py list test

  # Create a user (sends email with temp password)
  python3 scripts/manage_users.py create test user@example.com

  # Set (or reset) a user's password
  python3 scripts/manage_users.py set-password test user@example.com 'NewPass123'

  # Delete a user
  python3 scripts/manage_users.py delete test user@example.com
"""

import argparse
import sys
import boto3


def get_user_pool_id(env: str) -> str:
    cf = boto3.client("cloudformation")
    resp = cf.describe_stacks(StackName=f"hottub-{env}")
    outputs = resp["Stacks"][0]["Outputs"]
    for o in outputs:
        if o["OutputKey"] == "UserPoolId":
            return o["OutputValue"]
    raise RuntimeError(f"UserPoolId not found in hottub-{env} stack outputs")


def cmd_list(args):
    pool_id = get_user_pool_id(args.env)
    cognito = boto3.client("cognito-idp")
    paginator = cognito.get_paginator("list_users")
    users = []
    for page in paginator.paginate(UserPoolId=pool_id):
        users.extend(page["Users"])
    if not users:
        print("No users found.")
        return
    print(f"{'Username':<40} {'Status':<20} {'Email'}")
    print("-" * 80)
    for u in users:
        email = next(
            (a["Value"] for a in u["Attributes"] if a["Name"] == "email"), ""
        )
        print(f"{u['Username']:<40} {u['UserStatus']:<20} {email}")


def cmd_create(args):
    pool_id = get_user_pool_id(args.env)
    cognito = boto3.client("cognito-idp")
    cognito.admin_create_user(
        UserPoolId=pool_id,
        Username=args.email,
        UserAttributes=[{"Name": "email", "Value": args.email},
                        {"Name": "email_verified", "Value": "true"}],
        DesiredDeliveryMediums=["EMAIL"],
    )
    print(f"Created user {args.email}. A temporary password has been sent by email.")


def cmd_set_password(args):
    pool_id = get_user_pool_id(args.env)
    cognito = boto3.client("cognito-idp")
    cognito.admin_set_user_password(
        UserPoolId=pool_id,
        Username=args.email,
        Password=args.password,
        Permanent=True,
    )
    print(f"Password updated for {args.email}.")


def cmd_delete(args):
    pool_id = get_user_pool_id(args.env)
    cognito = boto3.client("cognito-idp")
    cognito.admin_delete_user(UserPoolId=pool_id, Username=args.email)
    print(f"Deleted user {args.email}.")


def main():
    parser = argparse.ArgumentParser(description="Manage hottub Cognito users")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="List all users")
    p_list.add_argument("env", choices=["test", "live"])

    p_create = sub.add_parser("create", help="Create a new user")
    p_create.add_argument("env", choices=["test", "live"])
    p_create.add_argument("email")

    p_pw = sub.add_parser("set-password", help="Set a user's password")
    p_pw.add_argument("env", choices=["test", "live"])
    p_pw.add_argument("email")
    p_pw.add_argument("password")

    p_del = sub.add_parser("delete", help="Delete a user")
    p_del.add_argument("env", choices=["test", "live"])
    p_del.add_argument("email")

    args = parser.parse_args()
    dispatch = {
        "list": cmd_list,
        "create": cmd_create,
        "set-password": cmd_set_password,
        "delete": cmd_delete,
    }
    try:
        dispatch[args.command](args)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
