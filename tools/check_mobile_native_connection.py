"""Observe real phone uploads through V2 without uploading fixture data.

Pairing credentials are read from a local Reality config. Temporary session
tokens remain in memory; the saved evidence includes only status and times.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from urllib.parse import urlsplit
from uuid import uuid4


KINDS = ("location", "device", "activity", "telemetry")


def request_json(base: str, method: str, path: str, token: str = "", payload=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    request = Request(base + path, data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=8) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.load(error)


def sources(data: dict) -> dict:
    return {kind: {key: data.get(kind, {}).get(key)
                   for key in ("available", "reason", "captured_at", "last_report_at", "age_seconds")
                   if key in data.get(kind, {})} for kind in KINDS}


def project_status(document: dict) -> dict:
    data = document.get("data", {})
    connections = data.get("connections", {}).get("devices", [])
    return {"checked_at": datetime.now().astimezone().isoformat(),
            "connections": [{key: device.get(key) for key in
                             ("device_name", "paired_at", "last_seen_at", "online", "reports")}
                            for device in connections if not device.get("device_name", "").startswith("Codex V2")],
            "sources": sources(data),
            "together": {key: data.get("together", {}).get(key) for key in
                         ("enabled", "running", "ready", "reason", "execution", "blockers", "capabilities")},
            "screen": {key: data.get("screen", {}).get(key) for key in
                       ("available", "online", "streaming", "last_report_at", "reason")}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--duration", type=float, default=120)
    parser.add_argument("--interval", type=float, default=5)
    parser.add_argument("--create-room", choices=("call", "watch", "novel"),
                        help="Explicitly test native room creation without joining or activating devices")
    parser.add_argument("--request-id", help="Reuse the original room request after an unconfirmed result")
    parser.add_argument("--legacy-room-request", action="store_true",
                        help="Match the installed Android client by omitting request_id")
    args = parser.parse_args()
    if args.duration < 0 or args.interval <= 0:
        parser.error("duration must be nonnegative and interval must be positive")
    if args.request_id and (not args.create_room or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", args.request_id)):
        parser.error("request-id requires create-room and a valid stable request identity")
    if args.legacy_room_request and (not args.create_room or args.request_id):
        parser.error("legacy-room-request requires create-room without an explicit request-id")
    config = json.loads(args.config.read_text(encoding="utf-8"))
    mobile = config.get("mobile", {})
    base = "http://127.0.0.1:" + str(int(mobile.get("port", 6322)))
    pairing = mobile.get("pairing_token", "")
    payload = {"user_id": str(mobile.get("allowed_user_id", "")), "device_name": "Codex V2 上报检查"}
    result = {"fixture_uploads": False, "observations": []}
    token = ""
    close_status = None
    try:
        status, health = request_json(base, "GET", "/health")
        result["gateway"] = health.get("data", {})
        if status != 200 or result["gateway"].get("execution_path") != "v2_native":
            raise RuntimeError("gateway is not the active V2 native gateway")
        status, paired = request_json(base, "POST", "/pair", pairing, payload)
        token = paired.get("data", {}).get("session_token", "")
        if status != 200 or not token:
            raise RuntimeError("diagnostic pairing failed with HTTP " + str(status))
        deadline = time.monotonic() + args.duration
        previous = None
        while True:
            status, document = request_json(base, "GET", "/status", token)
            if status != 200:
                raise RuntimeError("status read failed with HTTP " + str(status))
            observation = project_status(document)
            result["observations"].append(observation)
            signature = json.dumps([[(item["device_name"], item["paired_at"],
                                     {kind: receipt["accepted_at"] for kind, receipt in (item["reports"] or {}).items()})
                                    for item in observation["connections"]],
                                    {kind: value.get("available") for kind, value in observation["sources"].items()}],
                                   sort_keys=True)
            if signature != previous:
                print(json.dumps(observation, ensure_ascii=False), flush=True)
                previous = signature
            if time.monotonic() >= deadline:
                break
            time.sleep(min(args.interval, max(0, deadline - time.monotonic())))
        status, native = request_json(base, "GET", "/snapshot", token)
        value = native.get("data", {})
        result["native_snapshot"] = {"http": status, "ok": native.get("ok"), "code": native.get("code"),
            **{key: value.get(key) for key in ("execution_path", "capability", "state", "effect", "receipt_ref")},
            "sources": sources(value.get("snapshot", {}))}
        if args.create_room:
            request_id = args.request_id or "codex-native-check-" + uuid4().hex
            arguments = {"request_id": request_id, "mode": args.create_room, "client": "android_native"}
            if args.legacy_room_request:
                arguments.pop("request_id")
            result["room_creation"] = {"request_id_sent": not args.legacy_room_request}
            status, created = request_json(base, "POST", "/room/create", token, arguments)
            room = created.get("data", {})
            result["room_creation"].update({"http": status, "ok": created.get("ok"),
                "code": created.get("code"), "uncertain": created.get("uncertain"),
                **{key: room.get(key) for key in ("execution_path", "capability", "state", "effect",
                                                "operation_id", "receipt_ref", "request_id", "mode", "expires_at")}})
            if status == 200 and created.get("ok") is True and room.get("url"):
                # Fetch only from the local gateway. Do not launch the page,
                # execute JS, join its websocket or activate camera/microphone.
                parts = urlsplit(room["url"])
                local_page = base + parts.path + ("?" + parts.query if parts.query else "")
                with urlopen(local_page, timeout=8) as response:
                    result["room_creation"]["page_http"] = response.status
                    result["room_creation"]["page_is_html"] = "text/html" in response.headers.get("Content-Type", "")
                repeated_status, repeated = request_json(base, "POST", "/room/create", token, arguments)
                repeated_room = repeated.get("data", {})
                result["room_creation"]["stable_retry"] = bool(repeated_status == 200
                    and repeated_room.get("url") == room["url"]
                    and repeated_room.get("request_id") == room.get("request_id")
                    and repeated_room.get("operation_id") == room.get("operation_id"))
                if (result["room_creation"]["page_http"] != 200
                        or not result["room_creation"]["page_is_html"]
                        or not result["room_creation"]["stable_retry"]):
                    raise RuntimeError("native room page or stable retry validation failed")
            else:
                # Preserve the original request identity. An unknown outcome
                # must not be retried under a new identity.
                raise RuntimeError("native room creation did not return a confirmed success")
        # Reproduce the former observer-close bug while retaining the first
        # diagnostic session for the read after closing the second observer.
        second = ""
        try:
            status, paired = request_json(base, "POST", "/pair", pairing,
                dict(payload, device_name="Codex V2 会话隔离检查"))
            second = paired.get("data", {}).get("session_token", "")
            if status != 200 or not second:
                raise RuntimeError("isolation pairing failed with HTTP " + str(status))
        finally:
            if second:
                isolation_close, _ = request_json(base, "POST", "/session/close", second, {})
        status, after = request_json(base, "GET", "/status", token)
        result["after_observer_close"] = {"status_http": status, "close_http": isolation_close,
                                          **project_status(after)}
        before = result["observations"][-1]
        present = {kind for kind, value in before["sources"].items() if value.get("available")}
        result["validation"] = {
            "real_uploads_seen": any(device.get("reports") for observation in result["observations"]
                                     for device in observation["connections"]),
            "observer_close_preserved_sources": (all(result["after_observer_close"]["sources"][kind].get("available")
                                                      for kind in present) if present else None)}
        print(json.dumps({"native_snapshot": result["native_snapshot"],
                          "after_observer_close": result["after_observer_close"],
                          "validation": result["validation"], "room_creation": result.get("room_creation")},
                         ensure_ascii=False), flush=True)
        return 0 if result["native_snapshot"]["ok"] is True else 1
    except Exception as error:
        # Do not include HTTP bodies, request objects or credential-bearing config.
        result["error_type"] = type(error).__name__
        print(json.dumps({"error_type": type(error).__name__}), flush=True)
        return 1
    finally:
        if token:
            try:
                close_status, _ = request_json(base, "POST", "/session/close", token, {})
            except Exception:
                close_status = "unavailable"
        result["diagnostic_session_close"] = close_status
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    raise SystemExit(main())
