#!/bin/sh
# Keep the operator running under Termux on the Android device by the tub.
#
# Settings live outside the repository, in ~/hottub-operator.env:
#
#     export HOTTUB_API_URL=https://....execute-api.us-west-2.amazonaws.com
#     export HOTTUB_OPERATOR_KEY=....
#     export HOTTUB_LOG_FILE=$HOME/hottub-operator.log
#
# (chmod 600 that file: it holds the operator key.)

termux-wake-lock

. "$HOME/hottub-operator.env"
cd "$(dirname "$0")" || exit 1

# The operator loops by itself; this loop only restarts it if it ever exits.
while true; do
    python3 hottub_operator.py "$@"
    sleep 30
done
