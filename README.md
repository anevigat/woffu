# Woffu Automation

Small Python automation for attendance actions using the Woffu API.

## What It Does

The script can run three actions:

- `status`: read-only. Shows whether there is an open check-in and whether today is a holiday or absence.
- `checkin`: if today is not a day-off and no open check-in exists, it creates a check-in.
- `checkout`: if an open check-in exists, it performs checkout.

A day counts as a day-off when the user's Woffu calendar marks it as a holiday or there is an approved full-day absence (vacation, sick leave, etc.). Partial absences of a few hours do not block the check-in. If today's diary cannot be read, `checkin` fails instead of signing.

`checkin` and `checkout` can optionally report their result to Slack, see [Slack Notifications](#slack-notifications-optional).

## Scheduled Automation

A GitHub Actions workflow is included at [.github/workflows/woffu-automation.yml](.github/workflows/woffu-automation.yml).

It is scheduled to run (Atlantic/Canary summer mapping in UTC):

- Monday to Friday at 08:00 local time: `checkin`
- Monday to Thursday at 17:00 local time: `checkout`
- Friday at 15:00 local time: `checkout`

For `checkin` and `checkout`, the workflow waits a random delay between 1 and 300 seconds before running the script.

The workflow also supports manual execution (`workflow_dispatch`) with a selectable action.

## Slack Notifications (optional)

Disabled by default. When enabled, every `checkin` and `checkout` run posts its result to a Slack channel through an [incoming webhook](https://api.slack.com/messaging/webhooks): the sign itself, a skipped run (holiday, absence, already signed in, nothing to close) or a failure. `status` never notifies.

It is controlled by two environment variables:

| Variable | Description |
| --- | --- |
| `SLACK_NOTIFY` | Feature flag. Set to `1`, `true`, `yes` or `on` to enable. Anything else, or unset, disables notifications. |
| `SLACK_WEBHOOK` | Slack incoming webhook URL. Only used when `SLACK_NOTIFY` is enabled. |

A Slack failure never affects the sign: the script logs that the notification could not be sent and exits normally. If the flag is enabled but `SLACK_WEBHOOK` is missing, it logs a warning and continues.

The webhook URL is a secret: anyone who has it can post to the channel. Keep it out of source control.

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

With Slack notifications enabled:

```bash
WOFFU_USER="your_user" WOFFU_PASS="your_password" \
SLACK_NOTIFY=true SLACK_WEBHOOK="https://hooks.slack.com/services/..." \
python3 woffu.py --action checkin
```

Alternatively, keep the variables in a local `.woffu.env` file (git-ignored) and load it before running:

```bash
set -a; . ./.woffu.env; set +a
python3 woffu.py --action status
```

## GitHub Actions Setup

Add these repository secrets:

- `WOFFU_USER`
- `WOFFU_PASS`

In GitHub:

1. Open `Settings` in the repository.
2. Go to `Secrets and variables` -> `Actions`.
3. Create both secrets.

To enable Slack notifications from the workflow (optional), also add:

- Secret `SLACK_WEBHOOK`: the incoming webhook URL.
- Repository variable `SLACK_NOTIFY`: `true`.

Then enable and run the workflow from the `Actions` tab.

## Security Notes

- Never commit credentials or the Slack webhook URL to source control.
- Use GitHub Secrets for CI/CD.
- Rotate credentials if they were ever exposed.
