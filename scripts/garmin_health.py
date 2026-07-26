import garminconnect
import garth
import datetime
import json
import os
import traceback

today = datetime.date.today().isoformat()
path = "docs/garmin_health.json"
tokenstore = "config/garmintokens"
withings_session_file = "config/.garmin_session.json"  # samme fil Withings-delen allerede bruker

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
client = garminconnect.Garmin()
logged_in = False
method = None

# Metode 1 (foretrukket): gjenbruk Garmin-sesjonen som Withings-delen av
# workflowen allerede bruker vellykket hver dag (.garmin_session.json).
# Dette gjør INGEN nytt innloggingsforsøk mot Garmin sin login-endepunkt —
# bare en vanlig, autentisert API-forespørsel med en allerede godkjent
# sesjon. Kan derfor ikke forverre en ev. rate-limit (429) på kontoen.
try:
    with open(withings_session_file) as f:
        garth.client.loads(f.read())
    client.garth = garth.client
    entry["stats"] = client.get_stats(today)  # bekrefter samtidig at sesjonen virker
    logged_in = True
    method = "gjenbrukt Withings-sesjon"
except Exception as e:
    print("Kunne ikke gjenbruke Withings-sesjonen:", e)

# Metode 2: eget lagret garminconnect-token (fra GARMIN_CONNECT_TOKENS-
# secret, generert lokalt med garmin_token_setup.py).
if not logged_in:
    try:
        client = garminconnect.Garmin()
        client.login(tokenstore)
        logged_in = True
        method = "eget lagret token"
    except Exception as e:
        print("Kunne ikke bruke lagret token:", e)

# Metode 3: fersk brukernavn/passord-innlogging. SKRUDD AV som standard
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
        entry["errors"]["login"] = "Ingen innloggingsmetode lyktes (fersk innlogging er skrudd av, se kommentarer)."
    history[today] = entry
    with open(path, "w") as f:
        json.dump(history, f, default=str)
    print("Ingen Garmin-pålogging lyktes:", entry["errors"]["login"])
    raise SystemExit(0)

print("Logget inn via:", method)

if "stats" not in entry:
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
