import json
import os
import urllib.request
import urllib.parse
import datetime

CLIENT_ID = os.environ["STRAVA_CLIENT_ID"]
CLIENT_SECRET = os.environ["STRAVA_CLIENT_SECRET"]
REFRESH_TOKEN = os.environ["STRAVA_REFRESH_TOKEN"]


def post(url, data):
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def get(url, token):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def week_start(date_str):
    d = datetime.date.fromisoformat(date_str)
    return (d - datetime.timedelta(days=d.weekday())).isoformat()


# 1. Bytt refresh token mot en fersk access token (refresh_token er langtids-gyldig,
#    access_token varer kun 6 timer, så den byttes hver gang scriptet kjører)
token_data = post("https://www.strava.com/oauth/token", {
    "client_id": CLIENT_ID,
    "client_secret": CLIENT_SECRET,
    "grant_type": "refresh_token",
    "refresh_token": REFRESH_TOKEN,
})
access_token = token_data["access_token"]

# 2. Hent aktiviteter siste 8 uker (nok til trendgrafen i appen)
eight_weeks_ago = int((datetime.datetime.utcnow() - datetime.timedelta(weeks=8)).timestamp())
url = f"https://www.strava.com/api/v3/athlete/activities?after={eight_weeks_ago}&per_page=100"
raw_activities = get(url, access_token)

activities = []
for a in raw_activities:
    activities.append({
        "id": a.get("id"),
        "type": a.get("type"),
        "name": a.get("name"),
        "date": (a.get("start_date_local") or "")[:10],
        "distance_km": round((a.get("distance") or 0) / 1000, 2),
        "duration_min": round((a.get("moving_time") or 0) / 60, 1),
        "avg_hr": a.get("average_heartrate"),
        "kcal": a.get("kilojoules"),
    })

activities.sort(key=lambda x: x["date"], reverse=True)

# 3. Treningstimer per uke, siste 8 uker (til bar-chart i Fremgang-fanen)
weekly = {}
for a in activities:
    if not a["date"]:
        continue
    wk = week_start(a["date"])
    weekly[wk] = weekly.get(wk, 0) + a["duration_min"] / 60

today = datetime.date.today()
weeks = []
for i in range(7, -1, -1):
    wk_date = today - datetime.timedelta(weeks=i)
    wk_key = week_start(wk_date.isoformat())
    weeks.append({"week_start": wk_key, "hours": round(weekly.get(wk_key, 0), 1)})

out = {
    "updated": datetime.datetime.utcnow().isoformat() + "Z",
    "activities": activities[:20],
    "weekly_hours": weeks,
}

os.makedirs("docs", exist_ok=True)
with open("docs/strava.json", "w") as f:
    json.dump(out, f)

print(f"Skrev docs/strava.json med {len(activities)} aktiviteter siste 8 uker")
