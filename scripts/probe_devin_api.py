"""Probe the Devin API to verify response shapes before writing the real client.

Run with:
    python scripts/probe_devin_api.py

Requires DEVIN_API_KEY in .env (or environment).
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

API_KEY = os.environ.get("DEVIN_API_KEY", "")
BASE = os.environ.get("DEVIN_API_BASE", "https://api.devin.ai/v1")

if not API_KEY:
    print("ERROR: DEVIN_API_KEY not set. Add it to .env first.", file=sys.stderr)
    sys.exit(1)

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}


def pp(label: str, data: dict) -> None:
    print(f"\n{'='*60}")
    print(f"  {label}")
    print("=" * 60)
    print(json.dumps(data, indent=2))


def main() -> None:
    with httpx.Client(base_url=BASE, headers=HEADERS, timeout=30.0) as client:

        # ── 1. Create a minimal test session ──────────────────────────────
        print(f"\nPOST {BASE}/sessions ...")
        resp = client.post(
            "/sessions",
            json={
                "prompt": "Say hello and exit. Do not modify any code or files.",
                "title": "probe-test",
            },
        )
        print(f"Status: {resp.status_code}")
        resp.raise_for_status()
        create_data = resp.json()
        pp("POST /sessions response", create_data)

        session_id = create_data.get("session_id") or create_data.get("id")
        if not session_id:
            print("ERROR: could not extract session_id from response", file=sys.stderr)
            sys.exit(1)

        print(f"\nSession ID: {session_id}")

        # ── 2. Poll GET a couple of times ─────────────────────────────────
        for i in range(2):
            time.sleep(3)
            print(f"\nGET {BASE}/sessions/{session_id} (poll {i+1}) ...")
            resp = client.get(f"/sessions/{session_id}")
            print(f"Status: {resp.status_code}")
            resp.raise_for_status()
            pp(f"GET /sessions/{'{session_id}'} response (poll {i+1})", resp.json())

        # ── 3. Terminate ──────────────────────────────────────────────────
        print(f"\nDELETE {BASE}/sessions/{session_id} ...")
        resp = client.delete(f"/sessions/{session_id}")
        print(f"Status: {resp.status_code}")
        if resp.content:
            try:
                pp("DELETE response", resp.json())
            except Exception:
                print(resp.text)
        else:
            print("(empty body — likely 204 No Content)")

        print("\nProbe complete.")


if __name__ == "__main__":
    main()
