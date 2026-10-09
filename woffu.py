import argparse
import os
from datetime import datetime

import requests

WOFFU_BASE = "https://app.woffu.com"
TIMEOUT_SECONDS = 30


def login(username, password):
    """Authenticate and return the headers used for every request."""
    resp = requests.post(
        f"{WOFFU_BASE}/token",
        data={"grant_type": "password", "username": username, "password": password},
        timeout=TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    token = resp.json()["access_token"]
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json;charset=utf-8",
    }


def get_account(headers):
    """Resolve the user id and company domain, required for the diary/sign endpoints."""
    resp = requests.get(
        f"{WOFFU_BASE}/api/users", headers=headers, timeout=TIMEOUT_SECONDS
    )
    resp.raise_for_status()
    user = resp.json()
    resp = requests.get(
        f"{WOFFU_BASE}/api/companies/{user['CompanyId']}",
        headers=headers,
        timeout=TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return user["UserId"], resp.json()["Domain"]


def is_signed_in(headers):
    """Current clock state: the last sign of the day tells if we are in."""
    resp = requests.get(
        f"{WOFFU_BASE}/api/signs", headers=headers, timeout=TIMEOUT_SECONDS
    )
    resp.raise_for_status()
    signs = resp.json()
    return bool(signs) and bool(signs[-1].get("SignIn", False))


def day_off_reason(headers, domain, user_id):
    """Return why today is non-working ('festivo' / 'ausencia'), or None.

    Single precise call. The day's diary carries the calendar holiday flag
    ('isHoliday') and the approved absences ('absenceEvents'). Raises if
    today's diary can't be read, so we never check in on an unverified day.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    resp = requests.get(
        f"https://{domain}/api/svc/core/diariesquery/users/{user_id}"
        "/diaries/summary/presence",
        headers=headers,
        params={
            "userId": user_id,
            "fromDate": today,
            "toDate": today,
            "pageSize": 1,
        },
        timeout=TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    diaries = resp.json().get("diaries") or []
    diary = next(
        (d for d in diaries if str(d.get("date", "")).startswith(today)), None
    )
    if diary is None or "isHoliday" not in diary:
        raise RuntimeError(f"No se pudo leer el diario de {today} en Woffu.")

    if diary["isHoliday"]:
        return "festivo"
    # Partial absences (a few hours) still need the check-in; full days don't.
    if any(event.get("allDay") for event in diary.get("absenceEvents") or []):
        return "ausencia"
    return None


def toggle_sign(headers, domain):
    """Single POST. Woffu decides sign-in vs sign-out from the current state."""
    offset_minutes = datetime.now().astimezone().utcoffset().total_seconds() / 60
    resp = requests.post(
        f"https://{domain}/api/svc/signs/signs",
        headers=headers,
        json={"deviceId": "WebApp", "timezoneOffset": int(-offset_minutes)},
        timeout=TIMEOUT_SECONDS,
    )
    resp.raise_for_status()


def action_checkin(headers, domain, user_id):
    reason = day_off_reason(headers, domain, user_id)
    if reason:
        print(f"Hoy es {reason}. No se ficha la entrada.")
        return
    if is_signed_in(headers):
        print("Ya estás fichado. No se hace nada.")
        return
    toggle_sign(headers, domain)
    print("Entrada fichada.")


def action_checkout(headers, domain, user_id):
    if not is_signed_in(headers):
        print("No hay fichaje abierto. Nada que cerrar.")
        return
    toggle_sign(headers, domain)
    print("Salida fichada.")


def action_status(headers, domain, user_id):
    print(f"Fichado: {'sí (dentro)' if is_signed_in(headers) else 'no (fuera)'}")
    reason = day_off_reason(headers, domain, user_id)
    print(f"Festivo/ausencia hoy: {reason if reason else 'no'}")


def main():
    parser = argparse.ArgumentParser(description="Woffu automation helper")
    parser.add_argument(
        "--action",
        required=True,
        choices=["checkin", "checkout", "status"],
        help="Action to execute",
    )
    args = parser.parse_args()

    headers = login(os.environ["WOFFU_USER"], os.environ["WOFFU_PASS"])
    user_id, domain = get_account(headers)

    actions = {
        "checkin": action_checkin,
        "checkout": action_checkout,
        "status": action_status,
    }
    actions[args.action](headers, domain, user_id)


if __name__ == "__main__":
    main()