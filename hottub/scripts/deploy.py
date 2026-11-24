#!/usr/bin/env python3
"""Deploy the hot tub system to AWS.

    python scripts/deploy.py stack test     # AWS resources and API code
    python scripts/deploy.py ui test        # build and publish the web UI
    python scripts/deploy.py all test       # both, in that order
    python scripts/deploy.py outputs test   # show URLs and IDs
    python scripts/deploy.py operator-key test   # print the operator's key
    python scripts/deploy.py ui-config test      # point a local "npm run dev" at test
    python scripts/deploy.py shared test    # certificate + email identity (see below)

Use "live" instead of "test" for the environment people actually use.

"shared" sets up the two things both environments share, and prints the DNS
records that have to be added by whoever manages the domain:
  * a TLS certificate for the live UI's domain name (stack hottub-certificate,
    always in us-east-1, as CloudFront requires); test has no domain name
  * an SES identity so emails come from our own domain (stack hottub-email)
Run it again at any time to see whether the DNS records have taken effect.
Until they have, "stack" still works: the UI is served at its CloudFront
address and emails come from Cognito's built-in sender.  Once they have, the
next "stack" deploy picks them up automatically.  (The environment argument
is ignored by "shared".)

Requires the AWS CLI (configured with credentials) and, for the UI, Node.js.
The region defaults to us-west-2; override with --region or HOTTUB_REGION.

What "stack" does:
  1. Creates the S3 bucket that holds packaged Lambda code, if missing.
  2. Creates the operator's shared key, if missing, and keeps it in SSM
     Parameter Store as /hottub/<env>/operator-key (encrypted).
  3. Packages api/function and deploys infra/template.yaml as the
     CloudFormation stack hottub-<env>.
"""

import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "infra" / "template.yaml"
FUNCTION_DIR = ROOT / "api" / "function"
UI_DIR = ROOT / "ui"

# The UI's own domain name in each environment.
# Live only: test is a sandbox, served at its CloudFront address.
DOMAINS = {"live": "hottub.cohoecovillage.org"}
# Invitations and password-reset codes are sent from this address.
EMAIL_DOMAIN = "cohoecovillage.org"
EMAIL_FROM = "hottub@cohoecovillage.org"
# CloudFront only accepts certificates issued in this region.
CERTIFICATE_REGION = "us-east-1"


def run(command, cwd=None, capture=False, check=True):
    """Run a command; return its stdout (stripped) if capture is set."""
    executable = shutil.which(command[0])
    if executable is None:
        sys.exit(f"Cannot find '{command[0]}' on PATH")
    result = subprocess.run(
        [executable, *command[1:]],
        cwd=cwd,
        check=False,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )
    if check and result.returncode != 0:
        if capture:
            sys.stderr.write(result.stderr)
        sys.exit(f"Command failed: {' '.join(command[:4])} ...")
    if capture:
        return result.stdout.strip() if result.returncode == 0 else None
    return None


def aws(*args, **kwargs):
    return run(["aws", *args], **kwargs)


def stack_outputs(env):
    raw = aws(
        "cloudformation", "describe-stacks", "--stack-name", f"hottub-{env}",
        "--query", "Stacks[0].Outputs", "--output", "json",
        capture=True, check=False,
    )
    if raw is None:
        sys.exit(f"Stack hottub-{env} not found. Run: deploy.py stack {env}")
    return {o["OutputKey"]: o["OutputValue"] for o in json.loads(raw)}


def operator_key_name(env):
    return f"/hottub/{env}/operator-key"


def get_operator_key(env, create=False):
    key = aws(
        "ssm", "get-parameter", "--name", operator_key_name(env), "--with-decryption",
        "--query", "Parameter.Value", "--output", "text",
        capture=True, check=False,
    )
    if key:
        return key
    if not create:
        sys.exit(f"No operator key for {env} yet. Run: deploy.py stack {env}")
    print(f"==> Creating operator key {operator_key_name(env)}")
    key = secrets.token_hex(32)
    aws(
        "ssm", "put-parameter", "--name", operator_key_name(env),
        "--type", "SecureString", "--value", key,
        "--description", f"Shared secret for the hot tub operator ({env})",
        capture=True,
    )
    return key


def aws_json(*args, **kwargs):
    """Run an AWS CLI command and parse its JSON output; None if it failed."""
    raw = aws(*args, "--output", "json", capture=True, check=False, **kwargs)
    return json.loads(raw) if raw else None


def our_certificate():
    """(arn, detail) of the certificate in stack hottub-certificate, or (None, None).

    Only this one is used: other certificates for the same name may exist in
    the account (the old system had one) and are not ours to depend on.
    """
    arn = aws(
        "cloudformation", "describe-stack-resource", "--region", CERTIFICATE_REGION,
        "--stack-name", "hottub-certificate", "--logical-resource-id", "Certificate",
        "--query", "StackResourceDetail.PhysicalResourceId", "--output", "text",
        capture=True, check=False,
    )
    if not arn or not arn.startswith("arn:"):
        return None, None
    detail = aws_json(
        "acm", "describe-certificate", "--region", CERTIFICATE_REGION,
        "--certificate-arn", arn, "--query", "Certificate",
    )
    return (arn, detail) if detail else (None, None)


def find_certificate(domain):
    """ARN of our certificate if it is issued and covers `domain`, else None."""
    arn, detail = our_certificate()
    if detail and detail.get("Status") == "ISSUED" and domain in detail.get("SubjectAlternativeNames", []):
        return arn
    return None


def email_identity():
    """ARN of the SES identity if it is verified and ready to send, else None.

    Also None while the account's SES is in sandbox mode: there it only
    delivers to individually verified addresses, so switching Cognito to it
    would silently stop invitations reaching new users.
    """
    identity = aws_json("sesv2", "get-email-identity", "--email-identity", EMAIL_DOMAIN)
    if not identity or not identity.get("VerifiedForSendingStatus"):
        return None
    if not (aws_json("sesv2", "get-account") or {}).get("ProductionAccessEnabled"):
        return None
    account = aws("sts", "get-caller-identity", "--query", "Account", "--output", "text",
                  capture=True)
    return f"arn:aws:ses:{os.environ['AWS_DEFAULT_REGION']}:{account}:identity/{EMAIL_DOMAIN}"


def deploy_shared():
    print("==> Email identity (stack hottub-email)")
    aws(
        "cloudformation", "deploy",
        "--template-file", str(ROOT / "infra" / "email.yaml"),
        "--stack-name", "hottub-email",
        "--no-fail-on-empty-changeset",
        "--parameter-overrides", f"EmailDomain={EMAIL_DOMAIN}",
    )

    print("==> Certificate (stack hottub-certificate, us-east-1)")
    exists = aws(
        "cloudformation", "describe-stacks", "--region", CERTIFICATE_REGION,
        "--stack-name", "hottub-certificate", "--query", "Stacks[0].StackStatus",
        "--output", "text", capture=True, check=False,
    )
    if exists is None:
        # Not "deploy": that would wait, possibly for days, until the
        # validation records below are in DNS.
        aws(
            "cloudformation", "create-stack", "--region", CERTIFICATE_REGION,
            "--stack-name", "hottub-certificate",
            "--template-body", (ROOT / "infra" / "certificate.yaml").read_text(),
            "--parameters",
            f"ParameterKey=LiveDomainName,ParameterValue={DOMAINS['live']}",
            capture=True,
        )
        print("    Requested. Run this command again in a minute to see its DNS records.")

    show_shared()


def show_shared():
    """Print the DNS records still needed, and whether each part is ready."""
    print()
    print("DNS records needed (give these to whoever manages the domain):")
    print()

    print("  1. Certificate validation")
    _arn, detail = our_certificate()
    if detail:
        print(f"     Certificate: {detail.get('Status')}")
        for option in detail.get("DomainValidationOptions", []):
            record = option.get("ResourceRecord")
            status = option.get("ValidationStatus", "?")
            if record:
                print(f"     [{status}] {record['Name']} {record['Type']} {record['Value']}")
            else:
                print(f"     [{status}] {option['DomainName']}: record not available yet")
    else:
        print("     No certificate found yet; run this command again in a minute.")

    print()
    print("  2. Email (DKIM)")
    outputs = aws_json(
        "cloudformation", "describe-stacks", "--stack-name", "hottub-email",
        "--query", "Stacks[0].Outputs",
    ) or []
    for output in outputs:
        if output["OutputKey"].startswith("DkimRecord"):
            print(f"     {output['OutputValue']}")
    identity = aws_json("sesv2", "get-email-identity", "--email-identity", EMAIL_DOMAIN) or {}
    verified = identity.get("VerifiedForSendingStatus")
    print(f"     Status: {'verified' if verified else 'waiting for these records'}")
    account = aws_json("sesv2", "get-account") or {}
    if not account.get("ProductionAccessEnabled"):
        print("     NOTE: this AWS account's SES is in sandbox mode. Until AWS grants")
        print("     production access (requested in the SES console), SES only delivers")
        print("     to addresses that have themselves been verified.")

    print()
    print("  3. The UI's own names (after the stacks are deployed with them)")
    for env, domain in DOMAINS.items():
        target = (aws_json(
            "cloudformation", "describe-stacks", "--stack-name", f"hottub-{env}",
            "--query", "Stacks[0].Outputs[?OutputKey=='UiCloudFrontDomain'].OutputValue",
        ) or [None])[0]
        print(f"     {domain} CNAME {target or '(deploy the ' + env + ' stack first)'}")
    print()


def deploy_stack(env, region, use_domain=True):
    account = aws("sts", "get-caller-identity", "--query", "Account", "--output", "text",
                  capture=True)
    bucket = f"hottub-deploy-{account}-{region}"

    if aws("s3api", "head-bucket", "--bucket", bucket, capture=True, check=False) is None:
        print(f"==> Creating deployment bucket {bucket}")
        create = ["s3api", "create-bucket", "--bucket", bucket]
        if region != "us-east-1":
            create += ["--create-bucket-configuration", f"LocationConstraint={region}"]
        aws(*create, capture=True)

    key = get_operator_key(env, create=True)

    # Use our own domain name and email sender when they are ready; otherwise
    # deploy without them.  Every parameter is passed every time, because
    # CloudFormation otherwise keeps whatever value the last deploy used.
    certificate = find_certificate(DOMAINS[env]) if use_domain and env in DOMAINS else None
    identity = email_identity()
    if certificate:
        print(f"==> UI will be served at https://{DOMAINS[env]}")
    else:
        print("==> No domain name of our own this time; the UI gets a CloudFront address")
    if identity:
        print(f"==> Emails will be sent from {EMAIL_FROM}")
    else:
        print("==> SES is not ready; emails will come from Cognito's built-in sender")
    parameters = [
        f"Environment={env}",
        f"OperatorKey={key}",
        f"UiDomainName={DOMAINS[env] if certificate else ''}",
        f"UiCertificateArn={certificate or ''}",
        f"EmailFrom={EMAIL_FROM if identity else ''}",
        f"EmailIdentityArn={identity or ''}",
    ]

    # Compiled files would change the package's fingerprint for no reason.
    for cache in FUNCTION_DIR.rglob("__pycache__"):
        shutil.rmtree(cache)

    with tempfile.TemporaryDirectory() as tmp:
        packaged = str(Path(tmp) / "packaged.yaml")
        print("==> Packaging Lambda code")
        aws(
            "cloudformation", "package",
            "--template-file", str(TEMPLATE),
            "--s3-bucket", bucket, "--s3-prefix", f"hottub-{env}",
            "--output-template-file", packaged,
            capture=True,
        )
        print(f"==> Deploying stack hottub-{env} (a first deploy takes several minutes)")
        aws(
            "cloudformation", "deploy",
            "--template-file", packaged,
            "--stack-name", f"hottub-{env}",
            "--capabilities", "CAPABILITY_IAM",
            "--no-fail-on-empty-changeset",
            "--parameter-overrides", *parameters,
        )
    show_outputs(env)


def deploy_ui(env):
    outputs = stack_outputs(env)

    if not (UI_DIR / "node_modules").exists():
        print("==> Installing UI dependencies")
        run(["npm", "ci"], cwd=UI_DIR)
    print("==> Building UI")
    run(["npm", "run", "build"], cwd=UI_DIR)

    dist = UI_DIR / "dist"
    write_ui_config(env, dist, outputs)

    target = f"s3://{outputs['UiBucketName']}"
    print(f"==> Uploading to {target}")
    # Files under assets/ have a fingerprint in their name and can be cached
    # forever; the two entry files must always be fetched fresh.
    aws("s3", "sync", str(dist), target, "--delete",
        "--exclude", "index.html", "--exclude", "config.json",
        "--cache-control", "public,max-age=31536000,immutable")
    for name in ("index.html", "config.json"):
        aws("s3", "cp", str(dist / name), f"{target}/{name}", "--cache-control", "no-cache")
    aws("cloudfront", "create-invalidation", "--distribution-id", outputs["UiDistributionId"],
        "--paths", "/index.html", "/config.json", "/", capture=True)
    print(f"==> UI is at {outputs['UiUrl']}")


def write_ui_config(env, directory, outputs=None):
    """Write config.json, which tells the UI which backend it is talking to.

    The same UI build serves every environment; only this file differs.
    """
    outputs = outputs or stack_outputs(env)
    directory.mkdir(exist_ok=True)
    (directory / "config.json").write_text(json.dumps({
        "environment": env,
        "apiUrl": outputs["ApiUrl"],
        "userPoolId": outputs["UserPoolId"],
        "userPoolClientId": outputs["UserPoolClientId"],
    }, indent=2))


def show_outputs(env):
    outputs = stack_outputs(env)
    print()
    for name in sorted(outputs):
        print(f"  {name:<18} {outputs[name]}")
    print()
    print(f"  The operator needs HOTTUB_API_URL={outputs['ApiUrl']}")
    print(f"  and HOTTUB_OPERATOR_KEY from: deploy.py operator-key {env}")


def main():
    parser = argparse.ArgumentParser(description="Deploy the hot tub system")
    parser.add_argument(
        "action",
        choices=["stack", "ui", "all", "outputs", "operator-key", "ui-config", "shared"],
    )
    parser.add_argument(
        "--no-domain", action="store_true",
        help="serve the UI at its CloudFront address even if a certificate exists "
             "(needed for live while the old system still holds the domain name)",
    )
    parser.add_argument("env", choices=["test", "live"])
    parser.add_argument("--region", default=os.environ.get("HOTTUB_REGION", "us-west-2"))
    parser.add_argument("--yes", action="store_true", help="do not ask before changing live")
    args = parser.parse_args()

    # Every AWS CLI call below inherits this, so nothing lands in another region.
    os.environ["AWS_DEFAULT_REGION"] = args.region
    os.environ["AWS_REGION"] = args.region

    changes_live = args.env == "live" and args.action in ("stack", "ui", "all")
    if changes_live and not args.yes:
        if input("This changes the LIVE system. Type 'live' to continue: ").strip() != "live":
            sys.exit("Cancelled")

    if args.action == "shared":
        deploy_shared()
    if args.action in ("stack", "all"):
        deploy_stack(args.env, args.region, use_domain=not args.no_domain)
    if args.action in ("ui", "all"):
        deploy_ui(args.env)
    if args.action == "outputs":
        show_outputs(args.env)
    if args.action == "operator-key":
        print(get_operator_key(args.env))
    if args.action == "ui-config":
        write_ui_config(args.env, UI_DIR / "public")
        print(f"Wrote ui/public/config.json for {args.env}; now run: npm run dev (in ui/)")


if __name__ == "__main__":
    main()
