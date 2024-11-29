from flask import request, jsonify
from dotenv import load_dotenv
from functools import wraps
from datetime import datetime
from datetime import timedelta
import jwt
import os

load_dotenv()

# Chave secreta usada para assinar os tokens
SECRET_KEY = os.getenv("SECRET_KEY")

# Função para gerar token JWT
def generate_token(user, user_type):
    payload = {
        'matricula': user['matricula'],  # Informações do usuário
        'tipo_usuario': user_type,       # Tipo de usuário no payload
        'exp': datetime.utcnow() + timedelta(minutes=20)
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm='HS256')
    return token

# Função para verificar token JWT (decorador)
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        # Verifica se o token está no cabeçalho da requisição
        if 'Authorization' in request.headers:
            token = request.headers['Authorization'].split(" ")[1]
        
        if not token:
            return jsonify({'message': 'Token é necessário!'}), 401

        try:
            # Decodifica o token
            data = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
            matricula = data['matricula']  # Matricula extraída do token
            user_type = data['tipo_usuario']  # Tipo de usuário extraído do token
        except jwt.ExpiredSignatureError:
            return jsonify({'message': 'Token expirado!'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'message': 'Token inválido!'}), 401

        # Passa a matrícula e o tipo de usuário para a rota
        return f(matricula, user_type, *args, **kwargs)
    return decorated