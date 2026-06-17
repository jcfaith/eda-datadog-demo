#!/usr/bin/env python3
"""
Creates the Datadog monitor and webhook integration for the EDA demo.
Run once from your laptop before the demo.

Requirements:
    pip install datadog-api-client

Usage:
    export DD_API_KEY=<your-api-key>
    export DD_APP_KEY=<your-app-key>
    export EDA_WEBHOOK_URL=https://<your-aap-host>/api/eda/v1/external_event_stream/
    python3 setup_datadog_monitor.py
"""

import os
import sys
import json

try:
    from datadog_api_client import ApiClient, Configuration
    from datadog_api_client.v1.api.monitors_api import MonitorsApi
    from datadog_api_client.v1.api.webhooks_integration_api import WebhooksIntegrationApi
    from datadog_api_client.v1.model.monitor import Monitor
    from datadog_api_client.v1.model.monitor_type import MonitorType
    from datadog_api_client.v1.model.monitor_options import MonitorOptions
    from datadog_api_client.v1.model.webhooks_integration import WebhooksIntegration
except ImportError:
    print("ERROR: pip install datadog-api-client")
    sys.exit(1)

DD_API_KEY = os.environ["DD_API_KEY"]
DD_APP_KEY = os.environ["DD_APP_KEY"]
EDA_WEBHOOK_URL = os.environ["EDA_WEBHOOK_URL"]

WEBHOOK_NAME = "eda-remediation"

config = Configuration()
config.api_key["apiKeyAuth"] = DD_API_KEY
config.api_key["appKeyAuth"] = DD_APP_KEY


def create_webhook(client):
    api = WebhooksIntegrationApi(client)
    webhook = WebhooksIntegration(
        name=WEBHOOK_NAME,
        url=EDA_WEBHOOK_URL,
        # Datadog template variables — EDA rulebook parses these
        payload=json.dumps({
            "alert_id":         "$ALERT_ID",
            "alert_metric":     "$ALERT_METRIC",
            "alert_scope":      "$ALERT_SCOPE",
            "alert_status":     "$ALERT_STATUS",
            "alert_title":      "$EVENT_TITLE",
            "alert_transition": "$ALERT_TRANSITION",
            "hostname":         "$HOSTNAME",
            "tags":             "$TAGS",
            "url":              "$LINK",
        }),
        custom_headers=json.dumps({
            "Content-Type": "application/json",
        }),
        encode_as="json",
    )
    result = api.create_webhooks_integration(webhook)
    print(f"Webhook created: {result.name}")
    return result


def create_monitor(client):
    api = MonitorsApi(client)
    monitor = Monitor(
        name="[EDA Demo] nginx process down on eda-demo-host",
        type=MonitorType("process alert"),
        # Process check: alert when nginx master process count < 1
        query='processes("nginx").over("host:eda-demo-host").rollup("count").last("30s") < 1',
        message=(
            "nginx process is down on {{host.name}}. "
            "EDA is remediating. @webhook-" + WEBHOOK_NAME
        ),
        tags=["env:demo", "app:nginx-demo", "team:ansible"],
        options=MonitorOptions(
            notify_no_data=False,
            renotify_interval=0,
            # Tune for demo speed: alert on first failure
            thresholds={"critical": 1},
            new_host_delay=0,
            evaluation_delay=0,
            notify_audit=False,
            include_tags=True,
            # Re-notify when recovered so the demo shows green again
            notify_by=["*"],
        ),
    )
    result = api.create_monitor(monitor)
    print(f"Monitor created: id={result.id}  name={result.name}")
    print(f"View at: https://app.datadoghq.com/monitors/{result.id}")
    return result


if __name__ == "__main__":
    with ApiClient(config) as client:
        print("=== Creating Datadog webhook integration ===")
        create_webhook(client)
        print()
        print("=== Creating Datadog process monitor ===")
        create_monitor(client)
        print()
        print("Done. Allow 1-2 minutes for the monitor to initialize.")
        print("Verify at: https://app.datadoghq.com/monitors/manage")
