from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from datetime import datetime, timezone

GOOGLE_CREDENTIALS_FILE = 'credentials.json'

def adicionar_evento_google_calendar(summary, description, start_time, end_time, attendees_emails):
    try:
        credentials = Credentials.from_service_account_file(
            GOOGLE_CREDENTIALS_FILE,
            scopes=["https://www.googleapis.com/auth/calendar"]
        )
        service = build('calendar', 'v3', credentials=credentials)

        event = {
            'summary': summary,
            'description': description,
            'start': {
                'dateTime': start_time,
                'timeZone': 'America/Recife',  # Adjust if necessary
            },
            'end': {
                'dateTime': end_time,
                'timeZone': 'America/Recife',  # Adjust if necessary
            },
            'attendees': [{'email': email} for email in attendees_emails],
        }

        created_event = service.events().insert(calendarId='primary', body=event).execute()
        print(f'Evento criado: {created_event.get("htmlLink")}')
        return created_event.get('htmlLink')
    except Exception as e:
        print(f"Erro ao criar evento no Google Calendar: {str(e)}")
        raise