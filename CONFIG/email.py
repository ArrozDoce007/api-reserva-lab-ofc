from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
import smtplib
import os

load_dotenv()

executor = ThreadPoolExecutor(max_workers=2)

# Função para enviar e-mail
def send_email(to_email, subject, body):
    # Configuração do e-mail
    sender_email = os.getenv("EMAIL")
    sender_password = os.getenv("EMAIL_PASSWORD")
    smtp_server = "smtp.office365.com"
    smtp_port = 587

    # Criar mensagem
    message = MIMEMultipart()
    message["From"] = "Sistema de Salas"
    message["To"] = to_email
    message["Subject"] = subject

    # Anexando o corpo HTML
    message.attach(MIMEText(body, "html"))
    
    # Enviar e-mail
    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(message)
        print(f"Email enviado com sucesso para {to_email}")
    except Exception as e:
        print(f"Erro ao enviar e-mail: {e}")

# Função para enviar e-mail de forma assíncrona
def send_email_async(to_email, subject, body):
    executor.submit(send_email, to_email, subject, body)