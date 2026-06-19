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


def get_domain(headers):
    """Resolve the company domain, required for the sign/requests endpoints."""
    user = requests.get(
        f"{WOFFU_BASE}/api/users", headers=headers, timeout=TIMEOUT_SECONDS
    ).json()
    company = requests.get(
        f"{WOFFU_BASE}/api/companies/{user['CompanyId']}",
        headers=headers,
        timeout=TIMEOUT_SECONDS,
    ).json()
    return company["Domain"]


def is_signed_in(headers):
    """Current clock state: the last sign of the day tells if we are in."""
    signs = requests.get(
        f"{WOFFU_BASE}/api/signs", headers=headers, timeout=TIMEOUT_SECONDS
    ).json()
    return bool(signs) and bool(signs[-1].get("SignIn", False))


def day_off_reason(headers, domain):
    """Return why today is non-working ('festivo' / 'ausencia'), or None.

    Single precise call. The endpoint returns the day's requests, with public
    holidays under the 'Holidays' key and absences/leaves under 'Requests'.
    """
    today = datetime.now().strftime("%m/%d/%Y")  # this endpoint expects mm/dd/YYYY
    resp = requests.get(
        f"https://{domain}/api/svc/core/diary/user/requests",
        headers=headers,
        params={"date": today},
        timeout=TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    data = resp.json()

    if isinstance(data, dict):
        if data.get("Holidays"):
            return "festivo"
        if data.get("Requests"):
            return "ausencia"
    elif isinstance(data, list) and data:
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


def action_checkin(headers, domain):
    reason = day_off_reason(headers, domain)
    if reason:
        print(f"Hoy es {reason}. No se ficha la entrada.")
        return
    if is_signed_in(headers):
        print("Ya estás fichado. No se hace nada.")
        return
    toggle_sign(headers, domain)
    print("Entrada fichada.")


def action_checkout(headers, domain):
    if not is_signed_in(headers):
        print("No hay fichaje abierto. Nada que cerrar.")
        return
    toggle_sign(headers, domain)
    print("Salida fichada.")


def action_status(headers, domain):
    print(f"Fichado: {'sí (dentro)' if is_signed_in(headers) else 'no (fuera)'}")
    reason = day_off_reason(headers, domain)
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
    domain = get_domain(headers)

    actions = {
        "checkin": action_checkin,
        "checkout": action_checkout,
        "status": action_status,
    }
    actions[args.action](headers, domain)


if __name__ == "__main__":
    main()