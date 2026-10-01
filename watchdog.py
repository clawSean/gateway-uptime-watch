#!/usr/bin/env python3
"""Gateway-independent ClawPop/Tailscale health monitor and SMS notifier."""

import argparse
import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def probe_mac(host, timeout):
    try:
        result = subprocess.run(
            ["/usr/bin/tailscale", "ping", "--timeout=5s", "--c=1", host],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def probe_gateway(url, timeout):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


def send_sms(creds, body):
    sid = creds["account_sid"]
    token = creds["auth_token"]
    auth = base64.b64encode(f"{sid}:{token}".encode()).decode()
    payload = urllib.parse.urlencode(
        {"From": creds["from_number"], "To": creds["to_number"], "Body": body}
    ).encode()
    request = urllib.request.Request(
        f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
        data=payload,
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            reply = json.load(response)
            if response.status != 201 or not reply.get("sid"):
                raise RuntimeError("Twilio did not confirm message creation")
            return reply["sid"]
    except urllib.error.HTTPError as exc:
        # Never log Twilio's response body: it may contain phone numbers.
        raise RuntimeError(f"Twilio HTTP {exc.code}") from None


def initial_state():
    return {
        "mac": {"down_since": None, "alerted": False},
        "gateway": {"down_since": None, "alerted": False},
    }


def load_state(path):
    try:
        data = json.loads(path.read_text())
        if not all(k in data and all(f in data[k] for f in ("down_since", "alerted"))
                   for k in ("mac", "gateway")):
            raise ValueError("missing state fields")
        return data
    except FileNotFoundError:
        return initial_state()


def save_state(path, state):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w") as handle:
        os.fchmod(handle.fileno(), 0o600)
        json.dump(state, handle, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def transition(state, now, mac_ok, gateway_ok, config, notify):
    """Mutate state; notify(message) raises on failed delivery."""
    mac = state["mac"]
    gateway = state["gateway"]
    if not mac_ok:
        if mac["down_since"] is None:
            mac["down_since"] = now
        # Gateway cannot be measured while Mac is unreachable. Do not infer it failed.
        if not gateway["alerted"]:
            gateway["down_since"] = None
        if not mac["alerted"] and now - mac["down_since"] >= config["mac_seconds"]:
            mac["alerted"] = True
            try:
                notify("ClawPop unreachable from VPS for 10+ min (power, internet, or Tailscale).")
            except Exception:
                mac["alerted"] = False
                raise
        return "mac_unreachable"

    if mac["alerted"]:
        mac["alerted"] = False
        try:
            notify("ClawPop reachable again from VPS.")
        except Exception:
            mac["alerted"] = True
            raise
    mac["down_since"] = None

    if gateway_ok:
        if gateway["alerted"]:
            gateway["alerted"] = False
            try:
                notify("OpenClaw Gateway healthy again on ClawPop.")
            except Exception:
                gateway["alerted"] = True
                raise
        gateway["down_since"] = None
        return "healthy"

    if gateway["down_since"] is None:
        gateway["down_since"] = now
    if not gateway["alerted"] and now - gateway["down_since"] >= config["gateway_seconds"]:
        gateway["alerted"] = True
        try:
            notify("OpenClaw Gateway unhealthy for 5+ min; ClawPop is reachable.")
        except Exception:
            gateway["alerted"] = False
            raise
    return "gateway_unhealthy"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--test-sms", action="store_true")
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text())
    credentials = json.loads((Path(os.environ["CREDENTIALS_DIRECTORY"]) / "twilio.json").read_text())
    if args.test_sms:
        sid = send_sms(credentials, "TEST: ClawPop/Gateway uptime watchdog SMS delivery check.")
        print(f"test_sms_created={sid}")
        return

    state_path = Path(args.state)
    state = load_state(state_path)

    def notify(message):
        sid = send_sms(credentials, message)
        print(f"sms_created={sid}")
        # Persist each completed send, so later send errors do not re-send it.
        save_state(state_path, state)

    mac_ok = probe_mac(config["mac_host"], config["probe_timeout_seconds"])
    gateway_ok = probe_gateway(config["gateway_url"], config["probe_timeout_seconds"]) if mac_ok else None
    try:
        outcome = transition(state, time.time(), mac_ok, gateway_ok, config, notify)
    finally:
        save_state(state_path, state)
    print(f"status={outcome}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Avoid repr of HTTP requests/credentials/config on failure.
        detail = f": {exc}" if isinstance(exc, RuntimeError) else ""
        print(f"watchdog_error={type(exc).__name__}{detail}", file=sys.stderr)
        sys.exit(1)
