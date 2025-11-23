# icalender-to-bacnet
Concept idea to create a generic icalender to BACnet gateway.

---

<details>
<summary>🐍 Python Setup</summary>

Create a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate
```
Packages:
```bash
pip install requests icalendar recurring-ical-events python-dateutil tzdata bacpypes3
```

### Args

```bash
python scripts/ical_event_test.py \
    --url "YOUR_ICS_URL" \
    --tz America/Chicago \
    --max-events 10 \
    --poll-minutes 0
```

Useful options:

* `--poll-minutes 10` → check feed every 10 minutes
* `--no-debug` → quiet mode
* `--window-days 180` → expand events farther ahead

</details>

---

<details>
<summary>🧪 Test With Google’s US Holiday Calendar</summary>


Run the test script which also works fine on Windows in PowerShell:

```bash
python scripts/ical_event_test.py --url "https://calendar.google.com/calendar/ical/en.usa%23holiday%40group.v.calendar.google.com/public/basic.ics"
```

You will see the US Holidays from Googles calender:

```text
POLL #1 at 2025-11-23 09:27:31 CST
[DEBUG] HTTP status: 200
[DEBUG] Downloaded 121366 bytes.

=== Upcoming Events ===

Next 10 events:
------------------------------------------------------------
 1. Thanksgiving Day
    When: 2025-11-27 00:00 CST
    Ends: 2025-11-28 00:00 CST
    In:   3d 14h 32m
    Dur:  1440 min

 2. Black Friday
    When: 2025-11-28 00:00 CST
    Ends: 2025-11-29 00:00 CST
    In:   4d 14h 32m
    Dur:  1440 min

 3. Christmas Eve
    When: 2025-12-24 00:00 CST
    Ends: 2025-12-25 00:00 CST
    In:   30d 14h 32m
    Dur:  1440 min

 4. Christmas Day
    When: 2025-12-25 00:00 CST
    Ends: 2025-12-26 00:00 CST
    In:   31d 14h 32m
    Dur:  1440 min

 5. New Year's Eve
    When: 2025-12-31 00:00 CST
    Ends: 2026-01-01 00:00 CST
    In:   37d 14h 32m
    Dur:  1440 min

 6. New Year's Day
    When: 2026-01-01 00:00 CST
    Ends: 2026-01-02 00:00 CST
    In:   38d 14h 32m
    Dur:  1440 min

 7. Martin Luther King Jr. Day
    When: 2026-01-19 00:00 CST
    Ends: 2026-01-20 00:00 CST
    In:   56d 14h 32m
    Dur:  1440 min

 8. Valentine's Day
    When: 2026-02-14 00:00 CST
    Ends: 2026-02-15 00:00 CST
    In:   82d 14h 32m
    Dur:  1440 min

 9. Presidents' Day
    When: 2026-02-16 00:00 CST
    Ends: 2026-02-17 00:00 CST
    In:   84d 14h 32m
    Dur:  1440 min

10. Daylight Saving Time starts
    When: 2026-03-08 00:00 CST
    Ends: 2026-03-09 00:00 CDT
    In:   104d 14h 32m
    Dur:  1440 min

------------------------------------------------------------
Next event begins in: 3d 14h 32m
```
</details>

---

<details>
<summary>🗓️ Run a test on your own ICS calender</summary>

To get your own ICS URL from Google Calendar:

1. Calendar Settings → **Integrate Calendar**
2. Copy **Secret address in iCal format**
   (Treat this like a password)  

![Leave Temp Snip](https://github.com/bbartling/icalender-to-bacnet/blob/develop/googleSnip.png)  

I made an additional Testing Schedule on my personal Google account which is a recurring event named `Occupied`:  

![Leave Temp Snip](https://github.com/bbartling/icalender-to-bacnet/blob/develop/bensTestCalenderSnip.png)  

Tested on Windows in PowerShell:

```
> python scripts/ical_event_test.py --url "https://calendar.google.com/calendar/ical/4d67f1779bf6d9c1c1e3615a449f2f2469d0d4aa0136faa16a7eeebd0ae1ebbe%40group.calendar.google.com/private-d58ed4b8a80b7356cbac2e74ae596c0a/basic.ics"

POLL #1 at 2025-11-23 09:53:04 CST
[DEBUG] HTTP status: 200
[DEBUG] Downloaded 957 bytes.

=== Upcoming Events ===

Next 10 events:
------------------------------------------------------------
 1. Occupied
    When: 2025-11-24 08:00 CST
    Ends: 2025-11-24 17:00 CST
    In:   22h 6m
    Dur:  540 min

 2. Occupied
    When: 2025-11-25 08:00 CST
    Ends: 2025-11-25 17:00 CST
    In:   1d 22h 6m
    Dur:  540 min

 3. Occupied
    When: 2025-11-26 08:00 CST
    Ends: 2025-11-26 17:00 CST
    In:   2d 22h 6m
    Dur:  540 min

 4. Occupied
    When: 2025-11-27 08:00 CST
    Ends: 2025-11-27 17:00 CST
    In:   3d 22h 6m
    Dur:  540 min

 5. Occupied
    When: 2025-11-28 08:00 CST
    Ends: 2025-11-28 17:00 CST
    In:   4d 22h 6m
    Dur:  540 min

 6. Occupied
    When: 2025-12-01 08:00 CST
    Ends: 2025-12-01 17:00 CST
    In:   7d 22h 6m
    Dur:  540 min

 7. Occupied
    When: 2025-12-02 08:00 CST
    Ends: 2025-12-02 17:00 CST
    In:   8d 22h 6m
    Dur:  540 min

 8. Occupied
    When: 2025-12-03 08:00 CST
    Ends: 2025-12-03 17:00 CST
    In:   9d 22h 6m
    Dur:  540 min

 9. Occupied
    When: 2025-12-04 08:00 CST
    Ends: 2025-12-04 17:00 CST
    In:   10d 22h 6m
    Dur:  540 min

10. Occupied
    When: 2025-12-05 08:00 CST
    Ends: 2025-12-05 17:00 CST
    In:   11d 22h 6m
    Dur:  540 min

------------------------------------------------------------
Next event begins in: 22h 6m

```

</details>

---

<details>
<summary>🤖 Run the BACnet Gateway (POC)</summary>


* ***NOT FINISHED PROOF OF CONCEPT***

This launches a minimal BACnet server that:

* builds a **weekly BACnet ScheduleObject** from iCal events
* exposes **next event timestamp**
* exposes **next event state (BinaryValue)**
* periodically refreshes from the ICS feed

Run it:

```bash
python scripts/ical_to_bacnet_gateway.py \
    --name "iCal-BACnet-GW" \
    --instance 12345 \
    --url "YOUR_ICS_URL" \
    --tz America/Chicago \
    --poll-minutes 10 \
    --debug
```

### Key flags

| Flag             | Description                                        |
| ---------------- | -------------------------------------------------- |
| `--name`         | BACnet device name                                 |
| `--instance`     | BACnet device instance number                      |
| `--address`      | Optional local bind, e.g. `10.200.200.50/24:47808` |
| `--url`          | ICS feed URL                                       |
| `--tz`           | Timezone for event interpretation                  |
| `--poll-minutes` | How often to refresh ICS feed                      |
| `--debug`        | Enable debug logging                               |

---

## 📡 BACnet Objects Exposed

When scanning with YABE, BAC0, BACnet Explorer, or Niagara, you should discover:

### 1. **Schedule,1**

* `objectName = "ical-schedule"`
* `weeklySchedule` built from repeating/expanded iCal events
* `presentValue` reflects current active state

### 2. **Analog Value,10** → `"next-event-time"`

* `presentValue` = **UNIX timestamp** for next event start
* Useful for sequencing or triggering transitions

### 3. **Binary Value,10** → `"next-event-state"`

* `presentValue` = **ACTIVE / INACTIVE**
* Currently assumes:

  * ACTIVE → occupied
  * INACTIVE → unoccupied

If the iCal feed has no future events:

* schedule remains "unoccupied"
* next-event values revert to defaults

</details>

---

## 📜 License

Everything here is **MIT Licensed** — free, open source, and made for the BAS community.  
Use it, remix it, or improve it — just share it forward so others can benefit too. 🥰🌍


【MIT License】

Copyright 2025 Ben Bartling

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
