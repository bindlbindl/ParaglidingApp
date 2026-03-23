"""
Paragliding Conditions App - Flask backend.
"""

from flask import Flask, render_template, jsonify
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import threading
import time

from sites import SITES
from weather import fetch_weather
from conditions import evaluate_site
import xcontest

app = Flask(__name__)

# Simple in-memory cache: {site_name: (timestamp, data)}
_cache = {}
_cache_lock = threading.Lock()
CACHE_TTL = 1800  # 30 minutes


def _get_cached(site_name):
    with _cache_lock:
        entry = _cache.get(site_name)
        if entry:
            ts, data = entry
            if time.time() - ts < CACHE_TTL:
                return data
    return None


def _set_cached(site_name, data):
    with _cache_lock:
        _cache[site_name] = (time.time(), data)


def _fetch_site(site):
    cached = _get_cached(site["name"])
    if cached:
        return cached
    weather = fetch_weather(site["lat"], site["lon"])
    result = evaluate_site(site, weather)
    _set_cached(site["name"], result)
    return result


# XContest cache is managed inside xcontest.py (6-hour TTL)
def _fetch_site_with_xc(site):
    result = _fetch_site(site)
    xc_raw = xcontest.fetch_xc_flights(site)
    result["xc"] = xcontest.summarise(xc_raw)
    return result


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/conditions")
def all_conditions():
    """Fetch all sites in parallel and return JSON."""
    results = []
    with ThreadPoolExecutor(max_workers=6) as executor:
        future_to_site = {executor.submit(_fetch_site_with_xc, s): s for s in SITES}
        for future in as_completed(future_to_site):
            try:
                data = future.result(timeout=30)
                results.append(data)
            except Exception as e:
                site = future_to_site[future]
                results.append({"site": site, "error": str(e)})

    # Sort by current score descending
    results.sort(key=lambda r: r.get("current", {}).get("score", 0), reverse=True)
    return jsonify({"results": results, "fetched_at": datetime.now().isoformat()})


@app.route("/api/conditions/<site_name>")
def site_conditions(site_name):
    """Fetch a single site by name."""
    site = next((s for s in SITES if s["name"] == site_name), None)
    if not site:
        return jsonify({"error": "Site not found"}), 404
    # Bypass cache for single site refresh
    with _cache_lock:
        _cache.pop(site["name"], None)
    weather = fetch_weather(site["lat"], site["lon"])
    result = evaluate_site(site, weather)
    _set_cached(site["name"], result)
    return jsonify(result)


@app.route("/api/xcontest/<path:site_name>")
def site_xcontest(site_name):
    """Return raw XContest flight list for a single site (cache bypassed)."""
    site = next((s for s in SITES if s["name"] == site_name), None)
    if not site:
        return jsonify({"error": "Site not found"}), 404
    # Invalidate xcontest cache for this site so we get fresh data
    with xcontest._cache_lock:
        xcontest._cache.pop(site["name"], None)
    raw = xcontest.fetch_xc_flights(site)
    return jsonify({**raw, "summary": xcontest.summarise(raw)})


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
