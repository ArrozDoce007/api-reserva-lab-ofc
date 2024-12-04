from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# Caminho para o arquivo de credenciais
GOOGLE_CREDENTIALS_FILE = 'calendario-reserva-salas-f4b46c5d82d7.json'

def criar_evento_google_calendar(summary, description, start_time, end_time, attendees_emails):
    try:
        # Autenticação
        credentials = Credentials.from_service_account_file(
            GOOGLE_CREDENTIALS_FILE,
            scopes=["https://www.googleapis.com/auth/calendar"]
        )
        service = build('calendar', 'v3', credentials=credentials)

        # Detalhes do evento
        event = {
            'summary': summary,
            'description': description,
            'start': {
                'dateTime': start_time,
                'timeZone': 'America/Recife',
            },
            'end': {
                'dateTime': end_time,
                'timeZone': 'America/Recife',
            },
            'attendees': [{'email': email} for email in attendees_emails],
        }

        # Criar o evento
        created_event = service.events().insert(calendarId='primary', body=event).execute()
        print(f"Evento criado: {created_event.get('htmlLink')}")
        return created_event.get('htmlLink')
    except Exception as e:
        print(f"Erro ao criar evento: {e}")
        return None