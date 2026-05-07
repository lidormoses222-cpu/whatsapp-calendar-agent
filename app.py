import os
import json
from datetime import datetime, timedelta
from flask import Flask, request
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
import anthropic
from calendar_utils import get_calendar_service, create_event, check_conflicts, get_tomorrow_events

load_dotenv()

app = Flask(__name__)

twilio_client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
claude_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

TWILIO_FROM = os.getenv("TWILIO_WHATSAPP_FROM")
USER_PHONE = os.getenv("YOUR_WHATSAPP")

pending_conflicts = {}


def send_whatsapp(to, body):
    twilio_client.messages.create(from_=TWILIO_FROM, to=to, body=body)


def parse_event_with_claude(text):
    today = datetime.now().strftime("%Y-%m-%d")
    response = claude_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        messages=[{
            "role": "user",
            "content": f"""היום: {today}
חלץ פרטי אירוע מהטקסט הבא והחזר JSON בלבד (ללא הסבר):
{{
  "title": "שם האירוע",
  "date": "YYYY-MM-DD",
  "start_time": "HH:MM",
  "end_time": "HH:MM",
  "description": "תיאור אופציונלי"
}}

טקסט: {text}"""
        }]
    )
    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1].replace("json", "").strip()
    return json.loads(raw)


@app.route("/webhook", methods=["POST"])
def webhook():
    incoming = request.form.get("Body", "").strip()
    sender = request.form.get("From", "")
    resp = MessagingResponse()

    if sender in pending_conflicts:
        choice = incoming.strip()
        data = pending_conflicts.pop(sender)
        if choice == "1":
            service = get_calendar_service()
            event = create_event(service, data)
            resp.message(f"✅ האירוע נוצר:\n{data['title']}\n{data['date']} {data['start_time']}-{data['end_time']}")
        else:
            resp.message("❌ האירוע בוטל.")
        return str(resp)

    try:
        event_data = parse_event_with_claude(incoming)
        service = get_calendar_service()
        conflicts = check_conflicts(service, event_data)

        if conflicts:
            conflict_titles = "\n".join([f"• {c}" for c in conflicts])
            pending_conflicts[sender] = event_data
            resp.message(
                f"⚠️ יש התנגשות עם:\n{conflict_titles}\n\n"
                f"האירוע החדש: {event_data['title']} ב-{event_data['start_time']}\n\n"
                f"שלח 1 ליצור בכל זאת, 2 לביטול"
            )
        else:
            event = create_event(service, event_data)
            resp.message(f"✅ האירוע נוצר:\n{event_data['title']}\n{event_data['date']} {event_data['start_time']}-{event_data['end_time']}")

    except Exception as e:
        resp.message(f"❌ לא הצלחתי להבין. נסה שוב עם תאריך ושעה ברורים.\nלדוגמה: 'פגישה עם דני מחר ב-14:00 לשעה'")

    return str(resp)


def send_daily_summary():
    try:
        service = get_calendar_service()
        events = get_tomorrow_events(service)
        if not events:
            msg = "📅 אין אירועים מחר. יום פנוי!"
        else:
            lines = [f"📅 *סיכום מחר {(datetime.now() + timedelta(days=1)).strftime('%d/%m')}:*"]
            for e in events:
                start = e["start"].get("dateTime", e["start"].get("date", ""))
                if "T" in start:
                    time_str = datetime.fromisoformat(start).strftime("%H:%M")
                else:
                    time_str = "כל היום"
                lines.append(f"• {time_str} — {e['summary']}")
            msg = "\n".join(lines)
        send_whatsapp(USER_PHONE, msg)
    except Exception as e:
        print(f"שגיאה בסיכום יומי: {e}")


def send_checkin(message):
    send_whatsapp(USER_PHONE, message)


scheduler = BackgroundScheduler()
scheduler.add_job(send_daily_summary, "cron", hour=21, minute=0)
scheduler.add_job(send_checkin, "cron", hour=9, minute=0, args=["☀️ בוקר טוב! מה המשימות שלך להיום?"])
scheduler.add_job(send_checkin, "cron", hour=13, minute=0, args=["🕐 עדכון צהריים — איך מתקדם?"])
scheduler.add_job(send_checkin, "cron", hour=17, minute=0, args=["🔔 סיום יום — מה הושלם? צריך לדחות משהו?"])
scheduler.start()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5050))
    app.run(debug=False, host="0.0.0.0", port=port)
