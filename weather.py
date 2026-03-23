"""
Weather data fetching from Open-Meteo API (free, no API key required).
"""

import requests
from datetime import datetime, timezone

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# Wind direction degrees to compass cardinal
def degrees_to_cardinal(degrees):
    if degrees is None:
        return "N/A"
    dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    ix = round(degrees / (360 / len(dirs))) % len(dirs)
    return dirs[ix]


def ms_to_mph(ms):
    """Convert m/s to mph."""
    return ms * 2.23694


def fetch_weather(lat, lon):
    """
    Fetch current conditions + 7-day hourly forecast from Open-Meteo.
    Returns a dict with 'current' and 'daily' keys, or None on error.
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": [
            "temperature_2m",
            "relative_humidity_2m",
            "apparent_temperature",
            "precipitation",
            "weather_code",
            "cloud_cover",
            "wind_speed_10m",
            "wind_direction_10m",
            "wind_gusts_10m",
        ],
        "daily": [
            "weather_code",
            "temperature_2m_max",
            "temperature_2m_min",
            "precipitation_sum",
            "wind_speed_10m_max",
            "wind_gusts_10m_max",
            "wind_direction_10m_dominant",
        ],
        "hourly": [
            "temperature_2m",
            "precipitation_probability",
            "wind_speed_10m",
            "wind_direction_10m",
            "wind_gusts_10m",
            "cloud_cover",
            "cape",  # Convective Available Potential Energy (thermal indicator)
        ],
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timezone": "America/Los_Angeles",
        "forecast_days": 7,
    }

    try:
        resp = requests.get(OPEN_METEO_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return {"error": str(e)}

    current = data.get("current", {})
    daily = data.get("daily", {})
    hourly = data.get("hourly", {})

    # Parse current conditions
    current_parsed = {
        "temperature_f": current.get("temperature_2m"),
        "humidity": current.get("relative_humidity_2m"),
        "feels_like_f": current.get("apparent_temperature"),
        "precipitation_in": current.get("precipitation", 0),
        "weather_code": current.get("weather_code"),
        "cloud_cover": current.get("cloud_cover"),
        "wind_speed_mph": current.get("wind_speed_10m"),
        "wind_dir_deg": current.get("wind_direction_10m"),
        "wind_dir": degrees_to_cardinal(current.get("wind_direction_10m")),
        "wind_gusts_mph": current.get("wind_gusts_10m"),
        "time": current.get("time"),
    }

    # Parse daily forecast
    daily_parsed = []
    dates = daily.get("time", [])
    for i, date in enumerate(dates):
        daily_parsed.append({
            "date": date,
            "weather_code": _safe_get(daily, "weather_code", i),
            "temp_max_f": _safe_get(daily, "temperature_2m_max", i),
            "temp_min_f": _safe_get(daily, "temperature_2m_min", i),
            "precip_in": _safe_get(daily, "precipitation_sum", i, 0),
            "wind_max_mph": _safe_get(daily, "wind_speed_10m_max", i),
            "wind_gusts_mph": _safe_get(daily, "wind_gusts_10m_max", i),
            "wind_dir_deg": _safe_get(daily, "wind_direction_10m_dominant", i),
            "wind_dir": degrees_to_cardinal(_safe_get(daily, "wind_direction_10m_dominant", i)),
        })

    # Extract best flying window per day from hourly data (10am-5pm)
    hourly_times = hourly.get("time", [])
    daily_hourly = {}  # date -> list of hourly dicts during daytime

    for i, t in enumerate(hourly_times):
        date_part = t[:10]
        hour = int(t[11:13])
        if 9 <= hour <= 17:
            entry = {
                "hour": hour,
                "temp_f": _safe_get(hourly, "temperature_2m", i),
                "precip_prob": _safe_get(hourly, "precipitation_probability", i, 0),
                "wind_mph": _safe_get(hourly, "wind_speed_10m", i),
                "wind_dir_deg": _safe_get(hourly, "wind_direction_10m", i),
                "wind_dir": degrees_to_cardinal(_safe_get(hourly, "wind_direction_10m", i)),
                "wind_gusts_mph": _safe_get(hourly, "wind_gusts_10m", i),
                "cloud_cover": _safe_get(hourly, "cloud_cover", i),
                "cape": _safe_get(hourly, "cape", i, 0),
            }
            daily_hourly.setdefault(date_part, []).append(entry)

    return {
        "current": current_parsed,
        "daily": daily_parsed,
        "daily_hourly": daily_hourly,
    }


def _safe_get(d, key, index, default=None):
    lst = d.get(key, [])
    if lst and index < len(lst):
        return lst[index]
    return default


# WMO Weather Code descriptions
WMO_CODES = {
    0: ("Clear sky", "☀️"),
    1: ("Mainly clear", "🌤️"),
    2: ("Partly cloudy", "⛅"),
    3: ("Overcast", "☁️"),
    45: ("Foggy", "🌫️"),
    48: ("Icy fog", "🌫️"),
    51: ("Light drizzle", "🌦️"),
    53: ("Drizzle", "🌦️"),
    55: ("Heavy drizzle", "🌧️"),
    61: ("Slight rain", "🌧️"),
    63: ("Moderate rain", "🌧️"),
    65: ("Heavy rain", "🌧️"),
    71: ("Slight snow", "🌨️"),
    73: ("Moderate snow", "❄️"),
    75: ("Heavy snow", "❄️"),
    77: ("Snow grains", "❄️"),
    80: ("Light showers", "🌦️"),
    81: ("Showers", "🌧️"),
    82: ("Heavy showers", "⛈️"),
    85: ("Snow showers", "🌨️"),
    86: ("Heavy snow showers", "❄️"),
    95: ("Thunderstorm", "⛈️"),
    96: ("Thunderstorm w/ hail", "⛈️"),
    99: ("Thunderstorm w/ heavy hail", "⛈️"),
}


def weather_description(code):
    if code is None:
        return ("Unknown", "❓")
    return WMO_CODES.get(int(code), ("Unknown", "❓"))
