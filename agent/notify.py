import os
import smtplib
from email.mime.text import MIMEText


def send_email_notification(matches: list[dict]):
    if not matches:
        print("[INFO] No matches to notify.")
        return

    sender = os.getenv("EMAIL_ADDRESS")
    password = os.getenv("EMAIL_APP_PASSWORD")
    to_addr = os.getenv("NOTIFY_TO", sender)

    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))

    if not sender or not password or not to_addr:
        print("[WARN] Notification email is not configured; skipping email send.")
        return

    lines = []
    lines.append("New internship matches:\n")

    for i, item in enumerate(matches, 1):
        job = item["job"]
        match = item["match"]

        lines.append(f"{i}. {match.get('title') or job.get('title')}")
        lines.append(f"Company: {match.get('company') or job.get('company')}")
        lines.append(f"Score: {match.get('score')}")
        lines.append(f"CV: {match.get('matched_cv')}")
        lines.append(f"Profile: {match.get('search_profile')}")
        lines.append(f"Action: {match.get('recommended_action')}")
        lines.append(f"Reason: {match.get('reason')}")
        lines.append(f"URL: {job.get('url')}")
        lines.append("")

    body = "\n".join(lines)

    msg = MIMEText(body)
    msg["Subject"] = f"{len(matches)} new internship matches"
    msg["From"] = sender
    msg["To"] = to_addr

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(sender, password)
        server.send_message(msg)

    print(f"[INFO] Sent {len(matches)} matches.")
