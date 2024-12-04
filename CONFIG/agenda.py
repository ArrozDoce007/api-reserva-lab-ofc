from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# Caminho para o arquivo de credenciais
GOOGLE_CREDENTIALS_FILE = 'credentials.json'  # Coloque o caminho correto aqui

# Função para criar o evento no Google Calendar
def adicionar_evento_google_calendar(summary, description, start_time, end_time, attendees_emails):
    try:
        # Autenticação com a conta de serviço
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

        # Criar evento no Google Calendar (usando o calendarId 'primary' para a conta de serviço)
        created_event = service.events().insert(calendarId='primary', body=event).execute()
        return created_event.get('htmlLink')  # Retorna o link do evento criado
    except Exception as e:
        raise Exception(f"Erro ao criar evento no Google Calendar: {str(e)}")