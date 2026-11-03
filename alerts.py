"""
Business alert rules (no AI). Shared by extract.py and make_sample_data.py
so the tool and the answer key use exactly the same definition.

high : parcel needs follow-up now
low  : an earlier problem was recorded but the parcel is moving again
none : nothing to do
"""

from datetime import datetime

TIME_FMT = "%Y-%m-%d %H:%M:%S"
HIGH_STATUSES = {"exception", "delivery_failed", "cancelled", "not_found"}
FINISHED_STATUSES = {"delivered", "cancelled", "not_found"}  # never "stuck"


# Suggested next step for customer service. Edit to match your own process.
ACTIONS = {
    "delivery_failed": "Contact customer to confirm address and arrange redelivery or pickup",
    "exception": "Check with carrier (damage, loss, customs or return); update customer",
    "cancelled": "Confirm cancellation with warehouse; contact customer and reship if needed",
    "not_found": "Check parcel was handed to carrier; contact warehouse",
}
STUCK_ACTION = "Chase carrier for an update; let customer know about the delay"


def suggested_action(status, alert_reason):
    """Rule-based next step for a parcel with a high alert."""
    if status in ACTIONS:
        return ACTIONS[status]
    if "no update" in alert_reason:
        return STUCK_ACTION
    return ""


def alert_for(status, latest_event_time, has_history_issue, as_of, stuck_days=5):
    """Return (alert_level, alert_reason)."""
    reasons = []
    if status in HIGH_STATUSES:
        reasons.append(f"status {status}")

    if status not in FINISHED_STATUSES and latest_event_time:
        try:
            latest = datetime.strptime(latest_event_time, TIME_FMT)
            age_days = (as_of - latest).total_seconds() / 86400
            if age_days > stuck_days:
                reasons.append(f"no update for {int(age_days)} days")
        except ValueError:
            pass  # bad time format is caught by the review checks instead

    if reasons:
        return "high", "; ".join(reasons)
    if has_history_issue and status != "delivered":
        return "low", "earlier exception event, now moving again"
    return "none", ""
