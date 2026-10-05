"""Decide when posts go out: fixed slots plus random slots inside the posting window."""
from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta

from . import settings


def _parse_hhmm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def slots_for_day(day: date, cfg: dict | None = None, rng: random.Random | None = None) -> list[datetime]:
    """Return timezone-aware publish times for `day`, sorted, all inside the window."""
    cfg = cfg or settings.config()
    rng = rng or random.Random()
    sch = cfg["schedule"]
    tz = settings.tz(cfg)
    start_t, end_t = (_parse_hhmm(x) for x in sch["window"])
    start = datetime.combine(day, start_t, tzinfo=tz)
    end = datetime.combine(day, end_t, tzinfo=tz)
    n = int(sch.get("posts_per_day", 1))
    jitter = int(sch.get("jitter_minutes", 0))

    slots: list[datetime] = []
    for hhmm in (sch.get("fixed_times") or [])[:n]:
        t = datetime.combine(day, _parse_hhmm(hhmm), tzinfo=tz)
        if jitter:
            t += timedelta(minutes=rng.randint(-jitter, jitter))
        slots.append(min(max(t, start), end))

    span = int((end - start).total_seconds() // 60)
    while len(slots) < n and span > 0:
        cand = start + timedelta(minutes=rng.randint(0, span))
        # keep random slots at least 60 minutes away from existing ones
        if all(abs((cand - s).total_seconds()) >= 3600 for s in slots) or len(slots) * 60 >= span:
            slots.append(cand)
    return sorted(s.replace(second=0, microsecond=0) for s in slots)


def is_quiet_hour(now_local: datetime, quiet: list[int] | None) -> bool:
    if not quiet:
        return False
    start, end = quiet
    h = now_local.hour
    return start <= h < end if start <= end else (h >= start or h < end)
