"""
XContest flight data fetcher.
Queries xcontest.org for recent XC flights near each paragliding site.
Results are cached for 6 hours to avoid hammering the site.
"""

import re
import threading
import time
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

_cache: dict = {}
_cache_lock = threading.Lock()
CACHE_TTL = 6 * 3600  # 6 hours

# Radius around each site to search for flights (metres)
DEFAULT_RADIUS_M = 20_000  # 20 km

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.xcontest.org/",
}

# Minimum distance (km) to count as a meaningful XC flight
MIN_XC_KM = 5.0

# How many days back to look for flights
DAYS_BACK = 30


def fetch_xc_flights(site: dict) -> dict:
    """Return recent XC flights near *site* (cached for 6 h)."""
    key = site["name"]
    with _cache_lock:
        entry = _cache.get(key)
        if entry and time.time() - entry[0] < CACHE_TTL:
            return entry[1]

    result = _query_xcontest(site["lat"], site["lon"])

    with _cache_lock:
        _cache[key] = (time.time(), result)

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _query_xcontest(lat: float, lon: float) -> dict:
    """Fetch and parse the XContest flight list for a lat/lon area."""
    url = "https://www.xcontest.org/world/en/flights/"
    params = {
        "list[start]": 0,
        "filter[route]": "free_flight",
        "filter[lat_lng]": f"{lat},{lon}",
        "filter[radius]": DEFAULT_RADIUS_M,
    }

    try:
        session = requests.Session()
        resp = session.get(url, params=params, headers=HEADERS, timeout=15)

        if resp.status_code != 200:
            return _empty(f"HTTP {resp.status_code}")

        flights = _parse_flights(resp.text)
        return {
            "flights": flights,
            "count": len(flights),
            "source_url": resp.url,
        }

    except requests.exceptions.Timeout:
        return _empty("Request timed out")
    except Exception as exc:
        return _empty(str(exc))


def _parse_flights(html: str) -> list:
    """
    Parse flight rows from XContest HTML.

    XContest renders a <table class="flights ..."> where each <tr class="flight …">
    contains cells for: pilot, launch site, takeoff date, km, pts, route, wing.
    Cell positions can vary, so we search by CSS class / data patterns.
    """
    soup = BeautifulSoup(html, "html.parser")
    flights = []

    # Find the flights table (class contains "flights")
    table = soup.find("table", class_=re.compile(r"\bflights\b"))
    if table is None:
        # Fallback: look for any table that has rows with class "flight"
        for t in soup.find_all("table"):
            if t.find("tr", class_=re.compile(r"\bflight\b")):
                table = t
                break

    if table is None:
        return flights

    for row in table.find_all("tr", class_=re.compile(r"\bflight\b")):
        flight = _parse_row(row)
        if flight:
            flights.append(flight)

    # Sort newest first
    flights.sort(key=lambda f: f.get("date", ""), reverse=True)
    return flights


def _parse_row(row) -> dict | None:
    """Extract date, distance, pilot, and route from a single flight row."""
    cells = row.find_all("td")
    if not cells:
        return None

    flight: dict = {}

    for cell in cells:
        cls = " ".join(cell.get("class", []))
        text = cell.get_text(" ", strip=True)

        # Date cell — XContest uses class "flew" or "date", value like "23.03.26" or "2026-03-23"
        if "flew" in cls or "date" in cls:
            date = _parse_date(text)
            if date:
                flight["date"] = date

        # Distance cell — class "km" or "dist", value like "45.2 km" or "45.23"
        elif "km" in cls or "dist" in cls:
            km = _extract_km(text)
            if km is not None:
                flight["distance_km"] = km

        # Pilot cell — class "pilot" or "user"
        elif "pilot" in cls or "user" in cls:
            # Strip any icon text; take the anchor text if present
            a = cell.find("a")
            flight["pilot"] = a.get_text(strip=True) if a else text

        # Route type
        elif "route" in cls or "type" in cls:
            flight["route"] = text

    # Must have at least a date
    if "date" not in flight:
        return None

    # Ignore very short hops
    if flight.get("distance_km", MIN_XC_KM) < MIN_XC_KM:
        return None

    return flight


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

_DATE_PATTERNS = [
    # ISO:  2026-03-23
    (re.compile(r"(\d{4})-(\d{2})-(\d{2})"), "%Y-%m-%d"),
    # EU dot: 23.03.26 or 23.03.2026
    (re.compile(r"(\d{2})\.(\d{2})\.(\d{2,4})"), None),
    # EU slash: 23/03/2026
    (re.compile(r"(\d{2})/(\d{2})/(\d{2,4})"), None),
]


def _parse_date(text: str) -> str | None:
    text = text.strip()

    # ISO format
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
    if m:
        return m.group(0)

    # DD.MM.YY or DD.MM.YYYY
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{2,4})", text)
    if m:
        d, mo, y = m.group(1), m.group(2), m.group(3)
        if len(y) == 2:
            y = "20" + y
        try:
            dt = datetime(int(y), int(mo), int(d))
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass

    # DD/MM/YYYY
    m = re.search(r"(\d{2})/(\d{2})/(\d{2,4})", text)
    if m:
        d, mo, y = m.group(1), m.group(2), m.group(3)
        if len(y) == 2:
            y = "20" + y
        try:
            dt = datetime(int(y), int(mo), int(d))
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass

    return None


def _extract_km(text: str) -> float | None:
    m = re.search(r"([\d]+(?:[.,]\d+)?)", text)
    if m:
        try:
            return float(m.group(1).replace(",", "."))
        except ValueError:
            pass
    return None


def _empty(error: str) -> dict:
    return {"flights": [], "count": 0, "error": error}


# ---------------------------------------------------------------------------
# Summarise flights into a form useful for the frontend
# ---------------------------------------------------------------------------

def summarise(xc_data: dict) -> dict:
    """
    Build a compact summary for the frontend:
      - total flight count in the window
      - best (longest) flight distance
      - list of dates with activity (for highlighting the forecast)
      - days_since_last_flight
    """
    flights = xc_data.get("flights", [])
    if not flights:
        return {
            "count": 0,
            "best_km": None,
            "active_dates": [],
            "days_since_last": None,
            "error": xc_data.get("error"),
        }

    best_km = max((f.get("distance_km", 0) for f in flights), default=0) or None
    active_dates = sorted({f["date"] for f in flights if "date" in f}, reverse=True)
    days_since_last = None
    if active_dates:
        last = datetime.strptime(active_dates[0], "%Y-%m-%d")
        days_since_last = (datetime.now() - last).days

    return {
        "count": len(flights),
        "best_km": round(best_km, 1) if best_km else None,
        "active_dates": active_dates,
        "days_since_last": days_since_last,
        "recent_flights": flights[:10],  # cap payload size
    }
