"""
Paragliding conditions scoring logic.

Scores are 0-100. Ratings:
  80-100: GREAT   (green)
  60-79:  GOOD    (light green)
  40-59:  MARGINAL (yellow)
  20-39:  POOR    (orange)
  0-19:   AVOID   (red)
"""

from weather import degrees_to_cardinal, weather_description

# Dangerous WMO weather codes (precipitation, storms, fog)
DANGEROUS_CODES = {45, 48, 51, 53, 55, 61, 63, 65, 71, 73, 75, 77, 80, 81, 82, 85, 86, 95, 96, 99}
POOR_CODES = {3}  # overcast can limit thermals

CARDINAL_TO_DEG = {
    "N": 0, "NNE": 22.5, "NE": 45, "ENE": 67.5,
    "E": 90, "ESE": 112.5, "SE": 135, "SSE": 157.5,
    "S": 180, "SSW": 202.5, "SW": 225, "WSW": 247.5,
    "W": 270, "WNW": 292.5, "NW": 315, "NNW": 337.5,
}


def _angle_diff(a, b):
    """Smallest angle between two bearings (0-180)."""
    diff = abs(a - b) % 360
    return diff if diff <= 180 else 360 - diff


def _wind_dir_score(wind_dir_deg, preferred_dirs):
    """Score 0-100 based on how close wind direction is to preferred."""
    if wind_dir_deg is None or not preferred_dirs:
        return 50  # neutral
    min_diff = min(
        _angle_diff(wind_dir_deg, CARDINAL_TO_DEG.get(d, 0))
        for d in preferred_dirs
    )
    # 0° diff -> 100, 45° -> 75, 90° -> 25, 135+ -> 0
    if min_diff <= 30:
        return 100
    elif min_diff <= 60:
        return int(100 - (min_diff - 30) * 1.5)
    elif min_diff <= 90:
        return int(55 - (min_diff - 60) * 1.5)
    else:
        return max(0, int(10 - (min_diff - 90) * 0.2))


def score_conditions(wind_mph, wind_gusts_mph, wind_dir_deg, weather_code,
                     precip_in, cloud_cover, temp_f, cape, site):
    """
    Returns (score 0-100, list of factors).
    """
    factors = []
    score = 100

    pref_min = site["preferred_wind_min_mph"]
    pref_max = site["preferred_wind_max_mph"]
    site_type = site["site_type"]

    # --- Hard disqualifiers ---
    if weather_code is not None and int(weather_code) in DANGEROUS_CODES:
        desc, _ = weather_description(weather_code)
        return 5, [f"Dangerous weather: {desc}"]

    if precip_in and precip_in > 0.01:
        return 5, [f"Active precipitation ({precip_in:.2f}in)"]

    # --- Wind speed ---
    if wind_mph is None:
        factors.append("Wind data unavailable")
    elif wind_mph < 3:
        score -= 30
        factors.append(f"Wind too light ({wind_mph:.0f} mph) — hard to stay up")
    elif wind_mph < pref_min:
        penalty = int((pref_min - wind_mph) / pref_min * 40)
        score -= penalty
        factors.append(f"Wind below ideal ({wind_mph:.0f} mph, prefer {pref_min}-{pref_max} mph)")
    elif wind_mph <= pref_max:
        factors.append(f"Wind speed ideal ({wind_mph:.0f} mph)")
    elif wind_mph <= pref_max + 8:
        penalty = int((wind_mph - pref_max) / 8 * 30)
        score -= penalty
        factors.append(f"Wind slightly strong ({wind_mph:.0f} mph, prefer ≤{pref_max} mph)")
    else:
        score -= 50
        factors.append(f"Wind too strong ({wind_mph:.0f} mph — dangerous)")

    # --- Gusts ---
    if wind_gusts_mph and wind_mph:
        gust_ratio = wind_gusts_mph / max(wind_mph, 1)
        if wind_gusts_mph > 30:
            score -= 25
            factors.append(f"Strong gusts ({wind_gusts_mph:.0f} mph)")
        elif gust_ratio > 1.6:
            score -= 15
            factors.append(f"Gusty conditions ({wind_gusts_mph:.0f} mph gusts)")
        else:
            factors.append(f"Gusts manageable ({wind_gusts_mph:.0f} mph)")

    # --- Wind direction ---
    dir_score = _wind_dir_score(wind_dir_deg, site["preferred_wind_dirs"])
    dir_penalty = int((100 - dir_score) * 0.35)
    score -= dir_penalty
    wind_dir_name = degrees_to_cardinal(wind_dir_deg) if wind_dir_deg is not None else "N/A"
    if dir_score >= 80:
        factors.append(f"Wind direction favorable ({wind_dir_name})")
    elif dir_score >= 50:
        factors.append(f"Wind direction marginal ({wind_dir_name}, prefer {'/'.join(site['preferred_wind_dirs'])})")
    else:
        factors.append(f"Wind direction unfavorable ({wind_dir_name}, prefer {'/'.join(site['preferred_wind_dirs'])})")

    # --- Weather code ---
    if weather_code is not None:
        if int(weather_code) in POOR_CODES:
            score -= 10
            factors.append("Overcast sky limits thermals")
        elif int(weather_code) <= 2:
            factors.append("Clear/sunny sky — good for thermals")

    # --- Thermals (thermal sites) ---
    if site_type in ("thermal", "mountain"):
        if temp_f and temp_f >= 70:
            factors.append(f"Warm temp ({temp_f:.0f}°F) — thermal potential good")
        elif temp_f and temp_f >= 55:
            score -= 5
            factors.append(f"Moderate temp ({temp_f:.0f}°F) — mild thermals")
        elif temp_f:
            score -= 15
            factors.append(f"Cool temp ({temp_f:.0f}°F) — weak thermals")

        if cape is not None:
            if cape > 500:
                score -= 20
                factors.append(f"High CAPE ({cape:.0f} J/kg) — convective instability risk")
            elif cape > 100:
                factors.append(f"Moderate CAPE ({cape:.0f} J/kg) — good thermal lift")
            else:
                factors.append(f"Low CAPE ({cape:.0f} J/kg) — weak thermals")

    # --- Cloud cover ---
    if cloud_cover is not None:
        if cloud_cover > 85:
            score -= 10
            factors.append(f"Heavy cloud cover ({cloud_cover}%) — limits solar heating")
        elif cloud_cover > 50:
            score -= 5
            factors.append(f"Partial clouds ({cloud_cover}%)")
        else:
            factors.append(f"Good visibility ({cloud_cover}% cloud cover)")

    score = max(0, min(100, score))
    return score, factors


def get_rating(score):
    if score >= 80:
        return "GREAT", "great", "#27ae60"
    elif score >= 60:
        return "GOOD", "good", "#2ecc71"
    elif score >= 40:
        return "MARGINAL", "marginal", "#f39c12"
    elif score >= 20:
        return "POOR", "poor", "#e67e22"
    else:
        return "AVOID", "avoid", "#e74c3c"


def evaluate_site(site, weather_data):
    """
    Given a site dict and weather data, return full evaluation.
    """
    if "error" in weather_data:
        return {"error": weather_data["error"]}

    current = weather_data["current"]
    daily = weather_data.get("daily", [])
    daily_hourly = weather_data.get("daily_hourly", {})

    # Current score
    cur_score, cur_factors = score_conditions(
        wind_mph=current.get("wind_speed_mph"),
        wind_gusts_mph=current.get("wind_gusts_mph"),
        wind_dir_deg=current.get("wind_dir_deg"),
        weather_code=current.get("weather_code"),
        precip_in=current.get("precipitation_in", 0),
        cloud_cover=current.get("cloud_cover"),
        temp_f=current.get("temperature_f"),
        cape=None,
        site=site,
    )
    cur_label, cur_class, cur_color = get_rating(cur_score)

    # Daily forecast scores (use midday window avg)
    daily_evaluated = []
    for day in daily:
        date = day["date"]
        hourly_window = daily_hourly.get(date, [])

        if hourly_window:
            # Average key metrics over 10am-5pm window (best flying hours)
            window = [h for h in hourly_window if 10 <= h["hour"] <= 17]
            if not window:
                window = hourly_window
            avg_wind = _avg([h["wind_mph"] for h in window])
            avg_gusts = _avg([h["wind_gusts_mph"] for h in window])
            avg_dir = _avg([h["wind_dir_deg"] for h in window])
            avg_cloud = _avg([h["cloud_cover"] for h in window])
            avg_temp = _avg([h["temp_f"] for h in window])
            avg_cape = _avg([h["cape"] for h in window])
            avg_precip_prob = _avg([h["precip_prob"] for h in window])
        else:
            avg_wind = day.get("wind_max_mph")
            avg_gusts = day.get("wind_gusts_mph")
            avg_dir = day.get("wind_dir_deg")
            avg_cloud = None
            avg_temp = day.get("temp_max_f")
            avg_cape = None
            avg_precip_prob = 0

        # Reduce score if high precip probability
        d_score, d_factors = score_conditions(
            wind_mph=avg_wind,
            wind_gusts_mph=avg_gusts,
            wind_dir_deg=avg_dir,
            weather_code=day.get("weather_code"),
            precip_in=day.get("precip_in", 0),
            cloud_cover=avg_cloud,
            temp_f=avg_temp,
            cape=avg_cape,
            site=site,
        )

        if avg_precip_prob and avg_precip_prob > 40:
            d_score = max(0, d_score - int((avg_precip_prob - 40) * 0.5))
            d_factors.append(f"Rain probability: {avg_precip_prob:.0f}%")

        d_score = max(0, min(100, d_score))
        d_label, d_class, d_color = get_rating(d_score)

        desc, icon = weather_description(day.get("weather_code"))
        daily_evaluated.append({
            "date": date,
            "score": d_score,
            "label": d_label,
            "class": d_class,
            "color": d_color,
            "factors": d_factors,
            "weather_desc": desc,
            "weather_icon": icon,
            "temp_max": day.get("temp_max_f"),
            "temp_min": day.get("temp_min_f"),
            "wind_max": avg_wind,
            "wind_dir": degrees_to_cardinal(avg_dir) if avg_dir else "N/A",
            "precip_prob": avg_precip_prob,
        })

    cur_desc, cur_icon = weather_description(current.get("weather_code"))

    return {
        "site": site,
        "current": {
            **current,
            "score": cur_score,
            "label": cur_label,
            "class": cur_class,
            "color": cur_color,
            "factors": cur_factors,
            "weather_desc": cur_desc,
            "weather_icon": cur_icon,
        },
        "daily": daily_evaluated,
    }


def _avg(lst):
    vals = [v for v in lst if v is not None]
    return sum(vals) / len(vals) if vals else None
