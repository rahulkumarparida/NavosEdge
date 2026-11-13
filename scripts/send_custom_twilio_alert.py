"""
NavosEdge — Custom Twilio Alert & Surge Demo CLI

Sends a custom SMS and/or Voice Call via `/api/v1/notifications/test`,
and optionally triggers a synthetic emergency surge via
`/api/v1/emergency/demo/simulate-event`.

Usage:
  python scripts/send_custom_twilio_alert.py --to +91XXXXXXXXXX --channel BOTH
  python scripts/send_custom_twilio_alert.py --to +91XXXXXXXXXX --channel SMS --message "Custom alert"
  python scripts/send_custom_twilio_alert.py --to +91XXXXXXXXXX --simulate-surge
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import httpx

DEFAULT_MESSAGE = (
    "Evacuate immediately or take measurable actions as the AQI in your locality "
    "is getting severe and is expected to last longer. This can affect your health."
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Send custom NavosEdge Twilio alert or surge demo.")
    parser.add_argument("--server", default=os.getenv("NAVOS_SERVER_URL", "http://127.0.0.1:8420"))
    parser.add_argument("--to", required=True, help="Recipient E.164 phone number, e.g. +919876543210")
    parser.add_argument("--channel", choices=["SMS", "VOICE_CALL", "CALL", "BOTH"], default="BOTH")
    parser.add_argument("--message", default=DEFAULT_MESSAGE)
    parser.add_argument("--api-key", default=os.getenv("NAVOS_MANAGER_API_KEY", ""))
    parser.add_argument("--simulate-surge", action="store_true", help="Also run full synthetic surge flow")
    args = parser.parse_args()

    headers = {"Content-Type": "application/json"}
    if args.api_key:
        headers["X-Navos-Manager-Key"] = args.api_key

    base = args.server.rstrip("/")
    if args.channel == "BOTH":
        channels = ["SMS", "VOICE_CALL"]
    elif args.channel == "CALL":
        channels = ["VOICE_CALL"]
    else:
        channels = [args.channel]

    with httpx.Client(timeout=20.0) as client:
        for ch in channels:
            resp = client.post(
                f"{base}/api/v1/notifications/test",
                headers=headers,
                json={"phone_number": args.to, "channel": ch, "message": args.message},
            )
            print(f"[{ch}] HTTP {resp.status_code}: {resp.text}")
            if resp.status_code >= 400:
                return 1

        if args.simulate_surge:
            res = client.post(
                f"{base}/api/v1/emergency/residents",
                headers=headers,
                json={"full_name": "Demo Resident", "room_label": "Living Room"},
            )
            res.raise_for_status()
            rid = res.json()["resident_id"]

            client.post(
                f"{base}/api/v1/emergency/contacts",
                headers=headers,
                json={
                    "resident_id": rid,
                    "name": "Primary Caregiver",
                    "relationship": "Family",
                    "phone_number": args.to,
                    "priority_tier": 1,
                    "notify_sms": True,
                    "notify_call": True,
                },
            ).raise_for_status()

            client.post(
                f"{base}/api/v1/emergency/nodes",
                headers=headers,
                json={"node_id": "uno-q-001", "node_name": "UNO Q Edge Node"},
            )
            client.post(
                f"{base}/api/v1/emergency/nodes/uno-q-001/associate",
                headers=headers,
                json={"resident_id": rid},
            ).raise_for_status()

            surge = client.post(
                f"{base}/api/v1/emergency/demo/simulate-event",
                headers=headers,
                json={"node_id": "uno-q-001", "pm2_5": 320.0, "pm10": 450.0, "mq2_v": 3.8, "mq9_v": 3.5, "mq135_v": 3.6},
            )
            surge.raise_for_status()
            print("[SURGE]", json.dumps(surge.json(), indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())

