from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
import smtplib
import os
import base64
import requests
from requests.auth import HTTPBasicAuth

load_dotenv()

executor = ThreadPoolExecutor(max_workers=2)

# Função para obter o token de acesso OAuth2
def get_access_token():
    tenant_id = os.getenv("TENANT_ID")  # Carregar o Tenant ID do arquivo .env
    url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"  # URL com o Tenant ID

    client_id = os.getenv("CLIENT_ID")
    client_secret = os.getenv("CLIENT_SECRET")
    scope = "https://outlook.office365.com/.default"
    
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

# Função para enviar e-mail via OAuth2
def send_email(to_email, subject, body):
    # Configuração do e-mail
    sender_email = os.getenv("EMAIL")
    smtp_server = os.getenv("EMAIL_SERVER")
    smtp_port = 587

    # Obter o token de acesso OAuth2
    access_token = get_access_token()

    if not access_token:
        print("Não foi possível obter o token de acesso.")
        return

    # Criar a mensagem
    message = MIMEMultipart()
    message["From"] = sender_email
    message["To"] = to_email
    message["Subject"] = subject

    # Anexando o corpo HTML
    message.attach(MIMEText(body, "html"))
    
    # Preparar a autenticação OAuth2
    auth_string = base64.b64encode(
        f"user={sender_email}\1auth=Bearer {access_token}\1\1".encode()
    ).decode()

    # Enviar e-mail
    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.ehlo()
            server.docmd("AUTH XOAUTH2", auth_string)
            server.send_message(message)
        print(f"Email enviado com sucesso para {to_email}")
    except Exception as e:
        print(f"Erro ao enviar e-mail: {e}")

# Função para enviar e-mail de forma assíncrona
def send_email_async(to_email, subject, body):
    executor.submit(send_email, to_email, subject, body)