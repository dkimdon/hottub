#!/bin/sh
# Run the Ruby operator every two minutes under Termux on the Android device
# by the tub.  Replaces termux-loop.sh from the old system.
#
# Settings live outside the repository, in ~/hottub-operator.env:
#
#     export HOTTUB_API_URL=https://....execute-api.us-west-2.amazonaws.com
#     export HOTTUB_OPERATOR_KEY=....
#
# (chmod 600 that file: it holds the operator key.)
#
# Any arguments are passed to the operator, e.g.:  sh run-termux.sh --report-only

termux-wake-lock

. "$HOME/hottub-operator.env"
cd "$(dirname "$0")" || exit 1

LOG="$HOME/hottub-operator.log"

while true; do
    # Keep one old log; start a new one at about 1 MB.
    if [ -f "$LOG" ] && [ "$(wc -c < "$LOG")" -gt 1000000 ]; then
        mv "$LOG" "$LOG.1"
    fi

    # The bwa library has no timeouts of its own, so cap each cycle.  A cycle
    # normally takes a few seconds.
    timeout -k 10s 90s ruby hottub_operator.rb "$@" >> "$LOG" 2>&1

    sleep 120
done
