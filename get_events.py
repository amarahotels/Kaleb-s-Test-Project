# get_events.py
import os, json, requests
from datetime import datetime, timedelta, timezone
from pathlib import Path

TOKEN = os.getenv("EVENTBRITE_TOKEN")
if not TOKEN:
    raise RuntimeError("EVENTBRITE_TOKEN not set (expected in GitHub Actions secret).")

# NOTE: use endpoint without trailing slash to avoid 404/redirects
API_URL = "https://www.eventbriteapi.com/v3/events/search"

def iso_no_frac(dt: datetime) -> str:
    """Return UTC ISO8601 without fractional seconds, e.g., 2025-07-31T12:34:56Z."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

def fetch_range(start_dt: datetime, end_dt: datetime, max_pages=5):
    headers = {"Authorization": f"Bearer {TOKEN}"}
    base = {
        "location.address": "Singapore",
        "location.within": "30km",      # add an explicit search radius
        "sort_by": "date",
        "expand": "venue,category",
        "start_date.range_start": iso_no_frac(start_dt),
        "start_date.range_end": iso_no_frac(end_dt),
        "include_all_series_instances": "true",
    }

    events, page = [], 1
    while page <= max_pages:
        params = {**base, "page": page}
        r = requests.get(API_URL, headers=headers, params=params, timeout=30)

        if r.status_code != 200:
            # Log the full URL + body to understand what the API is complaining about
            print("Eventbrite request failed:",
                  r.status_code, r.reason)
            print("URL:", r.url)
            try:
                print("Body:", r.json())
            except Exception:
                print("Body (text):", r.text)
            # Stop trying; return what we have so far
            break

        data = r.json()
        for e in data.get("events", []):
            venue = e.get("venue") or {}
            addr = (venue.get("address") or {}).get("localized_address_display")
            logo = (e.get("logo") or {}).get("url")
            events.append({
                "id": e.get("id"),
                "name": (e.get("name") or {}).get("text"),
                "start": (e.get("start") or {}).get("local") or (e.get("start") or {}).get("utc"),
                "end": (e.get("end") or {}).get("local") or (e.get("end") or {}).get("utc"),
                "url": e.get("url"),
                "is_free": e.get("is_free"),
                "category": (e.get("category") or {}).get("short_name") or (e.get("category") or {}).get("name"),
                "venue": venue.get("name"),
                "address": addr,
                "image": logo,
                "source": "eventbrite",
            })

        pag = data.get("pagination") or {}
        if not pag.get("has_more_items"):
            break
        page += 1

    return events

def main():
    now = datetime.now(timezone.utc)
    week = fetch_range(now, now + timedelta(days=7))
    month = fetch_range(now, now + timedelta(days=30))

    seen, wk, mo = set(), [], []
    for e in week:
        if e["id"] not in seen:
            wk.append(e); seen.add(e["id"])
    for e in month:
        if e["id"] not in seen:
            mo.append(e); seen.add(e["id"])

    out = {
        "generated_at": iso_no_frac(datetime.utcnow()),
        "this_week": wk,
        "next_30_days": mo,
    }

    Path("public/data").mkdir(parents=True, exist_ok=True)
    with open("public/data/events.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"events.json → week:{len(wk)} month:{len(mo)}")

if __name__ == "__main__":
    main()
