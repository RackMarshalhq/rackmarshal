"""Send one clearly labelled test notification through the configured channel.

This uses the same credential loader and sender as real incident delivery,
so a pass means real notifications can reach you. It writes nothing to the
state database and never prints credentials.
"""

from rackmarshal.core.config import ConfigError, ha_credential_file, load_config
from rackmarshal.notifications import delivery

TEST_NOTIFICATION_ID = "rackmarshal-notify-test"
TEST_TITLE = "RackMarshal test notification"
TEST_MESSAGE = (
    "This is a test from `rackmarshal notify-test`. "
    "No incident exists. If you can read this, delivery works."
)


def send_test(config_path=None, loader=None, sender=None):
    """Return (report, exit_code). Exit 0 = delivered, 2 = not delivered."""
    loader = loader or delivery.load_ha_credentials
    sender = sender or delivery.send_ha
    report = {"channel": "home-assistant", "result": "FAIL"}
    try:
        credential_file = ha_credential_file(load_config(config_path))
    except ConfigError as exc:
        report["error"] = f"configuration: {exc}"
        return report, 2
    try:
        base_url, token = loader(str(credential_file))
    except (delivery.DeliveryError, OSError) as exc:
        report["error"] = f"credentials: {exc}"
        report["hint"] = (
            "Create the Home Assistant credential file described in "
            "docs/QUICKSTART.md (Option B), then run this again."
        )
        return report, 2
    try:
        sender(base_url, token, TEST_NOTIFICATION_ID, TEST_TITLE, TEST_MESSAGE)
    except delivery.DeliveryError as exc:
        # DeliveryError text never contains the token (see send_ha).
        report["error"] = f"delivery: {exc}"
        return report, 2
    report["result"] = "PASS"
    report["detail"] = (
        "Sent. Look for 'RackMarshal test notification' in Home Assistant "
        "notifications."
    )
    return report, 0
