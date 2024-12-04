from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
import os
import requests

load_dotenv()

executor = ThreadPoolExecutor(max_workers=2)

# Função para obter o token de acesso OAuth2 com credenciais de cliente
def get_access_token():
    url = f"https://login.microsoftonline.com/common/oauth2/v2.0/token"  # URL para obter o token

    client_id = os.getenv("CLIENT_ID")
    client_secret = os.getenv("CLIENT_SECRET")
    scope = "https://graph.microsoft.com/.default"  # A permissão deve ser para a API da Microsoft Graph
    
    # Parâmetros para obtenção do token
    data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": scope,
    }

    # Requisição para obter o token
    response = requests.post(url, data=data)
    
    if response.status_code == 200:
        token_data = response.json()
        return token_data['access_token']
    else:
        print(f"Erro ao obter o token: {response.text}")
        return None

# Função para enviar e-mail via Microsoft Graph API (sem interação humana)
def send_email(to_email, subject, body):
    # Obter o token de acesso OAuth2
    access_token = get_access_token()

    if not access_token:
        print("Não foi possível obter o token de acesso.")
        return

    # Configuração do e-mail
    sender_email = os.getenv("EMAIL")
    
    # Configurar o corpo do e-mail
    email_data = {
        "message": {
            "subject": subject,
            "body": {
                "contentType": "HTML",
                "content": body
            },
            "toRecipients": [
                {
                    "emailAddress": {
                        "address": to_email
                    }
                }
            ]
        }
    }
    
    # URL da API Graph para enviar e-mail
    url = f"https://graph.microsoft.com/v1.0/users/{sender_email}/sendMail"  # Use o e-mail do usuário configurado
    
    # Configurar cabeçalhos
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    # Enviar o e-mail via Microsoft Graph
    response = requests.post(url, json=email_data, headers=headers)
    
    if response.status_code == 202:
        print(f"Email enviado com sucesso para {to_email}")
    else:
        print(f"Erro ao enviar e-mail: {response.status_code} - {response.text}")

# Função para enviar e-mail de forma assíncrona
def send_email_async(to_email, subject, body):
    executor.submit(send_email, to_email, subject, body)
