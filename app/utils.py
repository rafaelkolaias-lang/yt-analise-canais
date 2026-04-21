# -*- coding: utf-8 -*-
"""Utilitários puros: log, parse de duração ISO 8601, datas, helpers numéricos."""
import time
from datetime import datetime, timezone
from dateutil.parser import isoparse


class QuotaExceeded(Exception):
    pass


def log(msg: str):
    print(msg, flush=True)


def _sleep_backoff(attempt):
    time.sleep(min(2.0 * attempt, 6.0))


def iso8601_duration_to_minutes(iso_duration: str) -> int:
    total_seconds = 0
    hours = minutes = seconds = 0
    dur = iso_duration
    if dur.startswith('P'):
        if 'T' in dur:
            p_part, t_part = dur[1:].split('T', 1)
        else:
            p_part, t_part = dur[1:], ''
        if 'D' in p_part:
            days_str = p_part.split('D')[0]
            try:
                days = int(days_str)
                hours += days * 24
            except Exception:
                pass
        dur = 'PT' + t_part
    dur = dur.replace('PT', '')
    num = ''
    for ch in dur:
        if ch.isdigit():
            num += ch
        else:
            if ch == 'H' and num:
                hours += int(num); num = ''
            elif ch == 'M' and num:
                minutes += int(num); num = ''
            elif ch == 'S' and num:
                seconds += int(num); num = ''
    total_seconds = hours * 3600 + minutes * 60 + seconds
    return total_seconds // 60


def _as_aware_utc(iso_str):
    """isoparse + garante tzinfo. Strings sem timezone são tratadas como UTC."""
    dt = isoparse(iso_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def human_date(iso_str: str) -> str:
    return _as_aware_utc(iso_str).strftime("%Y-%m-%d")


def human_age_days(iso_str: str) -> int:
    return (datetime.now(timezone.utc) - _as_aware_utc(iso_str)).days


def days_since(iso_str: str) -> int:
    return max(1, (datetime.now(timezone.utc) - _as_aware_utc(iso_str)).days)


def safe_ratio(num, den):
    try:
        if num is None or den in (None, 0):
            return None
        return num / den
    except Exception:
        return None


def fmt_int(n):
    return f"{n:,}".replace(",", ".") if isinstance(n, int) else "—"


def chunked(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]
