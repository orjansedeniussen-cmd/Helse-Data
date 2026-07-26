import garminconnect
import datetime
import json
import os
import traceback

email = os.environ["GARMIN_USERNAME"]
password = os.environ["GARMIN_PASSWORD"]
today = datetime.date.today().isoformat()
path = "docs/garmin_health.json"

# Les eksisterende historikk (samme akkumuleringsmønster som Withings-vekten
# i docs/data.json), slik at hver kjøring legger til dagens dato i stedet
# for å overskrive alt.
try:
    with open(path) as f:
        history = json.load(f)
    if not isinstance(history, dict):
        history = {}
    # Migrer bort fra den gamle flate strukturen (samme fil, første kjøring
    # skrev {"date":..., "sleep":..., "hrv":..., "stats":..., "errors":...}
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

try:
    client = garminconnect.Garmin(email, password)
    client.login()
except Exception as e:
    print("Login feilet:", e)
    traceback.print_exc()
    entry["errors"]["login"] = str(e)
    history[today] = entry
    with open(path, "w") as f:
        json.dump(history, f, default=str)
    raise SystemExit(0)

try:
    entry["sleep"] = client.get_sleep_data(today)
except Exception as e:
    entry["errors"]["sleep"] = str(e)

try:
    entry["hrv"] = client.get_hrv_data(today)
except Exception as e:
    entry["errors"]["hrv"] = str(e)

try:
    entry["stats"] = client.get_stats(today)  # inneholder bl.a. restingHeartRate
except Exception as e:
    entry["errors"]["stats"] = str(e)

history[today] = entry

with open(path, "w") as f:
    json.dump(history, f, default=str)

print(f"Skrev {path} med {len(history)} dager historikk")
