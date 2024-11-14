from flask import Blueprint, request, jsonify
import bcrypt
from CONFIG.db import get_db_connection
from CONFIG.token import generate_token
from CONFIG.email import send_email

login_cadastro_bp = Blueprint('login_cadastro', __name__)

# Rota para logar na página inicial e gerar JWT
@login_cadastro_bp.route('/login', methods=['POST'])
def login():
    db = get_db_connection()
    if db is None:
        return jsonify({"error": "Erro ao conectar ao banco de dados"}), 500

    cursor = db.cursor(dictionary=True)
    data = request.json
    matricula = data.get('matricula')
    senha = data.get('senha')

    try:
        # Busca o usuário pelo número de matrícula
        cursor.execute('SELECT nome, matricula, senha, tipo_usuario, acesso FROM usuarios WHERE matricula = %s', (matricula,))
        user = cursor.fetchone()

        if user:
            # Verifica se a senha é correta
            hashed_senha = user['senha']
            if bcrypt.checkpw(senha.encode('utf-8'), hashed_senha.encode('utf-8')):
                acesso = user['acesso']
                if acesso != 1:
                    return jsonify({'success': False, 'message': 'Seu cadastro está em análise'}), 403

                # Gera o token JWT
                token = generate_token(user)

                return jsonify({
                    'success': True,
                    'nome': user['nome'],
                    'matricula': user['matricula'],
                    'tipo_usuario': user['tipo_usuario'],
                    'token': token  # Retorna o token JWT
                })
            else:
                return jsonify({'success': False, 'message': 'Matrícula ou senha inválidos'}), 401
        else:
            return jsonify({'success': False, 'message': 'Matrícula ou senha inválidos'}), 401
    except Exception as e:
        print(f"Erro: {e}")
        return jsonify({"error": "Erro ao realizar o login"}), 500
    finally:
        cursor.close()
        db.close()

# Rota para cadastro de usuários
@login_cadastro_bp.route('/cadastro', methods=['POST'])
def cadastro():
    db = get_db_connection()
    if db is None:
        return jsonify({"error": "Erro ao conectar ao banco de dados"}), 500

    cursor = db.cursor(dictionary=True)
    data = request.json
    nome = data.get('nome')
    matricula = data.get('matricula')
    email = data.get('email')
    senha = data.get('senha')
    tipo_usuario = data.get('tipoUsuario')

    try:
        # Verifica se a matrícula já existe
        cursor.execute('SELECT * FROM usuarios WHERE matricula = %s', (matricula,))
        if cursor.fetchone():
            return jsonify({'success': False, 'message': 'Matrícula já cadastrada'}), 400

        # Criptografar a senha usando bcrypt
        hashed_senha = bcrypt.hashpw(senha.encode('utf-8'), bcrypt.gensalt(12))

        # Insere o novo usuário fornecido e a senha criptografada
        cursor.execute(
            'INSERT INTO usuarios (nome, matricula, email, senha, tipo_usuario) VALUES (%s, %s, %s, %s, %s)',
            (nome, matricula, email, hashed_senha.decode('utf-8'), tipo_usuario)
        )
        db.commit()

        # Enviar e-mail de confirmação
        subject = "Cadastro solicitado"
        body = f"""
        <html>
            <body>
                <h1>Olá {nome}</h1>
                <p>Seu cadastro ao sistema de reserva de salas foi solicitado com sucesso.</p>
                <p>Aguarde a aprovação do Administrador.</p>
                <br>
                <img src="https://reserva-lab-nassau.s3.amazonaws.com/assets/uninassau.png" alt="Logo Uninassau" style="width:200px;"/>
            </body>
        </html>
        """
        send_email(email, subject, body)

        return jsonify({'success': True, 'message': 'Cadastro solicitado com sucesso'})
    except Exception as e:
        print(f"Erro: {e}")
        return jsonify({"error": "Erro ao solicitar o cadastro"}), 500
    finally:
        cursor.close()
        db.close()