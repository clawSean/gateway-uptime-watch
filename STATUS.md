# Status

Operational (2026-09-30). One VPS systemd timer runs every minute, outside
OpenClaw. ClawPop Tailscale ping and tailnet-only Gateway `/readyz` were
verified. The initial and next scheduled service runs were healthy. Five
state-machine tests passed. A labeled direct-Twilio test SMS reached the
`delivered` state. No live outage or Gateway restart was induced.

Canonical source: this project. VPS artifact: `/opt/gateway-uptime-watch/`;
systemd unit/timer `gateway-uptime-watch`. Encrypted Twilio credential and
private deployment config are held on the VPS outside this repository.

Next: observe genuine incidents and tune only if measured false alerts occur.
