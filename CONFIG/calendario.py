<<<<<<< HEAD
from datetime import datetime
import requests
from msal import ConfidentialClientApplication

# Função para obter o token de acesso do Microsoft Graph
def get_outlook_token():
    client_id = "379f5aa8-3a26-4a36-b354-30bac3e47a78"
    client_secret = "fmT8Q~KKaXDtdwc91PvbU.D.sF_umzHxTO37Ia.u"
    tenant_id = "3b1fb1c8-e579-4141-bbff-5b4ce4ee95d8"

    authority = f"https://login.microsoftonline.com/{tenant_id}"
    scope = ["https://graph.microsoft.com/.default"]

    app = ConfidentialClientApplication(
        client_id=client_id,
        client_credential=client_secret,
        authority=authority
    )

    result = app.acquire_token_for_client(scopes=scope)

    if "access_token" not in result:
        raise Exception(f"Erro ao obter token: {result.get('error_description', 'Desconhecido')}")

    return result["access_token"]

# Função para criar o evento no Outlook
def create_outlook_event(participant_name, email, lab_name, start_datetime, end_datetime):
    token = get_outlook_token()

    url = "https://graph.microsoft.com/v1.0/me/events"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    event_data = {
        "subject": f"Reserva Aprovada: {lab_name}",
        "body": {
            "contentType": "HTML",
            "content": f"Reserva confirmada para o laboratório {lab_name}."
        },
        "start": {
            "dateTime": start_datetime,
            "timeZone": "America/Sao_Paulo"
        },
        "end": {
            "dateTime": end_datetime,
            "timeZone": "America/Sao_Paulo"
        },
        "attendees": [
            {
                "emailAddress": {
                    "address": email,
                    "name": participant_name
                },
                "type": "required"
            }
        ]
    }

    response = requests.post(url, headers=headers, json=event_data)
    if response.status_code != 201:
        raise Exception(f"Erro ao criar evento no Outlook: {response.json()}")
=======
from datetime import datetime
import requests
from msal import ConfidentialClientApplication

# Função para obter o token de acesso do Microsoft Graph
def get_outlook_token():
    client_id = "379f5aa8-3a26-4a36-b354-30bac3e47a78"
    client_secret = "fmT8Q~KKaXDtdwc91PvbU.D.sF_umzHxTO37Ia.u"
    tenant_id = "3b1fb1c8-e579-4141-bbff-5b4ce4ee95d8"

    authority = f"https://login.microsoftonline.com/{tenant_id}"
    scope = ["https://graph.microsoft.com/.default"]

    app = ConfidentialClientApplication(
        client_id=client_id,
        client_credential=client_secret,
        authority=authority
    )

    result = app.acquire_token_for_client(scopes=scope)

    if "access_token" not in result:
        raise Exception(f"Erro ao obter token: {result.get('error_description', 'Desconhecido')}")

    return result["access_token"]

# Função para criar o evento no Outlook
def create_outlook_event(participant_name, email, lab_name, start_datetime, end_datetime):
    token = get_outlook_token()

    url = "https://graph.microsoft.com/v1.0/me/events"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    event_data = {
        "subject": f"Reserva Aprovada: {lab_name}",
        "body": {
            "contentType": "HTML",
            "content": f"Reserva confirmada para o laboratório {lab_name}."
        },
        "start": {
            "dateTime": start_datetime,
            "timeZone": "America/Sao_Paulo"
        },
        "end": {
            "dateTime": end_datetime,
            "timeZone": "America/Sao_Paulo"
        },
        "attendees": [
            {
                "emailAddress": {
                    "address": email,
                    "name": participant_name
                },
                "type": "required"
            }
        ]
    }

    response = requests.post(url, headers=headers, json=event_data)
    if response.status_code != 201:
        raise Exception(f"Erro ao criar evento no Outlook: {response.json()}")
>>>>>>> 3ce02a7c2afe69c5314fcdb9c3a4cdeb2578d13e
    return response.json()