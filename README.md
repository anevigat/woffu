# Woffu Automation

Small Python automation for attendance actions using the Woffu API.

## What It Does

The script can run three actions:

- `status`: checks whether today looks like a vacation/day-off and whether there is an open check-in.
- `checkin`: if today is not a day-off and no open check-in exists, it creates a check-in.
- `checkout`: if an open check-in exists, it performs checkout.

The implementation includes endpoint and payload fallbacks because API availability can vary across tenants.

## Scheduled Automation

A GitHub Actions workflow is included at [.github/workflows/woffu-automation.yml](.github/workflows/woffu-automation.yml).

It is scheduled to run (Atlantic/Canary summer mapping in UTC):

- Monday to Friday at 08:00 local time: `checkin`
- Monday to Thursday at 17:00 local time: `checkout`
- Friday at 15:00 local time: `checkout`

For `checkin` and `checkout`, the workflow waits a random delay between 1 and 300 seconds before running the script.

The workflow also supports manual execution (`workflow_dispatch`) with a selectable action.

## Requirements

- Python 3.10+
- `requests` library
- Woffu credentials with API access

## Local Usage

Run from this folder:

```bash
WOFFU_USER="your_user" WOFFU_PASS="your_password" python3 woffu.py --action status
```

Other actions:

```bash
WOFFU_USER="your_user" WOFFU_PASS="your_password" python3 woffu.py --action checkin
WOFFU_USER="your_user" WOFFU_PASS="your_password" python3 woffu.py --action checkout
```

## GitHub Actions Setup

Add these repository secrets:

- `WOFFU_USER`
- `WOFFU_PASS`

In GitHub:

1. Open `Settings` in the repository.
2. Go to `Secrets and variables` -> `Actions`.
3. Create both secrets.

Then enable and run the workflow from the `Actions` tab.

## Security Notes

- Never commit credentials to source control.
- Use GitHub Secrets for CI/CD.
- Rotate credentials if they were ever exposed.
