#!/usr/bin/env python3
"""Hot tub operator — runs on the tub's network and keeps tub and cloud in step.

    python3 hottub_operator.py                 # run forever
    python3 hottub_operator.py --once          # one cycle, then exit
    python3 hottub_operator.py --report-only   # never change the tub

Configuration comes from environment variables:

    HOTTUB_API_URL        required   base URL of the API (https://...)
    HOTTUB_OPERATOR_KEY   required   the operator's shared key
    HOTTUB_SPA_IP         optional   the tub's IP address; found by UDP
                                     discovery each cycle if not set
    HOTTUB_STATE_FILE     optional   default: operator-state.json next to this file
    HOTTUB_LOG_FILE       optional   also log to this file (rotated at 1 MB)
    HOTTUB_INTERVAL       optional   seconds between cycles, default 120

See controller.py for what a cycle does.
"""

import argparse
import logging
import logging.handlers
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api_client import ApiClient, ApiError
from bwa.client import Client
from bwa.discovery import find_spa
from controller import StateFile, TubUnreachable, run_cycle

log = logging.getLogger("operator")


def make_connect(state: StateFile, fixed_ip):
    """Return a function that locates the tub and connects to it."""

    def connect():
        ip = fixed_ip or find_spa(timeout=5.0)
        saved = state.load()
        if ip is None:
            # Discovery is a UDP broadcast and is sometimes missed; the tub
            # rarely changes address, so try where it was last time.
            ip = saved.get("spa_ip")
            if ip is None:
                raise TubUnreachable("tub not found on the network")
            log.info("Discovery found nothing; trying last known address %s", ip)
        elif saved.get("spa_ip") != ip:
            state.save({**saved, "spa_ip": ip})
        return Client(ip, timeout=10.0)

    return connect


def configure_logging(log_file):
    handlers = [logging.StreamHandler()]
    if log_file:
        handlers.append(
            logging.handlers.RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=3)
        )
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
    )


def main():
    parser = argparse.ArgumentParser(description="Hot tub operator")
    parser.add_argument("--once", action="store_true", help="run one cycle and exit")
    parser.add_argument("--report-only", action="store_true",
                        help="report the tub's state but never change it")
    args = parser.parse_args()

    configure_logging(os.environ.get("HOTTUB_LOG_FILE"))

    try:
        api = ApiClient(os.environ["HOTTUB_API_URL"], os.environ["HOTTUB_OPERATOR_KEY"])
    except KeyError as e:
        sys.exit(f"Environment variable {e.args[0]} is not set")
    except ValueError as e:
        sys.exit(str(e))

    here = os.path.dirname(os.path.abspath(__file__))
    state = StateFile(os.environ.get("HOTTUB_STATE_FILE", os.path.join(here, "operator-state.json")))
    connect = make_connect(state, os.environ.get("HOTTUB_SPA_IP"))
    interval = float(os.environ.get("HOTTUB_INTERVAL", "120"))

    log.info("Operator starting%s", " (report only)" if args.report_only else "")
    while True:
        try:
            outcome = run_cycle(api, connect, state, report_only=args.report_only)
            log.info("Cycle finished: %s", outcome)
        except ApiError as e:
            log.warning("Could not talk to the API: %s", e)
        except Exception:
            # Whatever goes wrong, the loop must survive to try again.
            log.exception("Unexpected error in cycle")
        if args.once:
            break
        time.sleep(interval)


if __name__ == "__main__":
    main()
