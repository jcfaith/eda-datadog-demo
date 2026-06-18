# EDA + Datadog Auto-Remediation Demo

**Stack:** Ansible Automation Platform 2.6 · Event-Driven Ansible · Datadog · AWS EC2

---

## Overview

This project demonstrates closed-loop auto-remediation using Event-Driven Ansible and Datadog. An nginx web application runs on AWS EC2 with a built-in kill button to simulate a failure. When the process goes down, Datadog detects it, fires a webhook to the EDA Controller in AAP 2.6, and the platform automatically restarts nginx — no human intervention required.

**Key AAP 2.6 capabilities shown:**
- EDA Controller built into AAP — no separate install or sidecar
- Rulebook Activations run as platform-managed services
- EDA calls AAP Job Templates directly — full audit trail in the Jobs view
- One platform: event response + automation + RBAC + logging

---

## Architecture

```
Browser (Kill button)
    │  POST /kill
    ▼
nginx (EC2 :80)  ──proxy──▶  Kill Service sidecar (:8080)
    │                               │
    │ systemctl stop nginx ◀────────┘
    ▼
nginx DOWN

Datadog Agent (on EC2)
    │  process check: nginx count = 0  →  alert_type: "error"
    ▼
Datadog Monitor fires
    │  webhook POST (Basic auth)
    ▼
EDA Controller (AAP 2.6)
    │  rulebook: alert_type == "error" → run_job_template
    ▼
AAP Job Template: "Restart nginx"
    │  ansible.builtin.service: state=started
    ▼
nginx UP — remediation complete
```

---

## Setup

### 1. Provision an EC2 instance

- AMI: **Amazon Linux 2023**
- Instance type: `t3.small` or larger
- Security group inbound rules:
  - Port `22` — from your AAP controller IP
  - Port `80` — from `0.0.0.0/0`
- Tag: `Name=eda-demo-host`
- Generate an SSH key pair for Ansible access

### 2. Configure the EC2 host

Update `ansible/inventory.yml` with the EC2 public IP, then run:

```bash
ansible-playbook -i ansible/inventory.yml \
  infrastructure/configure_demo_host.yml \
  -e "dd_api_key=<YOUR_DD_API_KEY>"
```

This installs nginx, the kill service sidecar, and the Datadog agent with the process check configured.

### 3. Set up AAP

#### Inventory
- Create an inventory and add the EC2 host with `ansible_host` set to its public IP
- Attach an SSH machine credential with the EC2 private key

#### Job Template
- **Name:** `Restart nginx`
- **Playbook:** `ansible/restart_nginx.yml`
- **Inventory:** the inventory created above
- **Credentials:** the SSH machine credential
- Enable **Prompt on launch** for extra vars (EDA passes alert context at runtime)

#### EDA Project & Rulebook Activation
- Create an EDA project pointing at this repository
- Create a **Rulebook Activation** using `demo_rulebook.yml`
- Create an **Event Stream** with a Basic auth credential (username/password of your choice)
- Link the event stream to the activation via source mappings
- Note the generated **Event Stream webhook URL** — needed for Datadog

### 4. Set up Datadog

#### Webhook integration
- Go to **Integrations → Webhooks → New**
- URL: the EDA event stream webhook URL
- Custom header: `Authorization: Basic <base64(username:password)>`
- Payload:

```json
{
    "id": "$ID",
    "last_updated": "$LAST_UPDATED",
    "hostname": "$HOSTNAME",
    "event_type": "$EVENT_TYPE",
    "event_title": "$EVENT_TITLE",
    "alert_title": "$ALERT_TITLE",
    "alert_status": "$ALERT_STATUS",
    "alert_type": "$ALERT_TYPE",
    "metric": "$ALERT_METRIC",
    "date": "$DATE",
    "event_link": "$LINK",
    "org": {
        "id": "$ORG_ID",
        "name": "$ORG_NAME"
    },
    "body": "$EVENT_MSG"
}
```

#### Process monitor
- **Type:** Service Check → `process.up`
- **Scope:** `host:eda-demo-host`, `process:nginx`
- **Alert condition:** Critical when check fails
- **Notification message:** include `@webhook-<your-webhook-name>`

> **Note:** Use `alert_type` (not `alert_status`) in your EDA rulebook condition. For service check monitors, Datadog populates `$ALERT_TYPE` (`error` on alert, `success` on recovery) but leaves `$ALERT_STATUS` empty.

---

## How it works

1. Open the web app in a browser — the page shows live uptime and the architecture flow
2. Click **KILL APP** — the kill service sidecar runs `systemctl stop nginx`
3. The page goes dark (connection refused)
4. Datadog's process check detects nginx is gone within ~30 seconds and fires the webhook
5. EDA Controller receives the event, matches the rule (`alert_type == "error"`), and calls the `Restart nginx` Job Template
6. AAP runs the remediation playbook — nginx is restarted
7. The app comes back up automatically

---

## Timing

| Event | Expected time |
|---|---|
| Kill App → nginx stops | < 1 second |
| Datadog detects missing process | 15–30 seconds |
| Datadog webhook fires to EDA | Immediate on alert |
| EDA matches rule, triggers job | < 5 seconds |
| AAP job runs, nginx starts | 10–15 seconds |
| **Total outage-to-recovery** | **~60–90 seconds** |

---

## Repository structure

```
eda-datadog-demo/
├── infrastructure/
│   └── configure_demo_host.yml          # One-time EC2 setup playbook
├── web/
│   ├── index.html                        # Web app with kill button
│   ├── kill_service.py                   # Sidecar: stops nginx on POST /kill
│   ├── kill.service                      # systemd unit for the sidecar
│   └── nginx.conf                        # nginx config (proxies /kill to sidecar)
├── monitoring/
│   ├── datadog.yaml                      # Datadog agent config template
│   ├── process_check.yaml                # Datadog process check for nginx
│   └── setup_datadog_monitor.py          # Script to create monitor + webhook via API
├── extensions/
│   └── eda/
│       └── rulebooks/
│           └── demo_rulebook.yml         # EDA rulebook (alert_type == error → restart)
└── ansible/
    ├── inventory.yml                     # Inventory template
    └── restart_nginx.yml                 # Remediation playbook (AAP Job Template)
```

---

## Troubleshooting

**Kill button returns 502 Bad Gateway**
The kill service sidecar is not running. Check with:
```bash
sudo systemctl status kill-service
```

**Datadog monitor stays in Alert after nginx is restarted**
Verify the Datadog agent is running and the process check is reporting OK:
```bash
sudo systemctl status datadog-agent
sudo datadog-agent check process
```

**EDA not receiving Datadog webhooks**
- Confirm the Rulebook Activation is in **Running** state in AAP
- Verify the webhook URL in Datadog matches the EDA event stream URL
- Check EDA activation logs for incoming events and rule matches
- Ensure the `Authorization` header value matches the event stream credential

**AAP job skips all hosts**
The playbook uses `hosts: all` — ensure the inventory has at least one host and the Job Template is pointing at the correct inventory.

**AAP job fails with SSH error**
- Confirm the machine credential in the Job Template contains the correct private key
- Verify port 22 on the EC2 security group allows inbound traffic from the AAP controller IP
