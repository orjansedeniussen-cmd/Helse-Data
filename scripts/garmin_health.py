import garminconnect
import datetime
import json
import os
import traceback

email = os.environ["GARMIN_USERNAME"]
password = os.environ["GARMIN_PASSWORD"]
today = datetime.date.today().isoformat()
result = {"date": today, "errors": {}}

try:
    client = garminconnect.Garmin(email, password)
    client.login()
except Exception as e:
    print("Login feilet:", e)
    traceback.print_exc()
    with open("docs/garmin_health.json", "w") as f:
        json.dump({"date": today, "errors": {"login": str(e)}}, f)
    raise SystemExit(0)

try:
    result["sleep"] = client.get_sleep_data(today)
except Exception as e:
    result["errors"]["sleep"] = str(e)

try:
    result["hrv"] = client.get_hrv_data(today)
except Exception as e:
    result["errors"]["hrv"] = str(e)

try:
    result["stats"] = client.get_stats(today)  # inneholder bl.a. restingHeartRate
except Exception as e:
    result["errors"]["stats"] = str(e)

with open("docs/garmin_health.json", "w") as f:
    json.dump(result, f, default=str)

print("Skrev docs/garmin_health.json")
