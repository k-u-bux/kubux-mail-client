"""Calendar invitations (text/calendar) in mail files.

Outlook and Exchange send an invitation as a `text/calendar` MIME part whose
payload is an iCalendar (RFC 5545) document; it usually has no file name and
comes next to an empty `text/plain` alternative, so it tends to be invisible in
a mail viewer.  This module owns everything about such a part that needs
neither the mail tree nor a widget:

* `parse_calendar()`          - dependency-free ICS reader (VCALENDAR/VEVENT)
* `format_event_when()`       - the "Wed 2027-06-30 12:30-14:00 (Europe/Berlin)" line
* `render_calendar_html()`    - the card shown in the message pane
* `standardize_ics_timezones()` - rewrite Windows zone keys before exporting
* `WINDOWS_TO_IANA`           - Windows -> standard (IANA) zone mapping

The viewer finds the parts (MailViewer._collect_calendars) and calls in here:
picking a calendar part out of a MIME tree is a mail question, not a calendar
one.  See references/windows-timezone-keys.md in the kubux-mail-client skill.
"""

import html
import re
from datetime import datetime

from PySide6.QtCore import QTimeZone


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
    # Show the standard name: a Windows key ("W. Europe Standard Time") is not
    # a zone anybody can look up.
    return f" ({standard_timezone_name(tzid)})" if tzid else ""


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


# iCalendar TZID occurrences: the TZID property of a VTIMEZONE block
# ("TZID:W. Europe Standard Time") and the TZID parameter of DTSTART/DTEND
# (";TZID=W. Europe Standard Time"), whose value may be quoted.
TZID_PROPERTY_RE = re.compile(r'^(TZID:)("?)([^":;]*)\2\s*$')
TZID_PARAMETER_RE = re.compile(r'(;TZID=)("?)([^":;]*)\2')


# Windows/Exchange time zone keys -> standard (IANA) time zone names.
#
# Outlook and Exchange stamp invitations with a Windows zone key, e.g.
# "DTSTART;TZID=W. Europe Standard Time:20270630T123000", plus a VTIMEZONE
# block of the same name.  That key is no IANA tz database name, so it means
# nothing to any other calendar application: it must be mapped to the standard
# name (here Europe/Berlin) before it is displayed or exported.
#
# Source: CLDR common/supplemental/windowsZones.xml, the territory="001" rows —
# the reference Windows -> tzdb mapping, from the same data ICU is built from —
# fetched 2026-10-08 from
# https://raw.githubusercontent.com/unicode-org/cldr/main/common/supplemental/windowsZones.xml
# sha256 9cf3db6a31fb382fee21b70be6feba1e82766b0fcd06e6261fb7936a73e537ff,
# 139 keys.  Zones renamed since that revision were modernised against tzdata's
# link table, but only within the same area (a renamed zone is a spelling fix;
# a merger such as Atlantic/Reykjavik -> Africa/Abidjan is not chased, the CLDR
# name stays a valid tzdb name):
#   US Eastern: America/Indianapolis -> America/Indiana/Indianapolis, Argentina: America/Buenos_Aires -> America/Argentina/Buenos_Aires,
#   Greenland: America/Godthab -> America/Nuuk, FLE: Europe/Kiev -> Europe/Kyiv, India: Asia/Calcutta -> Asia/Kolkata,
#   Nepal: Asia/Katmandu -> Asia/Kathmandu, Myanmar: Asia/Rangoon -> Asia/Yangon.
# Regenerate by re-reading the territory="001" mapZone rows of that file.
WINDOWS_TO_IANA = {
    "AUS Central Standard Time": "Australia/Darwin",
    "AUS Eastern Standard Time": "Australia/Sydney",
    "Afghanistan Standard Time": "Asia/Kabul",
    "Alaskan Standard Time": "America/Anchorage",
    "Aleutian Standard Time": "America/Adak",
    "Altai Standard Time": "Asia/Barnaul",
    "Arab Standard Time": "Asia/Riyadh",
    "Arabian Standard Time": "Asia/Dubai",
    "Arabic Standard Time": "Asia/Baghdad",
    "Argentina Standard Time": "America/Argentina/Buenos_Aires",
    "Astrakhan Standard Time": "Europe/Astrakhan",
    "Atlantic Standard Time": "America/Halifax",
    "Aus Central W. Standard Time": "Australia/Eucla",
    "Azerbaijan Standard Time": "Asia/Baku",
    "Azores Standard Time": "Atlantic/Azores",
    "Bahia Standard Time": "America/Bahia",
    "Bangladesh Standard Time": "Asia/Dhaka",
    "Belarus Standard Time": "Europe/Minsk",
    "Bougainville Standard Time": "Pacific/Bougainville",
    "Canada Central Standard Time": "America/Regina",
    "Cape Verde Standard Time": "Atlantic/Cape_Verde",
    "Caucasus Standard Time": "Asia/Yerevan",
    "Cen. Australia Standard Time": "Australia/Adelaide",
    "Central America Standard Time": "America/Guatemala",
    "Central Asia Standard Time": "Asia/Bishkek",
    "Central Brazilian Standard Time": "America/Cuiaba",
    "Central Europe Standard Time": "Europe/Budapest",
    "Central European Standard Time": "Europe/Warsaw",
    "Central Pacific Standard Time": "Pacific/Guadalcanal",
    "Central Standard Time": "America/Chicago",
    "Central Standard Time (Mexico)": "America/Mexico_City",
    "Chatham Islands Standard Time": "Pacific/Chatham",
    "China Standard Time": "Asia/Shanghai",
    "Cuba Standard Time": "America/Havana",
    "Dateline Standard Time": "Etc/GMT+12",
    "E. Africa Standard Time": "Africa/Nairobi",
    "E. Australia Standard Time": "Australia/Brisbane",
    "E. Europe Standard Time": "Europe/Chisinau",
    "E. South America Standard Time": "America/Sao_Paulo",
    "Easter Island Standard Time": "Pacific/Easter",
    "Eastern Standard Time": "America/New_York",
    "Eastern Standard Time (Mexico)": "America/Cancun",
    "Egypt Standard Time": "Africa/Cairo",
    "Ekaterinburg Standard Time": "Asia/Yekaterinburg",
    "FLE Standard Time": "Europe/Kyiv",
    "Fiji Standard Time": "Pacific/Fiji",
    "GMT Standard Time": "Europe/London",
    "GTB Standard Time": "Europe/Bucharest",
    "Georgian Standard Time": "Asia/Tbilisi",
    "Greenland Standard Time": "America/Nuuk",
    "Greenwich Standard Time": "Atlantic/Reykjavik",
    "Haiti Standard Time": "America/Port-au-Prince",
    "Hawaiian Standard Time": "Pacific/Honolulu",
    "India Standard Time": "Asia/Kolkata",
    "Iran Standard Time": "Asia/Tehran",
    "Israel Standard Time": "Asia/Jerusalem",
    "Jordan Standard Time": "Asia/Amman",
    "Kaliningrad Standard Time": "Europe/Kaliningrad",
    "Korea Standard Time": "Asia/Seoul",
    "Libya Standard Time": "Africa/Tripoli",
    "Line Islands Standard Time": "Pacific/Kiritimati",
    "Lord Howe Standard Time": "Australia/Lord_Howe",
    "Magadan Standard Time": "Asia/Magadan",
    "Magallanes Standard Time": "America/Punta_Arenas",
    "Marquesas Standard Time": "Pacific/Marquesas",
    "Mauritius Standard Time": "Indian/Mauritius",
    "Middle East Standard Time": "Asia/Beirut",
    "Montevideo Standard Time": "America/Montevideo",
    "Morocco Standard Time": "Africa/Casablanca",
    "Mountain Standard Time": "America/Denver",
    "Mountain Standard Time (Mexico)": "America/Mazatlan",
    "Myanmar Standard Time": "Asia/Yangon",
    "N. Central Asia Standard Time": "Asia/Novosibirsk",
    "Namibia Standard Time": "Africa/Windhoek",
    "Nepal Standard Time": "Asia/Kathmandu",
    "New Zealand Standard Time": "Pacific/Auckland",
    "Newfoundland Standard Time": "America/St_Johns",
    "Norfolk Standard Time": "Pacific/Norfolk",
    "North Asia East Standard Time": "Asia/Irkutsk",
    "North Asia Standard Time": "Asia/Krasnoyarsk",
    "North Korea Standard Time": "Asia/Pyongyang",
    "Omsk Standard Time": "Asia/Omsk",
    "Pacific SA Standard Time": "America/Santiago",
    "Pacific Standard Time": "America/Los_Angeles",
    "Pacific Standard Time (Mexico)": "America/Tijuana",
    "Pakistan Standard Time": "Asia/Karachi",
    "Paraguay Standard Time": "America/Asuncion",
    "Qyzylorda Standard Time": "Asia/Qyzylorda",
    "Romance Standard Time": "Europe/Paris",
    "Russia Time Zone 10": "Asia/Srednekolymsk",
    "Russia Time Zone 11": "Asia/Kamchatka",
    "Russia Time Zone 3": "Europe/Samara",
    "Russian Standard Time": "Europe/Moscow",
    "SA Eastern Standard Time": "America/Cayenne",
    "SA Pacific Standard Time": "America/Bogota",
    "SA Western Standard Time": "America/La_Paz",
    "SE Asia Standard Time": "Asia/Bangkok",
    "Saint Pierre Standard Time": "America/Miquelon",
    "Sakhalin Standard Time": "Asia/Sakhalin",
    "Samoa Standard Time": "Pacific/Apia",
    "Sao Tome Standard Time": "Africa/Sao_Tome",
    "Saratov Standard Time": "Europe/Saratov",
    "Singapore Standard Time": "Asia/Singapore",
    "South Africa Standard Time": "Africa/Johannesburg",
    "South Sudan Standard Time": "Africa/Juba",
    "Sri Lanka Standard Time": "Asia/Colombo",
    "Sudan Standard Time": "Africa/Khartoum",
    "Syria Standard Time": "Asia/Damascus",
    "Taipei Standard Time": "Asia/Taipei",
    "Tasmania Standard Time": "Australia/Hobart",
    "Tocantins Standard Time": "America/Araguaina",
    "Tokyo Standard Time": "Asia/Tokyo",
    "Tomsk Standard Time": "Asia/Tomsk",
    "Tonga Standard Time": "Pacific/Tongatapu",
    "Transbaikal Standard Time": "Asia/Chita",
    "Turkey Standard Time": "Europe/Istanbul",
    "Turks And Caicos Standard Time": "America/Grand_Turk",
    "US Eastern Standard Time": "America/Indiana/Indianapolis",
    "US Mountain Standard Time": "America/Phoenix",
    "UTC": "Etc/UTC",
    "UTC+12": "Etc/GMT-12",
    "UTC+13": "Etc/GMT-13",
    "UTC-02": "Etc/GMT+2",
    "UTC-08": "Etc/GMT+8",
    "UTC-09": "Etc/GMT+9",
    "UTC-11": "Etc/GMT+11",
    "Ulaanbaatar Standard Time": "Asia/Ulaanbaatar",
    "Venezuela Standard Time": "America/Caracas",
    "Vladivostok Standard Time": "Asia/Vladivostok",
    "Volgograd Standard Time": "Europe/Volgograd",
    "W. Australia Standard Time": "Australia/Perth",
    "W. Central Africa Standard Time": "Africa/Lagos",
    "W. Europe Standard Time": "Europe/Berlin",
    "W. Mongolia Standard Time": "Asia/Hovd",
    "West Asia Standard Time": "Asia/Tashkent",
    "West Bank Standard Time": "Asia/Hebron",
    "West Pacific Standard Time": "Pacific/Port_Moresby",
    "Yakutsk Standard Time": "Asia/Yakutsk",
    "Yukon Standard Time": "America/Whitehorse",
}



def standard_timezone_name(tzid):
    """Map a time zone id to a standard (IANA) name.

    Outlook/Exchange use Windows zone keys ("W. Europe Standard Time"), which
    are no tz database names and mean nothing to other calendar applications;
    the CLDR mapping turns them into one ("Europe/Berlin").  Names that already
    look standard are returned as they are.
    """
    key = (tzid or "").strip().strip('"')
    if not key or "/" in key:
        return key
    name = WINDOWS_TO_IANA.get(key)
    if name:
        return name
    # Key not in the mapping (added since, or proprietary): fall back to any
    # zone Qt/ICU knows for it, whose offsets are the same by construction.
    ids = QTimeZone.windowsIdToIanaIds(key.encode("utf-8"))
    return bytes(ids[0]).decode("utf-8") if ids else key


def _fold_ical_line(line, limit=75):
    """Fold one content line to ``limit`` octets (RFC 5545 §3.1).

    Counts octets, not characters, and never splits a multi-byte character; a
    continuation line carries one leading space, which counts towards the limit
    too.  Short lines are returned unchanged.
    """
    if len(line.encode("utf-8")) <= limit:
        return line
    chunks = []
    current = ""
    used = 0
    for char in line:
        size = len(char.encode("utf-8"))
        if used + size > limit - (1 if chunks else 0):
            chunks.append(current)
            current = ""
            used = 0
        current += char
        used += size
    chunks.append(current)
    return "\r\n ".join(chunks)


def standardize_ics_timezones(ics_text):
    """Rewrite Windows/Exchange zone keys in an iCalendar text.

    Renames the TZID property of the VTIMEZONE blocks and the TZID parameters
    of DTSTART/DTEND alike, so the file stays self-consistent and every
    calendar application can resolve the zones by name.  Needed because the
    file is handed to xdg-open, where a Windows key is not resolvable.

    Lines are unfolded before and refolded after (a TZID may be folded across
    lines), which is why even untouched long lines come back refolded.
    """
    def rename(match):
        quote = match.group(2)
        return f"{match.group(1)}{quote}{standard_timezone_name(match.group(3))}{quote}"

    lines = _unfold_ical_lines(ics_text)
    while lines and not lines[-1]:
        lines.pop()
    folded = []
    for line in lines:
        line = TZID_PROPERTY_RE.sub(rename, line)
        line = TZID_PARAMETER_RE.sub(rename, line)
        folded.append(_fold_ical_line(line))
    return "\r\n".join(folded) + "\r\n"


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
