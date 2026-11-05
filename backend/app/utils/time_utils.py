"""
Sortyx 2.0 — Time utilities.

Provides UTC and Indian Standard Time (IST, UTC+5:30) datetime conversions
and formatting helpers. All database writes use UTC timestamptz.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta, date

# Indian Standard Time (UTC+05:30)
IST_OFFSET = timedelta(hours=5, minutes=30)
IST = timezone(IST_OFFSET, name="IST")


def get_utc_now() -> datetime:
    """Return the current time in UTC with timezone information."""
    return datetime.now(timezone.utc)


def get_ist_now() -> datetime:
    """Return the current time converted to Indian Standard Time."""
    return datetime.now(IST)


def utc_to_ist(dt: datetime) -> datetime:
    """Convert an arbitrary datetime to IST.

    If naive, assumes UTC.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST)


def get_ist_today_range() -> tuple[datetime, datetime]:
    """Return (start_utc, end_utc) corresponding to today in IST calendar day.

    Used for database queries that count events 'today' in Indian local time.
    """
    now_ist = get_ist_now()
    today_ist = now_ist.date()
    start_ist = datetime.combine(today_ist, datetime.min.time(), tzinfo=IST)
    end_ist = start_ist + timedelta(days=1)

    # Convert back to UTC for postgresql queries
    return start_ist.astimezone(timezone.utc), end_ist.astimezone(timezone.utc)


def format_ist_time(dt: Optional[datetime] = None) -> str:
    """Format time as '10:24 AM' in IST."""
    if dt is None:
        dt = get_ist_now()
    else:
        dt = utc_to_ist(dt)
    return dt.strftime("%I:%M %p")


def format_ist_date(dt: Optional[datetime] = None) -> str:
    """Format date as 'Tue, Nov 4, 2026' in IST."""
    if dt is None:
        dt = get_ist_now()
    else:
        dt = utc_to_ist(dt)
    return dt.strftime("%a, %b %d, %Y")

