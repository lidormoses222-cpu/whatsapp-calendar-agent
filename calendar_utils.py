import os
import base64
from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import pickle

SCOPES = ["https://www.googleapis.com/auth/calendar"]
TOKEN_FILE = "token.pickle"
CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")


def get_calendar_service():
    creds = None

    # Load token from env var (Railway) or local file
    token_b64 = os.getenv("GOOGLE_TOKEN_B64")
    if token_b64:
        creds = pickle.loads(base64.b64decode(token_b64))
    elif os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "rb") as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        if not token_b64:
            with open(TOKEN_FILE, "wb") as f:
                pickle.dump(creds, f)

    return build("calendar", "v3", credentials=creds)


def create_event(service, data):
    date = data["date"]
    start_dt = f"{date}T{data['start_time']}:00"
    end_dt = f"{date}T{data['end_time']}:00"
    event = {
        "summary": data["title"],
        "description": data.get("description", ""),
        "start": {"dateTime": start_dt, "timeZone": "Asia/Jerusalem"},
        "end": {"dateTime": end_dt, "timeZone": "Asia/Jerusalem"},
    }
    return service.events().insert(calendarId="primary", body=event).execute()


def check_conflicts(service, data):
    date = data["date"]
    start_dt = f"{date}T{data['start_time']}:00+03:00"
    end_dt = f"{date}T{data['end_time']}:00+03:00"
    events_result = service.events().list(
        calendarId="primary",
        timeMin=start_dt,
        timeMax=end_dt,
        singleEvents=True,
        orderBy="startTime"
    ).execute()
    events = events_result.get("items", [])
    return [e.get("summary", "אירוע ללא שם") for e in events]


def get_tomorrow_events(service):
    tomorrow = datetime.now() + timedelta(days=1)
    start = tomorrow.replace(hour=0, minute=0, second=0).isoformat() + "+03:00"
    end = tomorrow.replace(hour=23, minute=59, second=59).isoformat() + "+03:00"
    result = service.events().list(
        calendarId="primary",
        timeMin=start,
        timeMax=end,
        singleEvents=True,
        orderBy="startTime"
    ).execute()
    return result.get("items", [])
