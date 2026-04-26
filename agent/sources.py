import email
import imaplib
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from email.header import decode_header
from email.message import Message
from email.utils import parsedate_to_datetime
from typing import Any, cast
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright
except ImportError:
    PlaywrightTimeoutError = None
    sync_playwright = None


INTERNSHIP_TERMS = (
    "intern",
    "internship",
    "student",
    "university",
    "campus",
    "co-op",
)

CAREER_PATH_HINTS = (
    "/careers",
    "/jobs",
    "/students",
    "/students-and-graduates",
    "/early-careers",
    "/campus",
)

JS_HEAVY_HOST_HINTS = (
    "workday",
    "myworkdayjobs",
    "greenhouse",
    "lever",
    "ashby",
    "smartrecruiters",
)


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def normalize_company(company: dict) -> dict:
    return {
        "name": clean_text(company.get("name", "")),
        "careers_url": clean_text(company.get("careers_url", "")),
        "why_relevant": clean_text(company.get("why_relevant", "")),
    }


def _is_js_heavy_url(url: str) -> bool:
    lowered = (url or "").lower()
    return any(hint in lowered for hint in JS_HEAVY_HOST_HINTS)


def _is_job_like_text(text: str) -> bool:
    normalized = clean_text(text).lower()

    if not normalized:
        return False

    if not any(term in normalized for term in INTERNSHIP_TERMS):
        return False

    blocked_terms = ("privacy", "cookie", "sign in", "log in", "newsletter")
    return not any(term in normalized for term in blocked_terms)


def _extract_title(text: str, fallback: str) -> str:
    cleaned = clean_text(text)

    if not cleaned:
        return fallback

    parts = re.split(r"[|:\n-]", cleaned)
    for part in parts:
        piece = clean_text(part)
        if piece and any(term in piece.lower() for term in INTERNSHIP_TERMS):
            return piece[:160]

    return cleaned[:160]


def _extract_job_cards(soup: BeautifulSoup, base_url: str, company_name: str) -> list[dict]:
    jobs = []
    seen = set()

    for tag in soup.find_all(["a", "article", "section", "div", "li"]):
        text = clean_text(tag.get_text(" "))

        if not _is_job_like_text(text):
            continue

        href = ""
        anchor = tag if tag.name == "a" else tag.find("a", href=True)
        if anchor and anchor.get("href"):
            href = urljoin(base_url, anchor["href"])

        title = _extract_title(text, f"Internship opportunity at {company_name}")
        description = text[:4000]
        dedupe_key = (title.lower(), href.lower())

        if dedupe_key in seen:
            continue

        seen.add(dedupe_key)
        jobs.append(
            {
                "source": "company_website",
                "company": company_name,
                "title": title,
                "url": href or base_url,
                "description": description,
            }
        )

    return jobs


def fetch_company_page(company: dict) -> list[dict]:
    company = normalize_company(company)
    url = company["careers_url"]
    name = company["name"]

    if not url or not name:
        return []

    headers = {"User-Agent": "Mozilla/5.0 personal-job-alert-agent/1.0"}
    use_js_fallback = bool(company.get("use_js_fallback", True))

    try:
        base_url, html = _fetch_company_html(
            url=url,
            headers=headers,
            use_js_fallback=use_js_fallback,
        )
    except Exception as e:
        print(f"[WARN] Could not fetch {name}: {e}")
        return []

    soup = BeautifulSoup(html, "lxml")
    jobs = _extract_job_cards(soup, base_url, name)

    if jobs:
        return jobs[:10]

    page_text = clean_text(soup.get_text(" "))

    if not any(term in page_text.lower() for term in INTERNSHIP_TERMS):
        return []

    return [
        {
            "source": "company_website",
            "company": name,
            "title": f"Possible internship at {name}",
            "url": base_url,
            "description": page_text[:4000],
        }
    ]


def _fetch_company_html(
    url: str,
    headers: dict[str, str],
    use_js_fallback: bool = True,
) -> tuple[str, str]:
    last_url = url
    last_html = ""

    try:
        response = _fetch_company_response(url, headers)
        last_url = response.url
        last_html = response.text

        if _looks_like_blocked_or_empty_jobs_page(last_html, response.url) and use_js_fallback:
            raise ValueError("Page appears to require JavaScript rendering.")

        return response.url, response.text
    except Exception as http_error:
        if not use_js_fallback:
            raise http_error

        if not _should_try_js_fallback(url, last_html):
            raise http_error

        js_url, js_html = _fetch_company_page_with_browser(url)

        if not js_html.strip():
            raise http_error

        return js_url, js_html


def _fetch_company_response(url: str, headers: dict[str, str]) -> requests.Response:
    candidates = [url]
    parsed = urlparse(url)

    if parsed.scheme and parsed.netloc:
        origin = f"{parsed.scheme}://{parsed.netloc}"
        candidates.extend(origin + path for path in CAREER_PATH_HINTS)

    seen = set()
    last_error: Exception | None = None

    for candidate in candidates:
        normalized = candidate.rstrip("/")
        if not normalized or normalized in seen:
            continue

        seen.add(normalized)

        try:
            response = requests.get(
                candidate,
                headers=headers,
                timeout=20,
                allow_redirects=True,
            )
            response.raise_for_status()
        except Exception as e:
            last_error = e
            continue

        return response

    if last_error:
        raise last_error

    raise ValueError(f"No readable URL candidate found for {url}")


def _looks_like_blocked_or_empty_jobs_page(html: str, url: str) -> bool:
    lowered = clean_text(html).lower()

    if not lowered:
        return True

    if _is_js_heavy_url(url):
        js_markers = (
            "enable javascript",
            "javascript is required",
            "please enable javascript",
            "applicant accommodation",
            "greenhouse.io",
            "lever.co",
            "myworkdayjobs.com",
            "__next",
            "window.__initial_state__",
        )
        if any(marker in lowered for marker in js_markers):
            return True

    if any(term in lowered for term in INTERNSHIP_TERMS):
        return False

    generic_markers = (
        "job search",
        "career opportunities",
        "student programs",
        "open positions",
    )
    return not any(marker in lowered for marker in generic_markers)


def _should_try_js_fallback(url: str, html: str) -> bool:
    return _is_js_heavy_url(url) or _looks_like_blocked_or_empty_jobs_page(html, url)


def _fetch_company_page_with_browser(url: str) -> tuple[str, str]:
    if sync_playwright is None:
        raise RuntimeError(
            "Playwright is not installed. Install dependencies and run "
            "`playwright install chromium` to enable JavaScript-heavy career site scraping."
        )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent="Mozilla/5.0 personal-job-alert-agent/1.0",
        )

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)

            try:
                page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass

            try:
                if PlaywrightTimeoutError is not None:
                    page.wait_for_selector(
                        "a, div, li, section, article",
                        timeout=5000,
                    )
            except Exception:
                pass

            html = page.content()
            current_url = page.url
        finally:
            browser.close()

    return current_url, html


def fetch_known_company_jobs(config: dict) -> list[dict]:
    companies = []
    seen = set()

    for raw_company in config.get("known_companies", []):
        company = normalize_company(raw_company)
        key = (company["name"].lower(), company["careers_url"].lower())

        if not company["name"] or not company["careers_url"] or key in seen:
            continue

        seen.add(key)
        companies.append(company)

    if not companies:
        return []

    max_workers = min(8, max(1, len(companies)))
    jobs = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(fetch_company_page, company) for company in companies]

        for future in as_completed(futures):
            try:
                jobs.extend(future.result())
            except Exception as e:
                print(f"[WARN] Company fetch failed: {e}")

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


def email_body_to_text(msg: Message) -> str:
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
    storage_cfg = config.get("storage", {})

    if not email_cfg.get("enabled", True):
        return []

    address = os.getenv("EMAIL_ADDRESS")
    password = os.getenv("EMAIL_APP_PASSWORD")
    imap_host = os.getenv("IMAP_HOST", "imap.gmail.com")
    imap_port = int(os.getenv("IMAP_PORT", "993"))
    imap_folder = os.getenv("IMAP_FOLDER", email_cfg.get("imap_folder", "INBOX"))

    if not address or not password:
        print("[WARN] Email credentials are missing; skipping inbox job alerts.")
        return []

    max_recent = int(email_cfg.get("max_recent_emails", 80))
    retention_days = int(storage_cfg.get("retention_days", 14))
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    sender_keywords = [x.lower() for x in email_cfg.get("sender_keywords", [])]
    content_keywords = [x.lower() for x in email_cfg.get("content_keywords", [])]

    jobs = []

    try:
        mail = imaplib.IMAP4_SSL(imap_host, imap_port)
        mail.login(address, password)
        mail.select(imap_folder)
    except Exception as e:
        print(f"[WARN] Email connection failed: {e}")
        return []

    try:
        status, data = mail.search(None, "SINCE", cutoff.strftime("%d-%b-%Y"))

        if status != "OK":
            return []

        ids = data[0].split()
        recent_ids = ids[-max_recent:]

        for msg_id in reversed(recent_ids):
            status, msg_data = mail.fetch(msg_id, "(RFC822)")

            if status != "OK":
                continue

            raw_message = _raw_email_bytes(msg_data)

            if raw_message is None:
                continue

            msg = email.message_from_bytes(raw_message)

            subject = decode_subject(str(msg.get("Subject", "")))
            sender = msg.get("From", "")
            sent_at = _message_datetime(msg)
            posted_at = sent_at.isoformat(timespec="seconds") if sent_at else ""

            if sent_at and sent_at < cutoff:
                continue

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
                    "posted_at": posted_at,
                    "description": combined[:4000],
                }
            )
    finally:
        mail.logout()

    return jobs


def _raw_email_bytes(msg_data: list[Any]) -> bytes | None:
    if not msg_data:
        return None

    first_item = msg_data[0]

    if not isinstance(first_item, tuple) or len(first_item) < 2:
        return None

    payload = first_item[1]

    if not isinstance(payload, bytes):
        return None

    return cast(bytes, payload)


def _message_datetime(msg: Message) -> datetime | None:
    raw_date = msg.get("Date")

    if not raw_date:
        return None

    try:
        parsed = parsedate_to_datetime(raw_date)
    except (TypeError, ValueError):
        return None

    if parsed is None:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def collect_jobs(config: dict) -> list[dict]:
    jobs = []
    seen = set()

    for job in fetch_known_company_jobs(config) + fetch_job_alert_emails(config):
        key = (
            clean_text(job.get("url", "")).lower(),
            clean_text(job.get("company", "")).lower(),
            clean_text(job.get("title", "")).lower(),
        )

        if key in seen:
            continue

        seen.add(key)
        jobs.append(job)

    return jobs
