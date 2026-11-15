#!/usr/bin/env bash
# Deploy the hottub API CloudFormation stack.
#
# Usage:
#   ./scripts/deploy.sh test
#   ./scripts/deploy.sh live
#
# Prerequisites:
#   - AWS CLI configured with appropriate credentials
#   - An S3 bucket for Lambda code (created automatically if absent)
#
# The script will:
#   1. Create the S3 bucket if it doesn't exist
#   2. Zip and upload the Lambda function code
#   3. Deploy (or update) the CloudFormation stack
#
# After first deploy, print all stack outputs including how to retrieve
# the operator API key value.

set -euo pipefail

ENV="${1:-}"
if [[ "$ENV" != "test" && "$ENV" != "live" ]]; then
  echo "Usage: $0 <test|live>" >&2
  exit 1
fi

STACK_NAME="hottub-${ENV}"
REGION="${AWS_DEFAULT_REGION:-us-east-1}"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
S3_BUCKET="hottub-deploy-${ACCOUNT_ID}-${REGION}"
S3_KEY="${STACK_NAME}.zip"
TEMPLATE="$(dirname "$0")/../cloudformation/template.yaml"
LAMBDA_DIR="$(dirname "$0")/../lambda"
ZIP_FILE="/tmp/${S3_KEY}"

echo "==> Environment : ${ENV}"
echo "==> Stack       : ${STACK_NAME}"
echo "==> Region      : ${REGION}"
echo "==> S3 bucket   : ${S3_BUCKET}"

# 1. Ensure S3 bucket exists
if ! aws s3api head-bucket --bucket "${S3_BUCKET}" 2>/dev/null; then
  echo "==> Creating S3 bucket ${S3_BUCKET}"
  if [[ "$REGION" == "us-east-1" ]]; then
    aws s3api create-bucket --bucket "${S3_BUCKET}" --region "${REGION}"
  else
    aws s3api create-bucket --bucket "${S3_BUCKET}" --region "${REGION}" \
      --create-bucket-configuration LocationConstraint="${REGION}"
  fi
  aws s3api put-bucket-versioning --bucket "${S3_BUCKET}" \
    --versioning-configuration Status=Enabled
fi

# 2. Package Lambda
echo "==> Packaging Lambda"
(cd "${LAMBDA_DIR}" && zip -qr "${ZIP_FILE}" .)
aws s3 cp "${ZIP_FILE}" "s3://${S3_BUCKET}/${S3_KEY}"
rm "${ZIP_FILE}"

# 3. Deploy CloudFormation
echo "==> Deploying CloudFormation stack ${STACK_NAME}"
aws cloudformation deploy \
  --template-file "${TEMPLATE}" \
  --stack-name "${STACK_NAME}" \
  --region "${REGION}" \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    Environment="${ENV}" \
    LambdaS3Bucket="${S3_BUCKET}" \
    LambdaS3Key="${S3_KEY}"

# 4. Print outputs
echo ""
echo "==> Stack outputs:"
aws cloudformation describe-stacks \
  --stack-name "${STACK_NAME}" \
  --region "${REGION}" \
  --query 'Stacks[0].Outputs[*].[OutputKey,OutputValue]' \
  --output table

# 5. Print the operator API key value
KEY_ID=$(aws cloudformation describe-stacks \
  --stack-name "${STACK_NAME}" \
  --region "${REGION}" \
  --query "Stacks[0].Outputs[?OutputKey=='OperatorApiKeyId'].OutputValue" \
  --output text)

KEY_VALUE=$(aws apigateway get-api-key \
  --api-key "${KEY_ID}" \
  --include-value \
  --query value \
  --output text)

echo ""
echo "==> Operator API key value (store this securely):"
echo "    ${KEY_VALUE}"
