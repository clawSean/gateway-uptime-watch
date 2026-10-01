# Gateway Uptime Watch

![Python](https://img.shields.io/badge/Python-3.12-blue)
![systemd](https://img.shields.io/badge/systemd-timer-blue)

A single systemd timer on an external Linux host checks Mac reachability over
Tailscale, then OpenClaw Gateway `/readyz`. If ClawPop is unreachable for 10
minutes, or ClawPop is reachable but Gateway is unhealthy for 5 minutes, it
sends one direct Twilio SMS. It also sends one recovery message. Gateway alerts
are suppressed while the Mac cannot be reached. No OpenClaw cron, Gateway SMS
channel, or Gateway process is used by the watcher.

## Layout

- `watchdog.py`: stdlib-only probe, persisted state machine, direct Twilio sender.
- `config.example.json`: nonsecret deployment config template.
- `gateway-uptime-watch.{service,timer}`: one-minute systemd schedule.
- `test_watchdog.py`: threshold, suppression, recovery, and retry tests.

The live config belongs at `/etc/gateway-uptime-watch/config.json`, outside this
repository. Twilio credentials are read from a systemd encrypted credential
(`twilio.json`); never put them in config, the repository, process arguments,
or journal. The encrypted credential has keys `account_sid`, `auth_token`,
`from_number`, and `to_number`.

## Deployment

1. Install `watchdog.py` under `/opt/gateway-uptime-watch/` and the unit files
   under `/etc/systemd/system/` on the external host. Create a dedicated
   unprivileged `gateway-uptime-watch` user.
2. Create `/etc/gateway-uptime-watch/config.json` from the example, with the
   tailnet hostname and a tailnet-only Gateway health URL. Restrict the file to
   root and the watcher group.
3. Provision `twilio.json` using `systemd-creds encrypt -H --name=twilio.json`
   into `/etc/credstore.encrypted/gateway-uptime-watch/twilio.json`. Pipe the
   plaintext JSON from the secret manager directly into that command—never
   create a plaintext credential file.
4. Run `systemd-analyze verify` on both units, then `systemctl daemon-reload`
   and `systemctl enable --now gateway-uptime-watch.timer`.

The source project is canonical. The `/opt` copy is a deployed artifact;
compare its checksum with `watchdog.py` after each release.

## Verify

Run `python3 -m unittest -v`. On the VPS, inspect
`systemctl status gateway-uptime-watch.timer` and
`journalctl -u gateway-uptime-watch.service`. The probe never restarts or
repairs OpenClaw. `--test-sms` sends a labeled test text but does not alter
incident state.

An external watcher cannot alert if its own VPS, Twilio, or the wider network
is unavailable. A failed Tailscale probe means “Mac unreachable **from the
VPS**,” not a diagnosis of the battery or internet connection. Do not simulate
an outage by stopping the live Gateway; use the state-machine tests instead.
