import garminconnect
import datetime
import json
import os
import traceback

today = datetime.date.today().isoformat()
path = "docs/garmin_health.json"
tokenstore = "config/garmintokens"

# Les eksisterende historikk (samme akkumuleringsmønster som Withings-vekten
# i docs/data.json), slik at hver kjøring legger til dagens dato i stedet
# for å overskrive alt.
try:
    with open(path) as f:
        history = json.load(f)
    if not isinstance(history, dict):
        history = {}
    # Migrer bort fra den gamle flate strukturen (første kjøring skrev
    # {"date":..., "sleep":..., "hrv":..., "stats":..., "errors":...}
    # i stedet for datonøkler) hvis den fortsatt ligger igjen.
    if "date" in history and history["date"] not in history:
        old_date = history.pop("date")
        migrated = {}
        for key in ("sleep", "hrv", "stats", "errors"):
            if key in history:
                migrated[key] = history.pop(key)
        if migrated:
            history[old_date] = migrated
except (FileNotFoundError, json.JSONDecodeError):
    history = {}

entry = {"errors": {}}
logged_in = False
method = None

# Metode 1: eget lagret garminconnect-token (fra GARMIN_CONNECT_TOKENS-
# secret, generert lokalt med garmin_token_setup.py). Dette gjør IKKE noe
# nytt innloggingsforsøk mot Garmin — bare en tokenfornyelse — så det er
# trygt selv om kontoen nylig har vært rate-limitet (429).
# (Forsøk på å gjenbruke Withings-delens .garmin_session.json direkte er
# fjernet — den filen viste seg å ikke være i et format garminconnect kan
# lese, så det var en blindvei.)
client = garminconnect.Garmin()
try:
    client.login(tokenstore)
    logged_in = True
    method = "eget lagret token"
except Exception as e:
    print("Kunne ikke bruke lagret token:", e)

# Metode 2: fersk brukernavn/passord-innlogging. SKRUDD AV som standard
# (se ALLOW_FRESH_GARMIN_LOGIN under) fordi Garmin-kontoen ble rate-limitet
# (429) 26.07.2026 etter for mange innloggingsforsøk samme dag — hvert nytt
# forsøk mens sperren står kan forlenge den. Sett repo-variabelen
# ALLOW_FRESH_GARMIN_LOGIN til "true" (Settings → Secrets and variables →
# Actions → Variables) når sperren er bekreftet borte, for å skru dette på.
if not logged_in and os.environ.get("ALLOW_FRESH_GARMIN_LOGIN") == "true":
    try:
        email = os.environ["GARMIN_USERNAME"]
        password = os.environ["GARMIN_PASSWORD"]
        client = garminconnect.Garmin(email, password)
        client.login()
        logged_in = True
        method = "fersk innlogging"
    except Exception as e:
        print("Fersk innlogging feilet også:", e)
        traceback.print_exc()
        entry["errors"]["login"] = str(e)

if not logged_in:
    if "login" not in entry["errors"]:
        entry["errors"]["login"] = "Ingen innloggingsmetode lyktes (mangler gyldig token, og fersk innlogging er skrudd av)."
    history[today] = entry
    with open(path, "w") as f:
        json.dump(history, f, default=str)
    print("Ingen Garmin-pålogging lyktes:", entry["errors"]["login"])
    raise SystemExit(0)

print("Logget inn via:", method)

try:
    entry["stats"] = client.get_stats(today)  # inneholder bl.a. restingHeartRate
except Exception as e:
    entry["errors"]["stats"] = str(e)

try:
    entry["sleep"] = client.get_sleep_data(today)
except Exception as e:
    entry["errors"]["sleep"] = str(e)

try:
    entry["hrv"] = client.get_hrv_data(today)
except Exception as e:
    entry["errors"]["hrv"] = str(e)

history[today] = entry

with open(path, "w") as f:
    json.dump(history, f, default=str)

print(f"Skrev {path} med {len(history)} dager historikk")

# =====================================================================
# Aktiviteter — erstatter den tidligere Strava-integrasjonen.
#
# Alle øktene registreres uansett på Garmin-klokken og synkes videre til
# Strava, så Strava var et unødvendig mellomledd. Denne veien gir i tillegg
# data Strava-APIet ikke ga oss: treningseffekt (aerob/anaerob), treningsbe-
# lastning, VO2max per økt og tid i pulssoner. Bonus: "kcal"-feltet ble
# tidligere hentet som Stravas "kilojoules" (feilmerket — kJ ≠ kcal, ca 4x
# for lavt), mens Garmins "calories"-felt faktisk er kcal.
#
# Bruker samme innloggede client som helsedataene over, så det gjøres ikke
# noe nytt innloggingsforsøk (viktig etter 429-sperren 26.07.2026).
ACTIVITIES_PATH = "docs/activities.json"

GARMIN_TYPE_LABELS = {
    "running": "Løpetur", "trail_running": "Terrengløp", "track_running": "Løpetur (bane)",
    "treadmill_running": "Løpetur (mølle)", "street_running": "Løpetur",
    "cycling": "Sykkeltur", "road_biking": "Sykkeltur", "mountain_biking": "Sykkeltur (terreng)",
    "indoor_cycling": "Sykkeltur (innendørs)", "virtual_ride": "Sykkeltur (innendørs)",
    "strength_training": "Styrketrening", "cardio_training": "Trening", "indoor_cardio": "Trening (innendørs)",
    "walking": "Tur", "hiking": "Fottur",
    "lap_swimming": "Svømming", "open_water_swimming": "Svømming",
    "crossfit": "CrossFit", "hiit": "HIIT", "multi_sport": "Multisport",
}


def week_start(date_str):
    d = datetime.date.fromisoformat(date_str)
    return (d - datetime.timedelta(days=d.weekday())).isoformat()


activities_error = None
raw_activities = []
try:
    raw_activities = client.get_activities(0, 100)
except Exception as e:
    activities_error = str(e)
    print("Henting av aktiviteter feilet:", e)

eight_weeks_ago = datetime.date.today() - datetime.timedelta(weeks=8)

activities = []
for a in raw_activities:
    date_str = (a.get("startTimeLocal") or "")[:10]
    if not date_str:
        continue
    try:
        if datetime.date.fromisoformat(date_str) < eight_weeks_ago:
            continue
    except ValueError:
        continue

    type_key = (a.get("activityType") or {}).get("typeKey")

    zones = {}
    for z in range(1, 6):
        secs = a.get(f"hrTimeInZone_{z}")
        if secs:
            zones[str(z)] = round(secs / 60, 1)

    activities.append({
        "id": a.get("activityId"),
        "type": type_key,
        "type_label": GARMIN_TYPE_LABELS.get(type_key, type_key or a.get("activityName")),
        "name": a.get("activityName"),
        "date": date_str,
        "distance_km": round(a["distance"] / 1000, 2) if a.get("distance") else None,
        "duration_min": round(a["duration"] / 60, 1) if a.get("duration") else None,
        "avg_hr": a.get("averageHR"),
        "max_hr": a.get("maxHR"),
        "kcal": a.get("calories"),
        "elevation_gain_m": round(a["elevationGain"]) if a.get("elevationGain") else None,
        "cadence_spm": round(a["averageRunningCadenceInStepsPerMinute"]) if a.get("averageRunningCadenceInStepsPerMinute") else None,
        "aerobic_effect": a.get("aerobicTrainingEffect"),
        "anaerobic_effect": a.get("anaerobicTrainingEffect"),
        "training_effect_label": a.get("trainingEffectLabel"),
        "training_load": a.get("activityTrainingLoad"),
        "vo2max": a.get("vO2MaxValue"),
        "hr_zone_minutes": zones or None,
    })

activities.sort(key=lambda x: x["date"], reverse=True)

# Treningstimer per uke, siste 8 uker (til bar-chart i Fremgang-fanen) —
# regnes ut fra HELE 8-ukersvinduet, ikke bare de 20 siste øktene under.
weekly = {}
for a in activities:
    if not a["duration_min"]:
        continue
    wk = week_start(a["date"])
    weekly[wk] = weekly.get(wk, 0) + a["duration_min"] / 60

today_date = datetime.date.today()
weeks = []
for i in range(7, -1, -1):
    wk_date = today_date - datetime.timedelta(weeks=i)
    wk_key = week_start(wk_date.isoformat())
    weeks.append({"week_start": wk_key, "hours": round(weekly.get(wk_key, 0), 1)})

# VO2max-trend — bare et fåtall økter (typisk løp/sykkel) rapporterer dette,
# så vi bygger trenden fra hele 8-ukersvinduet i kronologisk rekkefølge,
# ikke bare de 20 siste øktene.
vo2max_trend = [
    {"date": a["date"], "value": a["vo2max"]}
    for a in sorted(activities, key=lambda x: x["date"])
    if a.get("vo2max")
]

# Pulssoner — summert over hele 8-ukersvinduet, i minutter per sone.
hr_zones = {str(z): 0.0 for z in range(1, 6)}
for a in activities:
    if not a.get("hr_zone_minutes"):
        continue
    for z, mins in a["hr_zone_minutes"].items():
        hr_zones[z] = round(hr_zones.get(z, 0) + mins, 1)

out = {
    "updated": datetime.datetime.utcnow().isoformat() + "Z",
    "activities": activities[:20],
    "weekly_hours": weeks,
    "vo2max_trend": vo2max_trend[-15:],
    "hr_zone_minutes": hr_zones,
}
if activities_error:
    out["error"] = activities_error

os.makedirs("docs", exist_ok=True)
with open(ACTIVITIES_PATH, "w") as f:
    json.dump(out, f)

print(f"Skrev {ACTIVITIES_PATH} med {len(activities)} aktiviteter siste 8 uker")
