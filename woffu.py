import argparse
import base64
import json
import os
from datetime import datetime, timezone

import requests

AUTH_URL = "https://app.woffu.com/token"
API_URL = "https://app.woffu.com/api"
TIMEOUT_SECONDS = 30


def extract_user_id(payload):
    """Try common user id fields in different payload shapes."""
    candidates = ("UserId", "userId", "Id", "id", "sub", "nameid")

    if isinstance(payload, dict):
        for key in candidates:
            if key in payload and payload[key] is not None:
                return payload[key]

        for key in ("User", "user", "Data", "data", "Result", "result"):
            if key in payload:
                nested = extract_user_id(payload[key])
                if nested is not None:
                    return nested

    if isinstance(payload, list):
        for item in payload:
            nested = extract_user_id(item)
            if nested is not None:
                return nested

    return None


def decode_jwt_payload(token):
    """Decode JWT payload without signature verification for claim inspection."""
    parts = token.split(".")
    if len(parts) < 2:
        return {}

    payload_b64 = parts[1]
    padding = "=" * (-len(payload_b64) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload_b64 + padding)
        return json.loads(decoded.decode("utf-8"))
    except Exception:
        return {}


def parse_iso_date(value):
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    for candidate in (text, text.replace("Z", "+00:00"), text[:10]):
        try:
            return datetime.fromisoformat(candidate).date()
        except ValueError:
            continue
    return None


def parse_rows(payload):
    if isinstance(payload, list):
        return payload

    if isinstance(payload, dict):
        rows = (
            payload.get("data")
            or payload.get("Data")
            or payload.get("items")
            or payload.get("Items")
            or payload.get("result")
            or payload.get("Result")
            or payload.get("requests")
            or payload.get("Requests")
            or payload.get("signs")
            or payload.get("Signs")
        )
        if isinstance(rows, list):
            return rows

    return []


def request_json(method, endpoint, headers, payload=None):
    response = requests.request(
        method,
        endpoint,
        headers=headers,
        json=payload,
        timeout=TIMEOUT_SECONDS,
    )

    body = None
    try:
        body = response.json()
    except ValueError:
        body = None

    return response, body


def get_auth_headers(username, password):
    resp = requests.post(
        AUTH_URL,
        data={"grant_type": "password", "username": username, "password": password},
        timeout=TIMEOUT_SECONDS,
    )
    resp.raise_for_status()

    token = resp.json()["access_token"]
    print("Token OK")
    return token, {"Authorization": f"Bearer {token}"}


def resolve_user_id(headers, token):
    me_resp = requests.get(f"{API_URL}/users/me", headers=headers, timeout=TIMEOUT_SECONDS)
    if me_resp.status_code == 200:
        me = me_resp.json()
        user_id = extract_user_id(me)
        if user_id is not None:
            print(f"UserId: {user_id}")
            return user_id

    token_claims = decode_jwt_payload(token)
    user_id = extract_user_id(token_claims)
    if user_id is not None:
        print(f"UserId (from token): {user_id}")
        return user_id

    print("UserId not available from /users/me or token claims.")
    return None


def find_vacation_today(headers, user_id):
    """Try common endpoints for absences/time off and check if today is included."""
    today = datetime.now().date()
    candidate_endpoints = [
        f"{API_URL}/requests",
        f"{API_URL}/vacations",
        f"{API_URL}/absences",
        f"{API_URL}/timeoff",
        f"{API_URL}/days-off",
    ]
    if user_id is not None:
        candidate_endpoints = [
            f"{API_URL}/requests?userId={user_id}",
            f"{API_URL}/vacations?userId={user_id}",
            f"{API_URL}/absences?userId={user_id}",
            f"{API_URL}/timeoff?userId={user_id}",
            f"{API_URL}/days-off?userId={user_id}",
        ] + candidate_endpoints

    start_keys = ["startDate", "StartDate", "from", "From", "dateFrom", "DateFrom"]
    end_keys = ["endDate", "EndDate", "to", "To", "dateTo", "DateTo"]
    type_keys = ["type", "Type", "requestType", "RequestType", "name", "Name"]
    status_keys = ["status", "Status", "state", "State"]

    for endpoint in candidate_endpoints:
        response, payload = request_json("GET", endpoint, headers)
        if response.status_code != 200 or payload is None:
            continue

        rows = parse_rows(payload)
        if not rows:
            continue

        for row in rows:
            if not isinstance(row, dict):
                continue

            start_raw = next((row.get(k) for k in start_keys if row.get(k)), None)
            end_raw = next((row.get(k) for k in end_keys if row.get(k)), None)
            if not start_raw or not end_raw:
                continue

            start_date = parse_iso_date(start_raw)
            end_date = parse_iso_date(end_raw)
            if start_date is None or end_date is None:
                continue

            req_type = str(next((row.get(k) for k in type_keys if row.get(k) is not None), "")).lower()
            req_status = str(next((row.get(k) for k in status_keys if row.get(k) is not None), "")).lower()

            is_day_off_type = any(word in req_type for word in ("vac", "holiday", "vacation", "leave", "day off", "off"))
            is_approved = any(word in req_status for word in ("approved", "aprob", "accept")) or req_status == ""

            if start_date <= today <= end_date and is_day_off_type and is_approved:
                return True, endpoint, row

    return False, None, None


def find_open_checkin(headers, user_id):
    """Find an open sign (checkin without checkout) with endpoint fallbacks."""
    today = datetime.now().date().isoformat()
    candidate_endpoints = [
        f"{API_URL}/signs",
        f"{API_URL}/signs?date={today}",
        f"{API_URL}/signs?from={today}",
    ]
    if user_id is not None:
        candidate_endpoints = [
            f"{API_URL}/signs?userId={user_id}",
            f"{API_URL}/signs?userId={user_id}&date={today}",
            f"{API_URL}/signs?userId={user_id}&from={today}",
        ] + candidate_endpoints

    out_keys = ["SignOutDateTime", "signOutDateTime", "CheckOutDateTime", "checkOutDateTime", "outDate", "OutDate"]
    for endpoint in candidate_endpoints:
        response, payload = request_json("GET", endpoint, headers)
        if response.status_code != 200 or payload is None:
            continue

        rows = parse_rows(payload)
        for row in rows:
            if not isinstance(row, dict):
                continue

            has_checkout = any(row.get(k) for k in out_keys)
            if not has_checkout:
                return row, endpoint

    return None, None


def try_checkin(headers, user_id):
    if user_id is None:
        print("Cannot do checkin: missing user_id.")
        return False

    now_iso = datetime.now(timezone.utc).isoformat()
    payloads = [
        {"UserId": user_id, "SignInDateTime": now_iso},
        {"userId": user_id, "signInDateTime": now_iso},
    ]

    for payload in payloads:
        response, body = request_json("POST", f"{API_URL}/signs", headers, payload)
        if response.status_code in (200, 201, 204):
            print("Checkin done.")
            return True
        if body and isinstance(body, dict):
            message = body.get("Message") or body.get("message")
            if message:
                print(f"Checkin attempt failed: {message}")

    print("Checkin failed on all known payload formats.")
    return False


def try_checkout(headers, open_sign):
    sign_id = extract_user_id(open_sign)
    now_iso = datetime.now(timezone.utc).isoformat()

    candidate_calls = []
    if sign_id is not None:
        candidate_calls.extend(
            [
                ("POST", f"{API_URL}/signs/{sign_id}/checkout", {"SignOutDateTime": now_iso}),
                ("POST", f"{API_URL}/signs/{sign_id}/check-out", {"SignOutDateTime": now_iso}),
                ("PUT", f"{API_URL}/signs/{sign_id}", {"SignOutDateTime": now_iso}),
                ("PATCH", f"{API_URL}/signs/{sign_id}", {"SignOutDateTime": now_iso}),
            ]
        )

    candidate_calls.extend(
        [
            ("POST", f"{API_URL}/signs/checkout", {"SignOutDateTime": now_iso}),
            ("POST", f"{API_URL}/signs", {"SignOutDateTime": now_iso}),
        ]
    )

    for method, endpoint, payload in candidate_calls:
        response, body = request_json(method, endpoint, headers, payload)
        if response.status_code in (200, 201, 204):
            print(f"Checkout done via {endpoint}.")
            return True
        if body and isinstance(body, dict):
            message = body.get("Message") or body.get("message")
            if message:
                print(f"Checkout attempt failed: {message}")

    print("Checkout failed on all known endpoint formats.")
    return False


def action_checkin(headers, user_id):
    on_vacation, source, item = find_vacation_today(headers, user_id)
    if on_vacation:
        print(f"Day off detected today. No checkin. Source: {source}")
        print(item)
        return

    open_sign, source = find_open_checkin(headers, user_id)
    if open_sign is not None:
        print(f"Open checkin already exists. No action. Source: {source}")
        return

    try_checkin(headers, user_id)


def action_checkout(headers, user_id):
    open_sign, source = find_open_checkin(headers, user_id)
    if open_sign is None:
        print("No open checkin found. Nothing to checkout.")
        return

    print(f"Open checkin found. Trying checkout. Source: {source}")
    try_checkout(headers, open_sign)


def action_status(headers, user_id):
    on_vacation, source, item = find_vacation_today(headers, user_id)
    if on_vacation:
        print(f"Vacation today: YES (endpoint: {source})")
        print(item)
    else:
        print("Vacation today: NO (or endpoint not available for this tenant)")

    open_sign, sign_source = find_open_checkin(headers, user_id)
    if open_sign is None:
        print("Open checkin: NO")
    else:
        print(f"Open checkin: YES (endpoint: {sign_source})")


def main():
    parser = argparse.ArgumentParser(description="Woffu automation helper")
    parser.add_argument(
        "--action",
        required=True,
        choices=["checkin", "checkout", "status"],
        help="Action to execute",
    )
    args = parser.parse_args()

    username = os.environ["WOFFU_USER"]
    password = os.environ["WOFFU_PASS"]

    token, headers = get_auth_headers(username, password)
    user_id = resolve_user_id(headers, token)

    if args.action == "checkin":
        action_checkin(headers, user_id)
    elif args.action == "checkout":
        action_checkout(headers, user_id)
    else:
        action_status(headers, user_id)


if __name__ == "__main__":
    main()