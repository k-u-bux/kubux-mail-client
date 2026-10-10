"""Calendar invitations (text/calendar) in mail files.

Outlook and Exchange send an invitation as a `text/calendar` MIME part whose
payload is an iCalendar (RFC 5545) document; it usually has no file name and
comes next to an empty `text/plain` alternative, so it tends to be invisible in
a mail viewer.  This module owns everything about such a part that needs
neither the mail tree nor a widget:

* `parse_calendar()`          - dependency-free ICS reader (VCALENDAR/VEVENT)
* `format_event_when()`       - the "Wed 2027-06-30 12:30-14:00 (Europe/Berlin)" line
* `render_calendar_html()`    - the card shown in the message pane

The viewer finds the parts (MailViewer._collect_calendars) and calls in here:
picking a calendar part out of a MIME tree is a mail question, not a calendar
one.

An invitation is shown and exported exactly as it arrived: a Windows/Exchange
zone key ("W. Europe Standard Time") is printed as the document states it.  Such
keys do occur in ordinary .ics documents (Exchange published/ICS feeds, Outlook
exports, events an Outlook-side client pushed into CalDAV), so mapping them to a
tz database name is the calendar application's job — kubux-calendar owns that
(window ``library/windows_tz.py``) for every document that reaches a calendar,
invite or not.
"""

import html
import re
from datetime import datetime


# Content types that carry an iCalendar (RFC 5545) payload.  Outlook sends a
# meeting invitation as a text/calendar part inside a multipart/alternative,
# with neither filename nor Content-Disposition, so it never reaches
# mailparser's attachment list and would otherwise render as a blank mail.
CALENDAR_CONTENT_TYPES = frozenset({
    "text/calendar",
    "application/ics",
    "application/calendar",
    "text/x-vcalendar",
})


def _unfold_ical_lines(text):
    """Split an iCalendar text into content lines, undoing RFC 5545 folding.

    A long line is folded by inserting CRLF plus one space or tab; the
    continuation is glued back onto the previous line without that character.
    """
    lines = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def _split_ical_line(line):
    """Split one calendar content line into (name, params, value).

    name is upper-cased, params maps upper-cased parameter names to unquoted
    values, value is the raw (still escaped) property value.  The name is
    separated from the value by the first colon outside a quoted parameter.
    Returns (None, {}, None) for a line without a value separator.
    """
    quoted = False
    head = None
    value = None
    for i, ch in enumerate(line):
        if ch == '"':
            quoted = not quoted
        elif ch == ":" and not quoted:
            head, value = line[:i], line[i + 1:]
            break
    if head is None:
        return None, {}, None
    fields = head.split(";")
    params = {}
    for field in fields[1:]:
        if "=" in field:
            key, val = field.split("=", 1)
            params[key.strip().upper()] = val.strip().strip('"')
    return fields[0].strip().upper(), params, value


def _unescape_ical_text(value):
    r"""Undo RFC 5545 TEXT escaping (\n, \N, \, \; \\) in a property value."""
    out = []
    i = 0
    while i < len(value):
        if value[i] == "\\" and i + 1 < len(value):
            nxt = value[i + 1]
            out.append("\n" if nxt in "nN" else nxt)
            i += 2
        else:
            out.append(value[i])
            i += 1
    return "".join(out)


def parse_calendar(ics_text):
    """Parse an iCalendar text into (method, events).

    method is the VCALENDAR METHOD (REQUEST, CANCEL, ...); events is a list of
    VEVENT dicts holding only the properties that were present: 'summary',
    'location', 'description' (unescaped text), 'status', 'rrule', 'start'
    and 'end' as (value, params) pairs, 'organizer' as (value, params) and
    'attendees' as a list of (value, params).  VTIMEZONE and other components
    are skipped, folded lines are handled.
    """
    method = ""
    events = []
    current = None
    for line in _unfold_ical_lines(ics_text):
        name, params, value = _split_ical_line(line)
        if name is None:
            continue
        if name == "BEGIN":
            if value.strip().upper() == "VEVENT":
                current = {"attendees": []}
            continue
        if name == "END":
            if value.strip().upper() == "VEVENT" and current is not None:
                events.append(current)
                current = None
            continue
        if current is None:
            if name == "METHOD":
                method = value.strip().upper()
            continue
        if name == "ATTENDEE":
            current["attendees"].append((value, params))
        elif name == "ORGANIZER":
            current["organizer"] = (value, params)
        elif name == "DTSTART":
            current["start"] = (value, params)
        elif name == "DTEND":
            current["end"] = (value, params)
        elif name in ("SUMMARY", "LOCATION", "DESCRIPTION"):
            current[name.lower()] = _unescape_ical_text(value)
        elif name in ("STATUS", "RRULE"):
            current[name.lower()] = value.strip()
    return method, events


def _parse_ical_moment(value, params):
    """Return (all_day, datetime or None) for a DATE / DATE-TIME value.

    The datetime is the printed wall-clock time of the value; TZID based
    zones are not resolved (nothing here does timezone arithmetic).
    """
    raw = (value or "").strip()
    all_day = params.get("VALUE", "").upper() == "DATE" or (
        len(raw) == 8 and raw.isdigit())
    try:
        if all_day:
            return True, datetime.strptime(raw[:8], "%Y%m%d")
        digits = raw.rstrip("Z")
        fmt = "%Y%m%dT%H%M%S" if len(digits) == 15 else "%Y%m%dT%H%M"
        return False, datetime.strptime(digits, fmt)
    except ValueError:
        return all_day, None


def _ical_zone_label(value, params, all_day):
    """Zone suffix for a printed moment: "", " UTC" or " (Europe/Berlin)"."""
    if all_day:
        return ""
    if (value or "").strip().endswith("Z"):
        return " UTC"
    tzid = params.get("TZID")
    # Printed as the document states it, Windows key or not: the card shows the
    # invitation as it arrived.
    return f" ({tzid})" if tzid else ""


def _format_ical_moment(value, params):
    """Format one iCalendar moment for display; returns (text, datetime)."""
    all_day, moment = _parse_ical_moment(value, params)
    if moment is None:
        # Unparseable: show the raw value rather than nothing.
        return (value or "").strip(), None
    if all_day:
        return f"{moment:%a %Y-%m-%d} (all day)", moment
    zone = _ical_zone_label(value, params, all_day)
    return f"{moment:%a %Y-%m-%d %H:%M}{zone}", moment


def format_event_when(event):
    """Format an event's start (and end); a same-day meeting collapses to a
    range like 'Wed 2027-06-30 12:30-14:00 (TZID)'."""
    start = event.get("start")
    if not start:
        return ""
    start_text, start_dt = _format_ical_moment(*start)
    end = event.get("end")
    if not end:
        return start_text
    end_text, end_dt = _format_ical_moment(*end)
    start_all_day, _ = _parse_ical_moment(*start)
    if start_dt and end_dt and not start_all_day and start_dt.date() == end_dt.date():
        zone = _ical_zone_label(start[0], start[1], all_day=False)
        return f"{start_dt:%a %Y-%m-%d %H:%M}-{end_dt:%H:%M}{zone}"
    return f"{start_text} - {end_text}"


def _format_ical_person(value, params):
    """Format a calendar address as 'Name <addr>' (CN plus MAILTO value)."""
    address = (value or "").strip()
    if address.lower().startswith("mailto:"):
        address = address[len("mailto:"):]
    name = params.get("CN", "").strip()
    if name and address and name.lower() != address.lower():
        return f"{name} <{address}>"
    return name or address


def render_calendar_html(calendar):
    """Render one parsed calendar part as the rich text of its invite card.

    One card per part on purpose: a calendar is just another MIME part, so a
    multipart mail can carry several of them (say REQUEST and CANCEL, or two
    different events) and each gets its own card and its own button.
    Deliberately limited to the constructs a QLabel renders reliably (bold,
    <br>, <p>): the card is a label so that it hugs its text, and the button
    below it sits directly under the event instead of at the bottom of a
    pane-filling text browser.
    """
    method = calendar.get("method", "")
    heading = "Calendar invitation"
    if method:
        heading += f" &mdash; {html.escape(method)}"
    lines = [f"<b>{heading}</b>"]
    if method == "CANCEL":
        lines.append("<b>This message cancels the event.</b>")
    for event in calendar["events"]:
        if event.get("summary"):
            lines.append(f"<b>Event:</b> {html.escape(event['summary'])}")
        when = format_event_when(event)
        if when:
            lines.append(f"<b>When:</b> {html.escape(when)}")
        if event.get("location"):
            lines.append(f"<b>Where:</b> {html.escape(event['location'])}")
        if event.get("organizer"):
            lines.append(f"<b>Organizer:</b> {html.escape(_format_ical_person(*event['organizer']))}")
        if event.get("attendees"):
            people = [html.escape(_format_ical_person(*a)) for a in event["attendees"]]
            lines.append("<b>Attendees:</b><br>"
                         + "<br>".join(f"&nbsp;&nbsp;&nbsp;&nbsp;{p}" for p in people))
        if event.get("status"):
            lines.append(f"<b>Status:</b> {html.escape(event['status'])}")
        if event.get("rrule"):
            lines.append(f"<b>Repeats:</b> {html.escape(event['rrule'])}")
        if event.get("description"):
            notes = html.escape(event["description"]).replace("\n", "<br>")
            lines.append(f"<b>Notes:</b> {notes}")
    return "<p>" + "<br>".join(lines) + "</p>"