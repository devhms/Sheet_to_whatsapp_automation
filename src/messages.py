"""Message formatting utilities."""


def format_submission_message(
    row_dict: dict[str, str], status_column: str = "Bot Details Sent"
) -> str:
    """Format a WhatsApp message from a sheet row."""
    name = row_dict.get(
        "Select your name", row_dict.get("Select Your Name", "Unknown Member")
    )
    date = row_dict.get("Date of Report", row_dict.get("Timestamp", "Unknown Date"))
    score = row_dict.get("Daily Score", row_dict.get("Score", "N/A"))

    exclude_keys = {
        "Timestamp",
        "Date of Report",
        "Select your name",
        "Select Your Name",
        "Daily Score",
        "Score",
        "Email address",
        "Email Address",
        status_column,
        "Bot Delivery State",
        "Admin_Notified",
        "",
    }

    details = ""
    for key, value in row_dict.items():
        if not key or key in exclude_keys:
            continue
        val_str = str(value).strip()
        if not val_str:
            continue
        details += f"- *{key}*: {val_str}\n"

    return (
        f"🔔 *New Daily Report*\n\n"
        f"👤 *Member*: {name}\n"
        f"📅 *Date*: {date}\n"
        f"🏆 *Score*: {score}\n\n"
        f"📝 *Details*:\n{details}\n"
        f"-----------------------------"
    )


def format_missing_report_message(missing_members: list[str]) -> str:
    """Format a message listing members who haven't submitted."""
    msg = (
        "⚠️ *Alert: Missing Reports*\n\n"
        "The following members have NOT submitted their daily report:\n"
    )
    msg += "\n".join(f"- {name}" for name in missing_members)
    msg += "\n\nPlease submit immediately."
    return msg


def format_red_flag_alert(name: str, missed_prayers: list[str]) -> str:
    """Format a red flag alert for missed prayers."""
    prayers = ", ".join(missed_prayers)
    return (
        f"🚨 *RED FLAG ALERT* 🚨\n\n"
        f"User: {name}\n"
        f"Missed: {prayers}\n\n"
        f"Verify immediately."
    )


def format_reminder_message(form_link: str) -> str:
    """Format a daily reminder message."""
    return f"⏳ *Reminder*\n\nDaily Audit Deadline is 10:00 PM.\nLink: {form_link}"
