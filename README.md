# EDA + Datadog Auto-Remediation Demo

**Audience:** Technical  
**Platform:** Ansible Automation Platform 2.6 (built-in EDA Controller) + Datadog + AWS EC2

---

## What this demo shows

> An nginx web app goes down. Datadog detects it. Event-Driven Ansible automatically remediates — no human intervention.

**Key AAP 2.6 highlights:**
- EDA Controller built into the platform (no separate install)
- Rulebook Activations run as managed services
- EDA calls AAP Job Templates — full audit trail in the AAP Jobs view
- One platform: automation + event response + RBAC + logging

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
    │  process check: nginx master process count = 0
    ▼
Datadog Monitor fires
    │  webhook POST
    ▼
EDA Controller (AAP 2.6)
    │  rulebook: alert_transition == "Triggered" → run_job_template
    ▼
AAP Job Template: "Restart nginx"
    │  ansible.builtin.service: state=started
    ▼
nginx UP — remediation complete
```

---

## Pre-demo setup (do this before you go on stage)

### 1. Provision an EC2 instance

- AMI: **Amazon Linux 2023**
- Type: `t3.small` or larger
- Security group inbound rules:
  - Port `22` — from your AAP controller IP
  - Port `80` — from `0.0.0.0/0` (public demo)
- Tag the instance: `Name=eda-demo-host`
- Create or reuse an SSH key pair; put the `.pem` in `~/.ssh/demo-key.pem`

### 2. Update the inventory

Edit `ansible/inventory.yml` and replace `<EC2_PUBLIC_IP>` with the real IP.

### 3. Configure the demo host (run once via AAP or CLI)

```bash
# Store your Datadog API key in Ansible Vault or AAP credential
ansible-playbook -i ansible/inventory.yml \
  infrastructure/configure_demo_host.yml \
  -e "dd_api_key=<YOUR_DD_API_KEY>"
```

This installs: nginx, the kill service, and the Datadog agent.

### 4. Set up AAP

#### a. Add the EC2 host to AAP inventory
- **Inventories → New → add `demo_hosts` group → add `eda-demo-host` host**
- Attach the SSH machine credential (the `.pem` key)

#### b. Create the Job Template
- **Templates → Job Templates → New**
  - Name: `Restart nginx`
  - Inventory: `EDA Demo Inventory`
  - Playbook: `ansible/restart_nginx.yml`
  - Credentials: SSH machine credential for the EC2 host
  - ✅ Enable "Prompt on launch" for extra vars (EDA passes alert context)

#### c. Upload the EDA Rulebook
- **EDA → Rulebooks → Create rulebook collection** (or link to the SCM repo containing `eda/demo_rulebook.yml`)
- Create a **Rulebook Activation**:
  - Rulebook: `demo_rulebook.yml`
  - AAP URL + credentials: point to your AAP instance
  - Status should show **Running**
- Copy the **Webhook URL** from the Activation detail page (you'll need it for Datadog)

### 5. Set up Datadog

```bash
pip install datadog-api-client

export DD_API_KEY=<your-api-key>
export DD_APP_KEY=<your-app-key>
export EDA_WEBHOOK_URL=<webhook-url-from-eda-activation>

python3 monitoring/setup_datadog_monitor.py
```

This creates:
- A **Webhook integration** named `eda-remediation` pointing at EDA
- A **Process monitor** on `eda-demo-host` — alerts when nginx master process disappears

**Tune for demo speed (in Datadog UI):**
- Monitor → Edit → Evaluation window: `Last 1 minute`
- No-data threshold: off
- Re-alert: off

---

## Demo script (live, ~90 seconds)

### Setup view
Open three browser tabs before going on stage:
1. **Tab 1:** `http://<EC2_PUBLIC_IP>` — the demo web app
2. **Tab 2:** Datadog → Monitors → `[EDA Demo] nginx process down`
3. **Tab 3:** AAP → EDA → Rulebook Activations → your activation

---

**Step 1 — Show the running app (Tab 1)**

> *"Here's a simple nginx app running on AWS EC2. You can see the uptime counter, it's returning HTTP 200 — everything is healthy."*

Point to the architecture flow on the page.

> *"The Datadog Agent is running on this host, monitoring the nginx process. The EDA Controller in AAP 2.6 has a Rulebook Activation running that's listening for Datadog webhook events."*

---

**Step 2 — Kill it (Tab 1)**

Click the red **KILL APP** button and confirm.

> *"I've just simulated an outage — killed the nginx process via systemd. The page goes dark."*

Try to refresh — connection refused.

---

**Step 3 — Show Datadog alerting (Tab 2)**

Switch to Datadog. The monitor should transition to **Alert** state within ~30 seconds.

> *"Datadog's process check detected that nginx is no longer running on this host. The monitor transitions to Alert — and fires a webhook to the EDA Controller in AAP."*

---

**Step 4 — Show EDA receiving the event (Tab 3)**

Switch to AAP → EDA → Rulebook Activations → your activation → **Activity log**.

> *"EDA received the Datadog webhook. The rulebook matched the event — `alert_transition == Triggered` — and automatically called the 'Restart nginx' Job Template. No human intervention."*

---

**Step 5 — Show the AAP job (Tab 3 → AAP Jobs)**

Navigate to **Jobs** — you'll see `Restart nginx` running or just completed.

> *"Here's the full audit trail in AAP. The job ran the remediation playbook — `ansible.builtin.service: state=started` — and you can see exactly what happened, when, and triggered by what."*

---

**Step 6 — App is back (Tab 1)**

Refresh Tab 1 — the app is live again.

> *"The app is back up, automatically. The entire cycle — outage, detection, remediation — completed in under 90 seconds. No ticket. No pager. No on-call engineer."*

---

## Files

```
eda-datadog-demo/
├── infrastructure/
│   └── configure_demo_host.yml   # One-time EC2 setup playbook
├── web/
│   ├── index.html                # Demo HTML app with kill button
│   ├── kill_service.py           # Sidecar that stops nginx on demand
│   ├── kill.service              # systemd unit for the sidecar
│   └── nginx.conf                # nginx config (proxies /kill to sidecar)
├── monitoring/
│   ├── datadog.yaml              # Datadog agent config
│   ├── process_check.yaml        # Datadog process check for nginx
│   └── setup_datadog_monitor.py  # Script to create monitor + webhook via API
├── eda/
│   └── demo_rulebook.yml         # EDA rulebook — matches Datadog alerts
└── ansible/
    ├── inventory.yml             # Demo inventory (update with EC2 IP)
    └── restart_nginx.yml         # Remediation playbook (Job Template)
```

---

## Timing expectations

| Event | Expected time |
|---|---|
| Click "Kill App" → nginx stops | < 1 second |
| Datadog detects missing process | 15–30 seconds |
| Datadog webhook fires to EDA | Immediate on alert |
| EDA matches rule, triggers job | < 5 seconds |
| AAP job runs, nginx starts | 10–15 seconds |
| **Total outage-to-recovery** | **~60–90 seconds** |

> **Demo tip:** If 60 seconds feels long on stage, start the kill at the beginning of your EDA explanation slide — by the time you switch back to the browser, it's already remediating.

---

## Troubleshooting

**Kill button returns 502 Bad Gateway**  
Kill service sidecar isn't running: `sudo systemctl status kill-service`

**Datadog monitor stays green after killing nginx**  
Check the Datadog agent is running: `sudo systemctl status datadog-agent`  
Verify process check: `sudo datadog-agent check process`

**EDA not receiving webhook**  
Confirm the Rulebook Activation is in **Running** state in AAP.  
Verify the webhook URL in Datadog matches the EDA activation URL.  
Check EDA activation logs for incoming events.

**AAP job fails with SSH error**  
Confirm the machine credential in the Job Template has the right private key.  
Verify port 22 is open in the EC2 security group from the AAP controller IP.
