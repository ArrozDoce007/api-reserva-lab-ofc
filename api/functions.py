# functions.py
from flask import request, jsonify
import jwt
import os
import mysql.connector
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from functools import wraps
import smtplib
from config import s3_client, executor, SECRET_KEY
from concurrent.futures import ThreadPoolExecutor

def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def upload_to_s3(file_obj, bucket_name, file_name):
    try:
        s3_client.upload_fileobj(file_obj, bucket_name, file_name)
        file_url = f"https://{bucket_name}.s3.amazonaws.com/{file_name}"
        return file_url
    except Exception as e:
        print(f"Erro ao fazer upload para o S3: {e}")
        return None

def check_image_exists(bucket_name, filename):
    try:
        s3_client.head_object(Bucket=bucket_name, Key=filename)
        return True
    except Exception as e:
        if e.response['Error']['Code'] == '404':
            return False
        else:
            print(f'Erro ao verificar a imagem no S3: {e}')
            return False

def delete_from_s3(bucket_name, file_name):
    try:
        s3_client.delete_object(Bucket=bucket_name, Key=file_name)
        print(f"Imagem {file_name} deletada do S3 com sucesso.")
    except Exception as e:
        print(f"Erro ao deletar a imagem do S3: {e}")

def format_filename(filename):
    return filename.replace(' ', '_').replace('-', '_')

def send_email(to_email, subject, body):
    sender_email = os.getenv("EMAIL")
    sender_password = os.getenv("EMAIL_PASSWORD")
    smtp_server = os.getenv("EMAIL_SERVER")
    smtp_port = 587

    message = MIMEMultipart()
    message["From"] = "Sistema de Salas"
    message["To"] = to_email
    message["Subject"] = subject
    message.attach(MIMEText(body, "html"))
    
    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(message)
    except Exception as e:
        print(f"Erro ao enviar e-mail: {e}")

executor = ThreadPoolExecutor(max_workers=2)

def send_email_async(to_email, subject, body):
    executor.submit(send_email, to_email, subject, body)

def generate_token(user):
    payload = {
        'matricula': user['matricula'],
        'exp': datetime.utcnow() + timedelta(minutes=20)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm='HS256')

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', None)
        if not token:
            return jsonify({'message': 'Token é necessário!'}), 401
        try:
            data = jwt.decode(token.split(" ")[1], SECRET_KEY, algorithms=['HS256'])
            matricula = data['matricula']
        except jwt.ExpiredSignatureError:
            return jsonify({'message': 'Token expirado!'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'message': 'Token inválido!'}), 401
        return f(matricula, *args, **kwargs)
    return decorated

def get_db_connection():
    try:
        db = mysql.connector.connect(
            host = os.getenv("DB_HOST"),
            user = os.getenv("DB_USER"),
            password = os.getenv("DB_PASSWORD"),
            database = os.getenv("DB_NAME")
        )
        return db
    except mysql.connector.Error as err:
        print(f"Erro ao conectar ao banco de dados: {err}")
        return None