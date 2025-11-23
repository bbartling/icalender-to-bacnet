#!/usr/bin/env python3
"""
ical_event_test.py
===================

This script is a stand‑alone utility to validate your iCalendar feed before
building a BACnet gateway around it.  It fetches an iCalendar (ICS) URL,
parses it with the `icalendar` and `recurring_ical_events` libraries, and
prints a human‑readable list of upcoming events along with how far away
they are from now.  It uses the same underlying logic as the gateway
example in this repository but without any BACnet dependencies.

Usage::

    python ical_event_test.py --url "<ICS_URL>" [--tz America/Chicago]

You can also enable continuous polling with the `--poll-minutes` flag.  For
example, the following command polls a public Google holiday feed every
minute, printing the upcoming events each time::

    python ical_event_test.py \
        --url "https://calendar.google.com/calendar/ical/en.usa%23holiday%40group.v.calendar.google.com/public/basic.ics" \
        --poll-minutes 1

This script is intentionally verbose to aid in debugging.  Use the
`--no-debug` flag to suppress internal debug messages.

Dependencies
------------
The following packages are required for this script:

* `requests` – for HTTP downloads
* `icalendar` – RFC5545 calendar parsing
* `recurring-ical-events` ≥ 3.0 – to expand recurring events
* `python-dateutil` and `tzdata` – for timezone handling

Install them with pip::

    pip install requests icalendar "recurring-ical-events>=3" python-dateutil tzdata

"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests
import icalendar
import recurring_ical_events
from dateutil import tz as dateutil_tz

CACHE_ICS = "calendar_cache.ics"
CACHE_META = "calendar_cache_meta.json"


def human_delta(seconds: float) -> str:
    """Convert a delta in seconds to a human readable string."""
    s = int(abs(seconds))
    minutes, sec = divmod(s, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if not parts:
        parts.append(f"{sec}s")
    return " ".join(parts)


def load_meta() -> dict:
    """Load cached HTTP metadata from disk."""
    if os.path.exists(CACHE_META):
        with open(CACHE_META, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_meta(meta: dict) -> None:
    """Persist HTTP metadata to disk."""
    with open(CACHE_META, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)


def fetch_ics(url: str, timeout: int, log) -> bytes:
    """Fetch an iCalendar feed, using conditional GET to minimize downloads."""
    meta = load_meta()
    headers: dict[str, str] = {}
    if "etag" in meta:
        headers["If-None-Match"] = meta["etag"]
        log(f"Using cached ETag: {meta['etag']}")
    if "last_modified" in meta:
        headers["If-Modified-Since"] = meta["last_modified"]
        log(f"Using cached Last-Modified: {meta['last_modified']}")

    response = requests.get(url, headers=headers, timeout=timeout)
    log(f"HTTP status: {response.status_code}")
    if response.status_code == 304 and os.path.exists(CACHE_ICS):
        log("Feed not modified; using cached file.")
        return open(CACHE_ICS, "rb").read()

    response.raise_for_status()
    content = response.content
    log(f"Downloaded {len(content)} bytes.")
    with open(CACHE_ICS, "wb") as f:
        f.write(content)

    new_meta = {
        "etag": response.headers.get("ETag"),
        "last_modified": response.headers.get("Last-Modified"),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    save_meta({k: v for k, v in new_meta.items() if v})
    return content


def normalize_dt(dt, local_tz: ZoneInfo, log) -> datetime:
    """Normalize a date or datetime into a timezone aware datetime."""
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    # handle date objects (for all day events)
    if hasattr(dt, "year") and hasattr(dt, "month") and hasattr(dt, "day"):
        return datetime(dt.year, dt.month, dt.day, 0, 0, tzinfo=local_tz)
    raise ValueError(f"Unsupported date type: {type(dt)}")


def parse_events(ics_bytes: bytes, window_days: int, local_tz: ZoneInfo, log):
    """Parse and expand events for a given time window."""
    cal = icalendar.Calendar.from_ical(ics_bytes)
    now = datetime.now(timezone.utc)
    window_end = now + timedelta(days=window_days)
    events = recurring_ical_events.of(cal).between(now, window_end)
    parsed: list[tuple[datetime, datetime, str]] = []
    for ev in events:
        summary = str(ev.get("SUMMARY", "(no title)"))
        dtstart_raw = ev.decoded("DTSTART", None)
        dtend_raw = ev.decoded("DTEND", None)
        dtstart = normalize_dt(dtstart_raw, local_tz, log)
        dtend = normalize_dt(dtend_raw, local_tz, log) if dtend_raw else None
        parsed.append((dtstart, dtend, summary))
    parsed.sort(key=lambda x: x[0])
    return parsed


def print_upcoming(events, now_utc: datetime, local_tz: ZoneInfo, max_events: int) -> None:
    """Render upcoming events from a list of (start_dt, end_dt, summary)."""
    upcoming = [e for e in events if isinstance(e[0], datetime) and e[0] >= now_utc][:max_events]
    print("\n=== Upcoming Events ===\n")
    if not upcoming:
        print("No upcoming events")
        return
    print(f"Next {len(upcoming)} events:\n" + "-" * 60)
    for i, (start_dt, end_dt, summary) in enumerate(upcoming, start=1):
        start_local = start_dt.astimezone(local_tz)
        delta_sec = (start_dt - now_utc).total_seconds()
        if end_dt:
            end_local = end_dt.astimezone(local_tz)
            dur_min = int((end_dt - start_dt).total_seconds() / 60)
            dur_str = f"{dur_min} min"
        else:
            end_local = None
            dur_str = "?"
        print(f"{i:>2}. {summary}")
        print(f"    When: {start_local:%Y-%m-%d %H:%M %Z}")
        if end_local:
            print(f"    Ends: {end_local:%Y-%m-%d %H:%M %Z}")
        print(f"    In:   {human_delta(delta_sec)}")
        print(f"    Dur:  {dur_str}\n")
    print("-" * 60)
    if upcoming:
        next_delta = (upcoming[0][0] - now_utc).total_seconds()
        print("Next event begins in:", human_delta(next_delta))


def main() -> None:
    parser = argparse.ArgumentParser(description="Test an iCalendar feed and print upcoming events.")
    parser.add_argument("--url", required=True, help="ICS feed URL to test")
    parser.add_argument("--tz", default="America/Chicago", help="Local timezone for display")
    parser.add_argument("--window-days", type=int, default=365, help="Days ahead to expand recurring events")
    parser.add_argument("--max-events", type=int, default=10, help="Maximum number of events to display")
    parser.add_argument("--poll-minutes", type=float, default=0, help="Polling interval in minutes; 0 disables polling")
    parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout for fetching the feed")
    parser.add_argument("--debug", dest="debug", action="store_true", help="Enable debug output")
    parser.add_argument("--no-debug", dest="debug", action="store_false", help="Disable debug output")
    parser.set_defaults(debug=True)
    args = parser.parse_args()

    local_tz = ZoneInfo(args.tz)
    def log(msg: str) -> None:
        if args.debug:
            print(f"[DEBUG] {msg}")

    poll_count = 0
    while True:
        poll_count += 1
        now_utc = datetime.now(timezone.utc)
        now_local = now_utc.astimezone(local_tz)
        print(f"\nPOLL #{poll_count} at {now_local:%Y-%m-%d %H:%M:%S %Z}")
        ics_bytes = fetch_ics(args.url, args.timeout, log)
        events = parse_events(ics_bytes, args.window_days, local_tz, log)
        print_upcoming(events, now_utc, local_tz, args.max_events)
        if args.poll_minutes <= 0:
            break
        sleep_seconds = max(1, int(args.poll_minutes * 60))
        log(f"Sleeping for {sleep_seconds} seconds...")
        time.sleep(sleep_seconds)


if __name__ == "__main__":
    main()