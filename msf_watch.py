#!/usr/bin/env python3
"""
msf_watch.py — Watch a UH Community Colleges (Leeward) continuing-ed course page
and push a phone notification when a section OPENS UP within a date horizon.

Default target: TRAN8101 MSF Basic RiderCourse (courseId=121631).

How it works
------------
- Fetches the course detail page.
- Parses every section: its start date and whether it's "Full" or has seats.
- Keeps only sections whose START date is within HORIZON_MONTHS from today.
- Alerts you the moment a section in that window becomes bookable, and (via a
  small state file) will NOT re-spam you every run while it stays open.

Notifications
-------------
- ntfy (default, free, easiest for phone push): set NTFY_TOPIC.
- Email fallback: set SMTP_* + ALERT_EMAIL vars.
If neither is configured it just prints to the console (useful for testing).

Env vars (all optional except a notifier if you want a push):
  COURSE_URL       full course URL (defaults to the MSF course)
  HORIZON_MONTHS   how far ahead to care about (default 3)
  NTFY_TOPIC       e.g. "johns-msf-9f3k2"   -> pushes to ntfy.sh/<topic>
  NTFY_SERVER      default "https://ntfy.sh"
  STATE_FILE       default "./msf_state.json"
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, ALERT_EMAIL, FROM_EMAIL
"""

import os
import re
import json
import sys
import smtplib
from datetime import date, datetime
from email.message import EmailMessage

import requests
from bs4 import BeautifulSoup

COURSE_URL = os.environ.get(
    "COURSE_URL",
    "https://ce.uhcc.hawaii.edu/search/publicCourseSearchDetails.do?method=load&courseId=121631",
)
HORIZON_MONTHS = int(os.environ.get("HORIZON_MONTHS", "3"))
STATE_FILE = os.environ.get("STATE_FILE", "./msf_state.json")
UA = "Mozilla/5.0 (compatible; msf-watch/1.0; personal course seat checker)"

SECTION_RE = re.compile(r"TRAN8101\s*-\s*(\d{6})")
DATE_RANGE_RE = re.compile(
    r"([A-Z][a-z]{2} \d{2}, \d{4})\s+to\s+([A-Z][a-z]{2} \d{2}, \d{4})"
)
SEATS_RE = re.compile(r"(\d+)\s+Seat\(s\) Left", re.IGNORECASE)


def add_months(d: date, months: int) -> date:
    """Add whole months to a date, clamping the day if needed."""
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    # clamp day to end of target month
    for day in (d.day, 28, 29, 30, 31):
        try:
            return date(y, m, min(day, 31))
        except ValueError:
            continue
    return date(y, m, 28)


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers={"User-Agent": UA}, timeout=30)
    resp.raise_for_status()
    return resp.text


def parse_sections(html: str):
    """Return list of dicts: {code, start, end, open, seats} for real sections."""
    text = BeautifulSoup(html, "html.parser").get_text(separator="\n")

    # Split the page text into per-section chunks keyed by the 6-digit code.
    parts = SECTION_RE.split(text)
    # parts = [preamble, code1, chunk1, code2, chunk2, ...]
    sections = []
    seen = set()
    for i in range(1, len(parts) - 1, 2):
        code = parts[i]
        chunk = parts[i + 1]

        # Real enrollable sections contain "Contact Hours"; modal popups don't.
        if "Contact Hours" not in chunk:
            continue
        if code in seen:  # de-dupe if a code appears twice
            continue
        seen.add(code)

        m = DATE_RANGE_RE.search(chunk)
        if not m:
            continue
        try:
            start = datetime.strptime(m.group(1), "%b %d, %Y").date()
            end = datetime.strptime(m.group(2), "%b %d, %Y").date()
        except ValueError:
            continue

        seats_m = SEATS_RE.search(chunk)
        is_open = bool(seats_m) or ("Add to Cart" in chunk)
        seats = int(seats_m.group(1)) if seats_m else (1 if is_open else 0)

        sections.append(
            {"code": code, "start": start, "end": end, "open": is_open, "seats": seats}
        )
    return sections


def load_state():
    try:
        with open(STATE_FILE) as f:
            return set(json.load(f).get("alerted", []))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def save_state(alerted):
    with open(STATE_FILE, "w") as f:
        json.dump({"alerted": sorted(alerted)}, f, indent=2)


def notify(title: str, message: str):
    sent = False
    topic = os.environ.get("NTFY_TOPIC")
    if topic:
        server = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
        try:
            requests.post(
                f"{server}/{topic}",
                data=message.encode("utf-8"),
                headers={
                    "Title": title,
                    "Priority": "high",
                    "Tags": "motorcycle,bell",
                    "Click": COURSE_URL,
                },
                timeout=20,
            )
            sent = True
        except requests.RequestException as e:
            print(f"[ntfy error] {e}", file=sys.stderr)

    if os.environ.get("SMTP_HOST") and os.environ.get("ALERT_EMAIL"):
        try:
            msg = EmailMessage()
            msg["Subject"] = title
            msg["From"] = os.environ.get("FROM_EMAIL", os.environ["SMTP_USER"])
            msg["To"] = os.environ["ALERT_EMAIL"]
            msg.set_content(message + f"\n\n{COURSE_URL}")
            with smtplib.SMTP(
                os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT", "587"))
            ) as s:
                s.starttls()
                if os.environ.get("SMTP_USER"):
                    s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
                s.send_message(msg)
            sent = True
        except Exception as e:  # noqa: BLE001
            print(f"[email error] {e}", file=sys.stderr)

    if not sent:
        print(f"\n=== NOTIFICATION (no push configured) ===\n{title}\n{message}\n")


def run(html=None):
    today = date.today()
    horizon = add_months(today, HORIZON_MONTHS)

    if html is None:
        html = fetch_html(COURSE_URL)
    sections = parse_sections(html)

    in_window = [s for s in sections if today <= s["start"] <= horizon]
    open_now = [s for s in in_window if s["open"]]

    print(
        f"Checked {len(sections)} sections; "
        f"{len(in_window)} within {HORIZON_MONTHS} mo (through {horizon:%b %d, %Y}); "
        f"{len(open_now)} open."
    )
    for s in in_window:
        flag = f"OPEN ({s['seats']} left)" if s["open"] else "full"
        print(f"  {s['start']:%a %b %d, %Y}  [{flag}]")

    alerted = load_state()
    newly_open = [s for s in open_now if s["code"] not in alerted]

    # Drop codes from state once they're no longer open (so re-openings re-alert).
    open_codes = {s["code"] for s in open_now}
    alerted &= open_codes

    if newly_open:
        lines = [
            f"• {s['start']:%a %b %d} \u2013 {s['end']:%b %d, %Y}  ({s['seats']} seat(s))"
            for s in sorted(newly_open, key=lambda x: x["start"])
        ]
        title = f"MSF course opened! {len(newly_open)} new date(s)"
        message = "Seats just opened for the Basic RiderCourse:\n" + "\n".join(lines)
        notify(title, message)
        alerted |= {s["code"] for s in newly_open}

    save_state(alerted)
    return {"in_window": in_window, "open_now": open_now, "newly_open": newly_open}


if __name__ == "__main__":
    run()
