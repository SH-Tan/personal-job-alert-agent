import os
import re
import imaplib
import email
import requests
from bs4 import BeautifulSoup
from email.header import decode_header


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def fetch_company_page(company: dict) -> list[dict]:
    url = company["careers_url"]
    name = company["name"]

    headers = {
        "User-Agent": "Mozilla/5.0 personal-internship-monitor"
    }

    try:
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        print(f"[WARN] Could not fetch {name}: {e}")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    text = clean_text(soup.get_text(" "))

    # Simple v1: one pseudo-job per company page.
    # Later you can add company-specific parsers.
    if "intern" not in text.lower() and "internship" not in text.lower():
        return []

    return [
        {
            "source": "company_website",
            "company": name,
            "title": f"Possible internship at {name}",
            "url": url,
            "description": text[:7000],
        }
    ]


def fetch_known_company_jobs(config: dict) -> list[dict]:
    jobs = []

    for company in config.get("known_companies", []):
        jobs.extend(fetch_company_page(company))

    return jobs


def decode_subject(raw_subject: str) -> str:
    if not raw_subject:
        return ""

    decoded = decode_header(raw_subject)
    parts = []

    for part, enc in decoded:
        if isinstance(part, bytes):
            parts.append(part.decode(enc or "utf-8", errors="ignore"))
        else:
            parts.append(part)

    return "".join(parts)


def email_body_to_text(msg) -> str:
    parts = []

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition"))

            if content_type in ["text/plain", "text/html"] and "attachment" not in disposition:
                payload = part.get_payload(decode=True)
                if payload:
                    parts.append(payload.decode(errors="ignore"))
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            parts.append(payload.decode(errors="ignore"))

    html_or_text = "\n".join(parts)
    soup = BeautifulSoup(html_or_text, "lxml")
    return clean_text(soup.get_text(" "))


def extract_links(raw_text: str) -> list[str]:
    return re.findall(r"https?://[^\s<>\"']+", raw_text or "")


def fetch_job_alert_emails(config: dict) -> list[dict]:
    email_cfg = config.get("email_sources", {})

    if not email_cfg.get("enabled", True):
        return []

    address = os.getenv("EMAIL_ADDRESS")
    password = os.getenv("EMAIL_APP_PASSWORD")
    imap_host = os.getenv("IMAP_HOST", "imap.gmail.com")
    imap_port = int(os.getenv("IMAP_PORT", "993"))

    max_recent = int(email_cfg.get("max_recent_emails", 80))
    sender_keywords = [x.lower() for x in email_cfg.get("sender_keywords", [])]
    content_keywords = [x.lower() for x in email_cfg.get("content_keywords", [])]

    jobs = []

    try:
        mail = imaplib.IMAP4_SSL(imap_host, imap_port)
        mail.login(address, password)
        mail.select("inbox")
    except Exception as e:
        print(f"[WARN] Email connection failed: {e}")
        return []

    status, data = mail.search(None, "ALL")

    if status != "OK":
        mail.logout()
        return []

    ids = data[0].split()
    recent_ids = ids[-max_recent:]

    for msg_id in reversed(recent_ids):
        status, msg_data = mail.fetch(msg_id, "(RFC822)")

        if status != "OK":
            continue

        msg = email.message_from_bytes(msg_data[0][1])

        subject = decode_subject(msg.get("Subject"))
        sender = msg.get("From", "")
        body = email_body_to_text(msg)

        combined = f"{subject}\n{sender}\n{body}"
        combined_lower = combined.lower()

        sender_hit = any(k in sender.lower() for k in sender_keywords)
        content_hit = any(k in combined_lower for k in content_keywords)

        if not sender_hit and not content_hit:
            continue

        links = extract_links(body)
        url = links[0] if links else f"email://{msg_id.decode()}"

        company = "Email Job Alert"

        if "linkedin" in combined_lower:
            company = "LinkedIn Alert"
        elif "handshake" in combined_lower:
            company = "Handshake Alert"
        elif "greenhouse" in combined_lower:
            company = "Greenhouse Alert"
        elif "lever" in combined_lower:
            company = "Lever Alert"

        jobs.append(
            {
                "source": "email_alert",
                "company": company,
                "title": subject or "Job alert email",
                "url": url,
                "description": combined[:7000],
            }
        )

    mail.logout()
    return jobs


def collect_jobs(config: dict) -> list[dict]:
    jobs = []

    jobs.extend(fetch_known_company_jobs(config))
    jobs.extend(fetch_job_alert_emails(config))

    return jobs