#!/usr/bin/env python3
"""
ical_to_bacnet_gateway.py
=========================

This proof‑of‑concept demonstrates how to convert an iCalendar (ICS) feed
into a BACnet schedule.  It uses the asynchronous BACpypes3 library to
expose a minimal BACnet device with three objects:

* A **ScheduleObject** whose weekly schedule is derived from the next
  seven days of events in a given iCal feed.  When no events are
  scheduled for a day, the schedule defaults to OFF (0).  When events
  occur, that day’s schedule toggles to ON (1) at the event start and
  back to OFF at the event end.  All‑day events (common for holidays)
  force the entire day off.
* An **AnalogValueObject** named ``next-event-time`` whose
  ``presentValue`` is the UNIX timestamp (seconds since 1970‑01‑01) for
  the next upcoming event.  If no events remain in the window, the
  value is ``0.0``.
* A **BinaryValueObject** named ``next-event-state`` whose
  ``presentValue`` is ``active`` when the next upcoming event will be
  ON (1) and ``inactive`` when it will be OFF (0).

This script is not a fully featured gateway: it does not support
exceptions beyond the next seven days, does not handle overlapping
events, and does not update the schedule mid‑day when events end.  It
should be treated as a starting point for building a robust gateway.

Usage::

    python ical_to_bacnet_gateway.py \
        --url "https://example.com/mycalendar.ics" \
        --name "MyCalendarDevice" \
        --instance 12345 \
        --tz America/Chicago

Optional arguments allow you to set the HTTP timeout, polling
interval, and debug verbosity.  See ``python ical_to_bacnet_gateway.py
--help`` for details.

Dependencies
------------
This script requires Python 3.9+ and the following packages::

    pip install bacpypes3 requests icalendar "recurring-ical-events>=3" python-dateutil tzdata

The BACpypes3 library is the asyncio rewrite of the classic BACpypes
stack.  Please ensure you do *not* install the legacy ``bacpypes``
package alongside bacpypes3, as the two are incompatible.

Limitations
-----------
* **Weekly schedule only** – The gateway computes a seven‑day rolling
  weekly schedule based on events occurring in the next seven days.  If
  your calendar contains recurring events that extend beyond this
  window, they will not appear until the next refresh.
* **All‑day holidays** – All‑day events set the day’s schedule to
  OFF (0) for the entire day.  You could invert this logic (treat
  holidays as occupied) by modifying the ``events_to_weekly_schedule``
  function.
* **Single value** – All events are treated as a binary on/off.  You
  could extend the schedule to use Analog values or multi‑state values
  by parsing event summaries and mapping them to numeric values.
"""

from __future__ import annotations

import asyncio
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

from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.app import Application
from bacpypes3.local.analog import AnalogValueObject
from bacpypes3.local.binary import BinaryValueObject
from bacpypes3.local.schedule import ScheduleObject
from bacpypes3.local.cmd import Commandable
from bacpypes3.basetypes import DailySchedule, TimeValue, DateRange
from bacpypes3.primitivedata import Integer, Null, Time, Date, Real
from bacpypes3.debugging import ModuleLogger


_log = ModuleLogger(globals())

# ---------- iCalendar Utilities (copied from the test script) ----------
CACHE_ICS = "calendar_cache.ics"
CACHE_META = "calendar_cache_meta.json"


def load_meta() -> dict:
    if os.path.exists(CACHE_META):
        with open(CACHE_META, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_meta(meta: dict) -> None:
    with open(CACHE_META, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)


def fetch_ics(url: str, timeout: int, log) -> bytes:
    meta = load_meta()
    headers: dict[str, str] = {}
    if "etag" in meta:
        headers["If-None-Match"] = meta["etag"]
    if "last_modified" in meta:
        headers["If-Modified-Since"] = meta["last_modified"]
    response = requests.get(url, headers=headers, timeout=timeout)
    if response.status_code == 304 and os.path.exists(CACHE_ICS):
        return open(CACHE_ICS, "rb").read()
    response.raise_for_status()
    content = response.content
    with open(CACHE_ICS, "wb") as f:
        f.write(content)
    new_meta = {
        "etag": response.headers.get("ETag"),
        "last_modified": response.headers.get("Last-Modified"),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    save_meta({k: v for k, v in new_meta.items() if v})
    return content


def normalize_dt(dt, local_tz: ZoneInfo) -> datetime | None:
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    if hasattr(dt, "year") and hasattr(dt, "month") and hasattr(dt, "day"):
        return datetime(dt.year, dt.month, dt.day, 0, 0, tzinfo=local_tz)
    raise ValueError(f"Unsupported date type: {type(dt)}")


def parse_events(ics_bytes: bytes, window_days: int, local_tz: ZoneInfo):
    cal = icalendar.Calendar.from_ical(ics_bytes)
    now = datetime.now(timezone.utc)
    window_end = now + timedelta(days=window_days)
    events = recurring_ical_events.of(cal).between(now, window_end)
    parsed: list[tuple[datetime, datetime, str]] = []
    for ev in events:
        summary = str(ev.get("SUMMARY", "(no title)"))
        dtstart_raw = ev.decoded("DTSTART", None)
        dtend_raw = ev.decoded("DTEND", None)
        dtstart = normalize_dt(dtstart_raw, local_tz)
        dtend = normalize_dt(dtend_raw, local_tz) if dtend_raw else None
        parsed.append((dtstart, dtend, summary))
    parsed.sort(key=lambda x: x[0])
    return parsed


# ---------- BACnet Schedule Construction ----------

def events_to_weekly_schedule(events: list[tuple[datetime, datetime, str]], local_tz: ZoneInfo) -> list[DailySchedule]:
    """
    Convert a list of events into a list of seven DailySchedule objects.

    Each element of the returned list corresponds to Monday through Sunday.
    For days with no events the daySchedule contains a single TimeValue at
    midnight with value 0.  For each event that falls within the next
    seven days, the corresponding day schedule toggles to 1 at the
    start time and back to 0 at the end time.  All‑day events (where
    start and end occur on midnight boundaries) set the whole day to 0.
    """
    # Initialize each day as off all day
    daily_entries: list[list[TimeValue]] = []
    for _ in range(7):
        # default off at midnight
        daily_entries.append([TimeValue(time=Time((0, 0, 0, 0)), value=Integer(0))])

    now = datetime.now(timezone.utc)
    end_window = now + timedelta(days=7)
    for (start_dt, end_dt, summary) in events:
        # Skip events outside the next seven days
        if start_dt < now or start_dt > end_window:
            continue
        # Determine day index (Monday=0 ... Sunday=6)
        day_index = start_dt.astimezone(local_tz).weekday()
        # Determine if all‑day event (duration >= 23h or none)
        all_day = False
        if end_dt is None:
            all_day = True
        else:
            dur = (end_dt - start_dt).total_seconds()
            if dur >= 23 * 3600:  # treat ~24h events as all day
                all_day = True
        if all_day:
            # override entire day: single entry at midnight with value 0
            daily_entries[day_index] = [TimeValue(time=Time((0, 0, 0, 0)), value=Integer(0))]
            continue
        # For timed events, toggle schedule on at start and off at end
        start_local = start_dt.astimezone(local_tz)
        end_local = end_dt.astimezone(local_tz) if end_dt else None
        # Convert to Time tuple (h, m, s, hundredths)
        def time_tuple(dt: datetime) -> tuple[int, int, int, int]:
            return (dt.hour, dt.minute, dt.second, 0)
        # Append start on and end off
        daily_entries[day_index].append(TimeValue(time=Time(time_tuple(start_local)), value=Integer(1)))
        if end_local:
            daily_entries[day_index].append(TimeValue(time=Time(time_tuple(end_local)), value=Integer(0)))

    # Convert each day's list to DailySchedule, sorting by time
    weekly_schedule: list[DailySchedule] = []
    for entries in daily_entries:
        # Sort by time-of-day (Time objects compare lexicographically)
        entries_sorted = sorted(entries, key=lambda tv: (tv.time.hour, tv.time.minute, tv.time.second, tv.time.hundredths))
        weekly_schedule.append(DailySchedule(daySchedule=entries_sorted))
    return weekly_schedule


# ---------- BACnet Application Classes ----------

class CommandableAnalogValueObject(Commandable, AnalogValueObject):
    """A Commandable Analog Value used for next event time."""


class CommandableBinaryValueObject(Commandable, BinaryValueObject):
    """A Commandable Binary Value used for next event state."""


class IcalBACnetGateway:
    """Main application class that ties together iCalendar parsing and BACnet objects."""

    def __init__(self, url: str, tzname: str, name: str, instance: int, poll_minutes: float, timeout: int, debug: bool):
        self.url = url
        self.local_tz = ZoneInfo(tzname)
        self.poll_seconds = max(1.0, poll_minutes * 60.0) if poll_minutes > 0 else 0.0
        self.timeout = timeout
        self.debug = debug
        # Set up BACnet application
        parser = SimpleArgumentParser(description="BACnet iCalendar Gateway")
        # Provide defaults; allow overrides via environment variables or command line
        parser.add_argument("--name", default=name)
        parser.add_argument("--instance", type=int, default=instance)
        parser.add_argument("--address", help="Override BACnet address (see bacpypes3 docs)")
        parser.add_argument("--debug", action="store_true")
        args = parser.parse_args([])  # parse no CLI args; we use constructor params instead
        # If debug flag from CLI or from constructor
        args.debug = args.debug or debug
        # Initialize BACnet app
        self.app = Application.from_args(args)
        # Create schedule object with placeholder weekly schedule
        initial_schedule = [DailySchedule(daySchedule=[TimeValue(time=Time((0, 0, 0, 0)), value=Integer(0))]) for _ in range(7)]
        effective_period = DateRange(
            startDate=Date(self._bacnet_date_tuple(datetime.now(self.local_tz).year, 1, 1)),
            endDate=Date(self._bacnet_date_tuple(datetime.now(self.local_tz).year + 10, 12, 31)),
        )
        self.schedule_obj = ScheduleObject(
            objectIdentifier=("schedule", 1),
            objectName="iCal-Schedule",
            presentValue=Integer(0),
            weeklySchedule=initial_schedule,
            scheduleDefault=Integer(0),
            effectivePeriod=effective_period,
            description="Schedule derived from iCalendar feed",
        )
        # Next event time as seconds since epoch (float)
        self.next_event_time = CommandableAnalogValueObject(
            objectIdentifier=("analogValue", 1001),
            objectName="next-event-time",
            presentValue=0.0,
            statusFlags=[0, 0, 0, 0],
            units="seconds",
            description="Unix timestamp of next iCal event start",
        )
        # Next event state (active/inactive)
        self.next_event_state = CommandableBinaryValueObject(
            objectIdentifier=("binaryValue", 1001),
            objectName="next-event-state",
            presentValue="inactive",
            statusFlags=[0, 0, 0, 0],
            description="State of next iCal event (active/inactive)",
        )
        # Register objects
        for obj in [self.schedule_obj, self.next_event_time, self.next_event_state]:
            self.app.add_object(obj)
        _log.info("BACnet objects registered.")
        # Kick off periodic update
        asyncio.create_task(self.update_loop())

    def _bacnet_date_tuple(self, year: int, month: int, day: int) -> tuple[int, int, int, int]:
        """Helper: convert a Gregorian date into BACnet date tuple (year offset, month, day, weekday)."""
        dt = datetime(year, month, day)
        bacnet_day = dt.weekday() + 1  # BACnet Monday=1 ... Sunday=7
        return (year - 1900, month, day, bacnet_day)

    async def update_loop(self) -> None:
        """Background task to refresh the schedule and next event points."""
        while True:
            try:
                await self.refresh_schedule()
            except Exception as e:
                _log.error(f"Error refreshing schedule: {e}")
            if self.poll_seconds <= 0:
                break
            await asyncio.sleep(self.poll_seconds)

    async def refresh_schedule(self) -> None:
        """Fetch the iCal feed, update the weekly schedule and next event points."""
        if self.debug:
            _log.debug("Fetching iCal feed...")
        ics_bytes = fetch_ics(self.url, self.timeout, lambda msg: _log.debug(msg) if self.debug else None)
        events = parse_events(ics_bytes, 7, self.local_tz)
        # Build weekly schedule
        weekly_schedule = events_to_weekly_schedule(events, self.local_tz)
        self.schedule_obj.weeklySchedule = weekly_schedule
        # Compute next event
        now = datetime.now(timezone.utc)
        next_event = None
        for e in events:
            if e[0] >= now:
                next_event = e
                break
        if next_event:
            # seconds since epoch for next event start
            ts = next_event[0].timestamp()
            self.next_event_time.presentValue = ts
            # Determine state: 1 means ON, 0 means OFF – we treat events as ON
            self.next_event_state.presentValue = "active"
        else:
            self.next_event_time.presentValue = 0.0
            self.next_event_state.presentValue = "inactive"
        if self.debug:
            _log.debug("Schedule and next event updated.")


async def main_async(args) -> None:
    # Construct and run gateway
    gateway = IcalBACnetGateway(
        url=args.url,
        tzname=args.tz,
        name=args.name,
        instance=args.instance,
        poll_minutes=args.poll_minutes,
        timeout=args.timeout,
        debug=args.debug,
    )
    # Keep running until cancelled
    await asyncio.Future()


def main() -> None:
    parser = argparse.ArgumentParser(description="iCalendar to BACnet gateway (concept demo)")
    parser.add_argument("--url", required=True, help="iCalendar feed URL")
    parser.add_argument("--tz", default="America/Chicago", help="Local timezone for schedule evaluation")
    parser.add_argument("--name", default="IcalBACnetGateway", help="BACnet device name")
    parser.add_argument("--instance", type=int, default=1234, help="BACnet device instance number")
    parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout for iCal download")
    parser.add_argument("--poll-minutes", type=float, default=60.0, help="Polling interval in minutes (0 for no polling)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()
    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        _log.info("Keyboard interrupt, exiting.")


if __name__ == "__main__":
    main()