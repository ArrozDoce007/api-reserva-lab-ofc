from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime
from datetime import timedelta
from werkzeug.utils import secure_filename
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from concurrent.futures import ThreadPoolExecutor
from functools import wraps
from dotenv import load_dotenv
import os
import smtplib
import mysql.connector
import pytz
import boto3
import threading
import bcrypt
import jwt

app = Flask(__name__)
CORS(app)

load_dotenv()

# Limitar o tamanho do upload para 10 MB
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10 MB

# Gerenciamento de erros para arquivo muito grande
@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({'error': 'O arquivo enviado é muito grande. O tamanho máximo permitido é de 10 MB.'}), 413

sala_lock = threading.Lock()

# Configurações do S3
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_S3_BUCKET_NAME = os.getenv("AWS_S3_BUCKET_NAME")

s3_client = boto3.client(
    's3',
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name='us-east-2'
)

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
        return True  # A imagem já existe
    except Exception as e:
        if e.response['Error']['Code'] == '404':
            return False  # A imagem não existe
        else:
            print(f'Erro ao verificar a imagem no S3: {e}')
            return False

def delete_from_s3(bucket_name, file_name):
    try:
        s3_client.delete_object(Bucket=bucket_name, Key=file_name)
        print(f"Imagem {file_name} deletada do S3 com sucesso.")
    except Exception as e:
        print(f"Erro ao deletar a imagem do S3: {e}")

# Função para substituir espaços por underscore
def format_filename(filename):
    return filename.replace(' ', '_').replace('-', '_')

executor = ThreadPoolExecutor(max_workers=2)

# Função para enviar e-mail
def send_email(to_email, subject, body):
    # Configuração do e-mail
    sender_email = os.getenv("EMAIL")
    sender_password = os.getenv("EMAIL_PASSWORD")
    smtp_server = os.getenv("EMAIL_SERVER")
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
    
# Chave secreta usada para assinar os tokens
SECRET_KEY = os.getenv("SECRET_KEY")

# Função para gerar token JWT
def generate_token(user):
    payload = {
        'matricula': user['matricula'],  # Informações do usuário
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
        except jwt.ExpiredSignatureError:
            return jsonify({'message': 'Token expirado!'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'message': 'Token inválido!'}), 401

        return f(matricula, *args, **kwargs)
    return decorated
        
# Função para conectar ao banco de dados
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

# Rota data e hora
@app.route('/time/brazilia', methods=['GET'])
def get_brasilia_time():
    try:
        brasilia_tz = pytz.timezone('America/Sao_Paulo')
        brasilia_time = datetime.now(brasilia_tz)
        formatted_time = brasilia_time.strftime('%Y-%m-%dT%H:%M:%S')
        return jsonify({'datetime': formatted_time})
    except Exception as e:
        print(f"Erro: {e}")
        return jsonify({"error": "Erro ao obter a data e hora atual"}), 500
        
# Rota para logar na página inicial e gerar JWT
@app.route('/login', methods=['POST'])
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
@app.route('/cadastro', methods=['POST'])
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
                <img src="https://reserva-lab-nassau.s3.amazonaws.com/uninassau.png" alt="Logo Uninassau" style="width:200px;"/>
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

# Rota para buscar usuários
@app.route('/usuarios', methods=['GET'])
@token_required  # Decorador para proteger a rota
def get_usuarios(matricula):  # Recebe a matrícula do token
    db = get_db_connection()
    if db is None:
        return jsonify({"error": "Erro ao conectar ao banco de dados"}), 500

    cursor = db.cursor(dictionary=True)

    try:
        # Aqui você pode usar a matrícula se precisar filtrar os usuários
        cursor.execute('SELECT * FROM usuarios')
        usuarios = cursor.fetchall()

        return jsonify({
            'success': True,
            'usuarios': usuarios
        })
    except Exception as e:
        print(f"Erro: {e}")
        return jsonify({"error": "Erro ao buscar os usuários"}), 500
    finally:
        cursor.close()
        db.close()

# Rota para deletar usuários
@app.route('/usuarios/deletar/<int:user_id>', methods=['DELETE'])
@token_required  # Decorador para proteger a rota
def deletar_usuario(matricula, user_id):
    db = get_db_connection()
    if db is None:
        return jsonify({"error": "Erro ao conectar ao banco de dados"}), 500

    cursor = db.cursor(dictionary=True)

    try:
        # Verifica se o usuário existe
        cursor.execute('SELECT * FROM usuarios WHERE id = %s', (user_id,))
        user = cursor.fetchone()

        if not user:
            return jsonify({'success': False, 'message': 'Usuário não encontrado'}), 404

        # Recupera o e-mail, nome e matrícula do usuário
        user_email = user['email']
        user_name = user['nome']
        user_matricula = user['matricula']
        user_tipo = user.get('tipo_usuario')

        # Excluir rejeições associadas às reservas rejeitadas do usuário
        cursor.execute('''
            DELETE FROM rejeicoes
            WHERE pedido_id IN (SELECT id FROM reservas WHERE matricula = %s AND status = 'rejeitado')
        ''', (user_matricula,))
        db.commit()

        # Excluir todas as reservas relacionadas ao usuário
        cursor.execute('DELETE FROM reservas WHERE matricula = %s', (user_matricula,))
        db.commit()

        # Excluir notificações associadas ao usuário
        cursor.execute('DELETE FROM notifications WHERE user_matricula = %s', (user_matricula,))
        db.commit()

        # Exclui o usuário
        cursor.execute('DELETE FROM usuarios WHERE id = %s', (user_id,))
        db.commit()

        # Personaliza o e-mail baseado no tipo de usuário
        if user_tipo == 'null':
            subject = "Cadastro negado"
            body = f"""
            <html>
                <body>
                    <h1>Olá {user_name}</h1>
                    <p>Sua solicitação para uso do sistema não foi aceita.</p>
                    <p>Se você tiver dúvidas ou isso foi um erro, entre em contato com o suporte.</p>
                    <br>
                    <img src="https://reserva-lab-nassau.s3.amazonaws.com/uninassau.png" alt="Logo Uninassau" style="width:200px;"/>
                </body>
            </html>
            """
        else:
            subject = "Conta excluída"
            body = f"""
            <html>
                <body>
                    <h1>Olá {user_name}</h1>
                    <p>Sua conta foi excluída do sistema de reserva de salas.</p>
                    <p>Se você não solicitou essa exclusão, entre em contato com o suporte.</p>
                    <br>
                    <img src="https://reserva-lab-nassau.s3.amazonaws.com/uninassau.png" alt="Logo Uninassau" style="width:200px;"/>
                </body>
            </html>
            """

        # Enviar e-mail de notificação de exclusão
        send_email(user_email, subject, body)

        return jsonify({'success': True, 'message': 'Usuário, reservas, rejeições e notificações excluídos com sucesso'}), 200
    except Exception as e:
        print(f"Erro: {e}")
        return jsonify({"error": "Erro ao excluir o usuário"}), 500
    finally:
        cursor.close()
        db.close()
        
# Rota para aprovar um usuário
@app.route('/usuarios/aprovar/<int:user_id>', methods=['PUT'])
@token_required  # Decorador para proteger a rota
def aprove_usuario(matricula, user_id):
    db = get_db_connection()
    if db is None:
        return jsonify({"error": "Erro ao conectar ao banco de dados"}), 500

    cursor = db.cursor(dictionary=True)
    
    # Obtém os dados do corpo da requisição
    data = request.get_json()
    if not data:
        return jsonify({"error": "Dados não fornecidos"}), 400
    
    # Atualiza o campo 'acesso' para 1 ao aprovar o usuário
    try:
        # Recupera o usuário para obter o e-mail e nome
        cursor.execute('SELECT * FROM usuarios WHERE id = %s', (user_id,))
        user = cursor.fetchone()

        if not user:
            return jsonify({"error": "Usuário não encontrado"}), 404

        user_email = user['email']
        user_name = user['nome']
        
        # Atualiza o acesso para 1
        cursor.execute('UPDATE usuarios SET acesso = 1 WHERE id = %s', (user_id,))
        
        # Verifica se a atualização foi feita
        if cursor.rowcount == 0:
            return jsonify({"error": "Usuário não encontrado ou acesso já concedido"}), 404

        db.commit()

        # Enviar e-mail de aprovação
        subject = "Aprovação de Usuário"
        body = f"""
        <html>
            <body>
                <h1>Olá {user_name}</h1>
                <p>Seu acesso ao sistema foi aprovado.</p>
                <p>Acesse o sistema através do link abaixo.</p>
                <a href="https://reserva-salas-uninassau.netlify.app" target="_blank">Sistema de reserva</a>
                <br>
                <img src="https://reserva-lab-nassau.s3.amazonaws.com/uninassau.png" alt="Logo Uninassau" style="width:200px;"/>
            </body>
        </html>
        """

        send_email(user_email, subject, body)

        return jsonify({"success": True, "message": "Usuário aprovado com sucesso."})
    except Exception as e:
        print(f"Erro: {e}")
        return jsonify({"error": "Erro ao atualizar o usuário"}), 500
    finally:
        cursor.close()
        db.close()

# Rota para atualizar um usuário
@app.route('/usuarios/atualizar/<int:user_id>', methods=['PUT'])
@token_required  # Decorador para proteger a rota
def update_usuario(matricula, user_id):
    db = get_db_connection()
    if db is None:
        return jsonify({"error": "Erro ao conectar ao banco de dados"}), 500

    cursor = db.cursor(dictionary=True)
    
    # Obtém os dados do corpo da requisição
    data = request.get_json()
    if not data:
        return jsonify({"error": "Dados não fornecidos"}), 400
    
    # A partir daqui, você pode especificar quais campos deseja atualizar
    tipo_usuario = data.get('tipo_usuario')

    try:
        # Recupera o usuário para obter o e-mail e nome
        cursor.execute('SELECT * FROM usuarios WHERE id = %s', (user_id,))
        user = cursor.fetchone()

        if not user:
            return jsonify({"error": "Usuário não encontrado"}), 404

        user_email = user['email']
        user_name = user['nome']

        # Atualiza o tipo de usuário
        cursor.execute('UPDATE usuarios SET tipo_usuario = %s WHERE id = %s', (tipo_usuario, user_id))
        
        # Verifica se a atualização foi feita
        if cursor.rowcount == 0:
            return jsonify({"error": "Usuário não encontrado"}), 404

        db.commit()

        subject = ""
        body = ""

        if tipo_usuario != 'Administrador':
            subject = "Rebaixamento de Usuário"
            body = f"""
            <html>
                <body>
                    <h1>Olá {user_name}</h1>
                    <p>Seu acesso ao sistema foi rebaixado, você não é mais um administrador.</p>
                    <p>Se você não solicitou essa alteração, entre em contato com o suporte.</p>
                    <br>
                    <img src="https://reserva-lab-nassau.s3.amazonaws.com/uninassau.png" alt="Logo Uninassau" style="width:200px;"/>
                </body>
            </html>
            """
                
        elif tipo_usuario == 'Administrador':
            subject = "Promoção para Administrador"
            body = f"""
            <html>
                <body>
                    <h1>Olá {user_name}</h1>
                    <p>Parabéns! Você foi promovido a administrador.</p>
                    <p>Se você não solicitou essa alteração, entre em contato com o suporte.</p>
                    <br>
                    <img src="https://reserva-lab-nassau.s3.amazonaws.com/uninassau.png" alt="Logo Uninassau" style="width:200px;"/>
                </body>
            </html>
            """

        send_email(user_email, subject, body)

        return jsonify({"success": True, "message": "Usuário atualizado com sucesso."})
    except Exception as e:
        print(f"Erro: {e}")
        return jsonify({"error": "Erro ao atualizar o usuário"}), 500
    finally:
        cursor.close()
        db.close()
        
# Rota para obter os laboratórios
@app.route('/laboratorios', methods=['GET'])
@token_required  # Decorador para proteger a rota
def get_laboratorios(matricula):
    db = get_db_connection()
    if db is None:
        return jsonify({"error": "Erro ao conectar ao banco de dados"}), 500

    cursor = db.cursor(dictionary=True)
    try:
        query = "SELECT id, name, capacity, description, image FROM Laboratorios"
        cursor.execute(query)
        laboratorios = cursor.fetchall()
        return jsonify(laboratorios)
    except Exception as e:
        print(f"Erro: {e}")
        return jsonify({"error": "Erro ao recuperar os laboratórios"}), 500
    finally:
        cursor.close()
        db.close()

# Rota para criar laboratórios/salas
@app.route('/laboratorios/criar', methods=['POST'])
@token_required  # Decorador para proteger a rota
def criar_sala(matricula):
    if 'roomImage' not in request.files or request.files['roomImage'].filename == '':
        return jsonify({'message': 'Imagem não fornecida ou inválida'}), 400
    
    room_image = request.files['roomImage']
    room_name = request.form.get('roomName')
    room_capacity = request.form.get('roomCapacity')
    room_description = request.form.get('roomDescription')

    if room_image and allowed_file(room_image.filename):
        filename = format_filename(secure_filename(room_image.filename))

        db = get_db_connection()
        if db is None:
            return jsonify({"error": "Erro ao conectar ao banco de dados"}), 500

        cursor = db.cursor()
        try:
            # Usa o lock para proteger a seção crítica
            with sala_lock:
                # Verifica se a sala já existe
                cursor.execute('SELECT COUNT(*) FROM Laboratorios WHERE name = %s', (room_name,))
                exists = cursor.fetchone()[0]  # Modificado para obter o primeiro elemento

                if exists > 0:
                    return jsonify({'message': 'Já existe uma sala com este nome. Por favor, escolha outro nome.'}), 400

                # Verifica se a imagem já existe no S3
                if check_image_exists(AWS_S3_BUCKET_NAME, filename):
                    return jsonify({'message': 'Já existe uma imagem com este nome. Por favor, escolha outro nome.'}), 400

                # Faz upload da imagem para o S3
                image_url = upload_to_s3(room_image, AWS_S3_BUCKET_NAME, filename)
                
                if image_url is None:
                    return jsonify({'message': 'Erro ao fazer upload da imagem para o S3'}), 500

                # Inserir dados no banco de dados
                cursor.execute('INSERT INTO Laboratorios (name, capacity, description, image) VALUES (%s, %s, %s, %s)',
                               (room_name, room_capacity, room_description, image_url))
                db.commit()
                return jsonify({'message': 'Sala criada com sucesso!', 'image_url': image_url}), 201
        except Exception as e:
            print(f'Erro ao inserir no banco: {e}')
            db.rollback()  # Reverte a transação em caso de erro
            return jsonify({'message': 'Erro ao criar sala. Tente novamente.'}), 500
        finally:
            cursor.close()
            db.close()
    else:
        return jsonify({'message': 'Arquivo não permitido. Por favor, envie uma imagem válida (PNG, JPG OU JPEG).'}), 400

# Rota para editar laboratórios/salas
@app.route('/laboratorios/editar/<int:lab_id>', methods=['PUT'])
@token_required  # Decorador para proteger a rota
def edit_lab(matricula, lab_id):
    db = get_db_connection()
    if db is None:
        return jsonify({"error": "Erro ao conectar ao banco de dados"}), 500

    cursor = db.cursor()
    data = request.form  # Captura os dados do formulário
    name = data.get('name')
    capacity = data.get('capacity')
    description = data.get('description')
    room_image = request.files.get('roomImage')  # Captura a nova imagem, se fornecida

    try:
        # Verifica se a sala existe antes de tentar atualizar
        cursor.execute("SELECT COUNT(*) FROM Laboratorios WHERE id = %s", (lab_id,))
        if cursor.fetchone()[0] == 0:
            return jsonify({'message': 'Sala não encontrada'}), 404

        # Verifica se o novo nome já existe (exceto para a sala que está sendo editada)
        cursor.execute("SELECT COUNT(*) FROM Laboratorios WHERE name = %s AND id != %s", (name, lab_id))
        if cursor.fetchone()[0] > 0:
            return jsonify({'message': 'Já existe uma sala com esse nome. Por favor, escolha outro nome.'}), 400

        # Atualiza os dados da sala
        cursor.execute("""
            UPDATE Laboratorios
            SET name = %s, capacity = %s, description = %s
            WHERE id = %s
        """, (name, capacity, description, lab_id))

        # Se uma nova imagem foi enviada, faça o upload e atualize o campo de imagem
        if room_image:
            old_image_url = get_old_image_url(cursor, lab_id)  # Obter URL da imagem antiga
            
            # Verifica se a nova imagem já existe no S3
            filename = format_filename(secure_filename(room_image.filename))
            if check_image_exists(AWS_S3_BUCKET_NAME, filename):
                return jsonify({'message': 'Já existe uma imagem com este nome. Por favor, escolha outro nome.'}), 400
            
            if old_image_url:
                # Extrai o nome do arquivo da URL antiga para excluir do S3
                old_filename = old_image_url.split('/')[-1]  # Obtém apenas o nome do arquivo
                delete_from_s3(AWS_S3_BUCKET_NAME, old_filename)  # Exclui a imagem antiga do S3
            
            # Faz upload da nova imagem
            image_url = upload_to_s3(room_image, AWS_S3_BUCKET_NAME, filename)  # Faz upload da nova imagem
            if image_url is None:
                return jsonify({'message': 'Erro ao fazer upload da nova imagem. Tente novamente.'}), 500
            
            # Atualiza o banco de dados com a nova imagem
            cursor.execute("""
                UPDATE Laboratorios
                SET image = %s
                WHERE id = %s
            """, (image_url, lab_id))

        db.commit()
        return jsonify({'message': 'Sala atualizada com sucesso!'}), 200

    except mysql.connector.Error as err:
        print(f"Erro no banco de dados: {err}")
        return jsonify({"message": "Erro ao acessar o banco de dados. Por favor, tente novamente."}), 500
    except Exception as e:
        print(f"Erro: {e}")
        return jsonify({"message": "Erro desconhecido ao atualizar a sala. Por favor, tente novamente."}), 500
    finally:
        cursor.close()
        db.close()

# Busca a imagem atinga
def get_old_image_url(cursor, lab_id):
    cursor.execute("SELECT image FROM Laboratorios WHERE id = %s", (lab_id,))
    result = cursor.fetchone()
    return result[0] if result else None

# Rota para deletar laboratórios/salas
@app.route('/laboratorios/deletar/<int:lab_id>', methods=['DELETE'])
@token_required  # Decorador para proteger a rota
def delete_lab(matricula, lab_id):
    db = get_db_connection()
    if db is None:
        return jsonify({"error": "Erro ao conectar ao banco de dados"}), 500

    cursor = db.cursor(dictionary=True)

    try:
        # Primeiro, busque o laboratório para garantir que ele existe
        cursor.execute("SELECT image FROM Laboratorios WHERE id = %s", (lab_id,))
        lab = cursor.fetchone()

        if lab is None:
            return jsonify({'error': 'Sala não encontrada'}), 404

        # Obtenha a URL da imagem do S3
        image_url = lab['image']

        # Extrair o nome do objeto (chave) da URL
        image_key = image_url.split('/')[-1]

        # Deletar a imagem do S3
        delete_from_s3(AWS_S3_BUCKET_NAME, image_key)

        # Execute a exclusão no banco de dados
        cursor.execute("DELETE FROM Laboratorios WHERE id = %s", (lab_id,))
        db.commit()

        return jsonify({'message': 'Sala deletada com sucesso!'}), 200
    except Exception as e:
        print(f"Erro: {e}")
        return jsonify({"error": "Erro ao deletar a sala"}), 500
    finally:
        cursor.close()
        db.close()

# Rota para fazer a reserva
@app.route('/reserve', methods=['POST'])
@token_required  # Decorador para proteger a rota
def reservas_lab(matricula):
    db = get_db_connection()
    if db is None:
        return jsonify({"error": "Erro ao conectar ao banco de dados"}), 500

    # Criando o cursor com o argumento dictionary=True para retornar os dados como dicionário
    cursor = db.cursor(dictionary=True)
    try:
        data = request.json
        lab_name = data.get('labName')
        date = data.get('date')
        time = data.get('time')
        time_fim = data.get('time_fim')
        purpose = data.get('purpose')
        nome = data.get('userName')
        matricula = data.get('userMatricula')
        software_especifico = data.get('softwareEspecifico', False)
        software_nome = data.get('softwareNome')

        # Verificar se o usuário existe e obtem o e-mail dele no banco de dados
        cursor.execute('SELECT email FROM usuarios WHERE matricula = %s', (matricula,))
        user = cursor.fetchone()

        if not user:
            return jsonify({"error": "Usuário não encontrado"}), 404

        email = user['email']  # Acessa o e-mail a partir do dicionário retornado

        # Inserindo a reserva no banco de dados
        insert_query = """
        INSERT INTO reservas (lab_name, date, time, time_fim, purpose, nome, matricula, status, software_especifico, software_nome)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        cursor.execute(insert_query, (lab_name, date, time, time_fim, purpose, nome, matricula, "pendente", software_especifico, software_nome))
        db.commit()

        formatted_date = datetime.strptime(date, '%Y-%m-%d').strftime('%d-%m-%Y')

        # Criar notificação após a reserva ser criada
        notification_message = f"Sua reserva para {lab_name} em {formatted_date} foi solicitada e está pendente de aprovação."
        create_notification(matricula, notification_message)

        # Enviando o e-mail de confirmação para o usuário
        subject = "Solicitação de Reserva"
        body = f"""
        <html>
            <body>
                <h2>Olá {nome}</h2>
                <p>Sua reserva para o(a) <strong>{lab_name}</strong> no dia <strong>{formatted_date}</strong> das <strong>{time}</strong> às <strong>{time_fim}</strong> foi solicitada.</p>
                <p>Status: <strong <strong style="color: #B8860B;">Pendente de aprovação</strong>.</p>
                <p>Finalidade: {purpose}</p>
                <p>Software específico: {'Sim' if software_especifico else 'Não'}</p>
                {f'<p>Nome do software: {software_nome}</p>' if software_especifico else ''}
                <br>
                <p>Aguarde a aprovação do Administrador.</p>
                <br>
                <img src="https://reserva-lab-nassau.s3.amazonaws.com/uninassau.png" alt="Logo Uninassau" style="width:200px;"/>
            </body>
        </html>
        """
        send_email_async(email, subject, body)

        return "", 204
    except Exception as e:
        print(f"Erro: {e}")
        return jsonify({"error": "Erro ao processar a reserva"}), 500
    finally:
        cursor.close()
        db.close()

# Rota para obter as reservas gerais
@app.route('/reserve/status/geral', methods=['GET'])
@token_required  # Decorador para proteger a rota
def get_reservas_geral(matricula):
    db = get_db_connection()
    if db is None:
        return jsonify({"error": "Erro ao conectar ao banco de dados"}), 500

    cursor = db.cursor(dictionary=True)
    try:
        query = "SELECT id, lab_name, date, time, time_fim, purpose, status, nome, matricula, software_especifico, software_nome FROM reservas"
        cursor.execute(query)
        reservations = cursor.fetchall()
        return jsonify(reservations)
    except Exception as e:
        print(f"Erro: {e}")
        return jsonify({"error": "Erro ao recuperar as reservas"}), 500
    finally:
        cursor.close()
        db.close()

# Rota para obter o reserva por matrícula
@app.route('/reserve/status', methods=['GET'])
@token_required  # Decorador para proteger a rota
def get_reservas_por_matricula(matricula):
    db = get_db_connection()
    if db is None:
        return jsonify({"error": "Erro ao conectar ao banco de dados"}), 500

    cursor = db.cursor(dictionary=True)
    try:
        query = "SELECT id, lab_name, date, time, time_fim, purpose, status, nome, matricula, software_especifico, software_nome FROM reservas"
        cursor.execute(query)
        reservations = cursor.fetchall()

        reservations_list = []
        for reservation in reservations:
            reservations_list.append({
                'id': reservation['id'],
                'lab_name': reservation['lab_name'],
                'date': reservation['date'],
                'time': reservation['time'],
                'time_fim': reservation['time_fim'],
                'purpose': reservation['purpose'],
                'status': reservation['status'],
                'user_name': reservation['nome'],
                'user_matricula': reservation['matricula'],
                'software_especifico': reservation['software_especifico'],
                'software_nome': reservation['software_nome']
            })

        return jsonify(reservations_list)
    except Exception as e:
        print(f"Erro: {e}")
        return jsonify({"error": "Erro ao recuperar as reservas"}), 500
    finally:
        cursor.close()
        db.close()

# Rota para cancelar solicitação
@app.route('/reserve/cancelar/<int:id>', methods=['PUT'])
@token_required  # Decorador para proteger a rota
def update_reservas(matricula, id):
    db = get_db_connection()
    if db is None:
        return jsonify({"error": "Erro ao conectar ao banco de dados"}), 500

    cursor = db.cursor(dictionary=True)
    try:
        data = request.json
        new_status = data.get('status')

        if new_status not in ['pendente', 'aprovado', 'cancelado']:
            return jsonify({"error": "Status inválido"}), 400

        # Atualizar o status da reserva
        update_query = "UPDATE reservas SET status = %s WHERE id = %s"
        cursor.execute(update_query, (new_status, id))
        db.commit()

        if cursor.rowcount == 0:
            return jsonify({"error": "Reserva não encontrada"}), 404

        # Buscar detalhes da reserva e o e-mail do usuário
        cursor.execute("SELECT matricula, lab_name, date, time, time_fim, purpose, software_especifico, software_nome, nome FROM reservas WHERE id = %s", (id,))
        reservation = cursor.fetchone()

        if reservation:
            formatted_date = datetime.strptime(reservation['date'], '%Y-%m-%d').strftime('%d-%m-%Y')  # Formatar a data
            notification_message = f"Sua reserva para {reservation['lab_name']} em {formatted_date} foi {new_status}."
            create_notification(reservation['matricula'], notification_message)

            # Obter o e-mail do usuário no banco de dados
            cursor.execute('SELECT email FROM usuarios WHERE matricula = %s', (reservation['matricula'],))
            user = cursor.fetchone()

            if user:
                email = user['email']
                nome = reservation['nome']
                lab_name = reservation['lab_name']
                time = reservation['time']
                time_fim = reservation['time_fim']
                purpose = reservation['purpose']
                software_especifico = reservation['software_especifico']
                software_nome = reservation['software_nome']

                # Criar o corpo do e-mail com base no novo status
                subject = "Cancelamento da Reserva"
                body = f"""
                <html>
                    <body>
                        <h2>Olá {nome}</h2>
                        <p>Sua reserva para o(a) <strong>{lab_name}</strong> no dia <strong>{formatted_date}</strong> das <strong>{time}</strong> às <strong>{time_fim}</strong> foi <strong style="color: #FF0000;">{new_status}</strong>.</p>
                        <p>Finalidade: {purpose}</p>
                        <p>Software específico: {'Sim' if software_especifico else 'Não'}</p>
                        {f'<p>Nome do software: {software_nome}</p>' if software_especifico else ''}
                        <br>
                        <p>Caso tenha dúvidas, entre em contato com a Administração.</p>
                        <br>
                        <img src="https://reserva-lab-nassau.s3.amazonaws.com/uninassau.png" alt="Logo Uninassau" style="width:200px;"/>
                    </body>
                </html>
                """
                
                send_email_async(email, subject, body)

        return jsonify({"message": "Status da reserva atualizado com sucesso"}), 200
    except Exception as e:
        return jsonify({"error": f"Erro ao atualizar a reserva: {str(e)}"}), 500
    finally:
        cursor.close()
        db.close()

# Rota para obter o motivo de rejeição
@app.route('/rejeicoes/<int:pedido_id>', methods=['GET'])
def get_rejeicao(pedido_id):
    db = get_db_connection()
    try:
        cursor = db.cursor(dictionary=True)
        query = "SELECT motivo FROM rejeicoes WHERE pedido_id = %s"
        cursor.execute(query, (pedido_id,))
        result = cursor.fetchone()

        if result:
            return jsonify(result)
        else:
            return jsonify({"error": "Motivo de rejeição não encontrado"}), 404
    except mysql.connector.Error as err:
        return jsonify({"error": f"Erro no banco de dados: {str(err)}"}), 500

# Rota para rejeitar um pedido
@app.route('/rejeitar/pedido/<int:id>', methods=['POST'])
@token_required  # Decorador para proteger a rota
def rejeitar_pedido(matricula, id):
    db = get_db_connection()
    if db is None:
        return jsonify({"error": "Erro ao conectar ao banco de dados"}), 500

    cursor = db.cursor(dictionary=True)
    try:
        data = request.json
        motivo = data.get('motivo')
        new_status = data.get('status', 'rejeitado')  # Define 'rejeitado' como padrão caso o status não seja enviado

        if not motivo:
            return jsonify({"error": "Motivo é obrigatório"}), 400

        # Atualiza o status do pedido para o valor de new_status
        update_query = "UPDATE reservas SET status = %s WHERE id = %s"
        cursor.execute(update_query, (new_status, id))
        db.commit()

        if cursor.rowcount == 0:
            return jsonify({"error": "Pedido não encontrado"}), 404

        # Insere o motivo na tabela de rejeições
        insert_query = "INSERT INTO rejeicoes (pedido_id, motivo) VALUES (%s, %s)"
        cursor.execute(insert_query, (id, motivo))
        db.commit()

        # Criar notificação para o usuário
        cursor.execute("SELECT matricula, lab_name, date, time, time_fim, nome FROM reservas WHERE id = %s", (id,))
        reservation = cursor.fetchone()

        if reservation:
            formatted_date = datetime.strptime(reservation['date'], '%Y-%m-%d').strftime('%d-%m-%Y')  # Formatar a data
            notification_message = f"Sua reserva para {reservation['lab_name']} em {formatted_date} foi {new_status}. Motivo: {motivo}."
            create_notification(reservation['matricula'], notification_message)

            # Obter o e-mail do usuário no banco de dados
            cursor.execute('SELECT email FROM usuarios WHERE matricula = %s', (reservation['matricula'],))
            user = cursor.fetchone()

            if user:
                email = user['email']
                nome = reservation['nome']
                lab_name = reservation['lab_name']
                time = reservation['time']
                time_fim = reservation['time_fim']

                # Criar o corpo do e-mail de rejeição
                subject = "Reserva Rejeitada"
                body = f"""
                <html>
                    <body>
                        <h2>Olá {nome}</h2>
                        <p>Lamentamos informar que sua reserva para o(a) <strong>{lab_name}</strong> no dia <strong>{formatted_date}</strong> das <strong>{time}</strong> às <strong>{time_fim}</strong> foi <strong style="color: #FF0000;">{new_status}</strong>.</p>
                        <p>Motivo da rejeição: {motivo}</p>
                        <br>
                        <p>Caso tenha dúvidas, entre em contato com a Administração.</p>
                        <br>
                        <img src="https://reserva-lab-nassau.s3.amazonaws.com/uninassau.png" alt="Logo Uninassau" style="width:200px;"/>
                    </body>
                </html>
                """

                send_email_async(email, subject, body)

        return jsonify({"message": "Pedido rejeitado com sucesso"}), 200
    except Exception as e:
        return jsonify({"error": "Erro ao rejeitar o pedido"}), 500
    finally:
        cursor.close()
        db.close()

# Rota para aprovar um pedido
@app.route('/aprovar/pedido/<int:id>', methods=['PUT'])
@token_required  # Decorador para proteger a rota
def update_reservas_aprj(matricula, id):
    db = get_db_connection()
    if db is None:
        return jsonify({"error": "Erro ao conectar ao banco de dados"}), 500

    cursor = db.cursor(dictionary=True)
    try:
        data = request.json
        new_status = data.get('status')

        if new_status not in ['pendente', 'aprovado']:
            return jsonify({"error": "Status inválido"}), 400

        # Atualizar o status da reserva
        update_query = "UPDATE reservas SET status = %s WHERE id = %s"
        cursor.execute(update_query, (new_status, id))
        db.commit()

        if cursor.rowcount == 0:
            return jsonify({"error": "Reserva não encontrada"}), 404

        # Buscar detalhes da reserva e o e-mail do usuário
        cursor.execute("SELECT matricula, lab_name, date, time, time_fim, nome FROM reservas WHERE id = %s", (id,))
        reservation = cursor.fetchone()

        if reservation:
            formatted_date = datetime.strptime(reservation['date'], '%Y-%m-%d').strftime('%d-%m-%Y')  # Formatar a data
            notification_message = f"Sua reserva para {reservation['lab_name']} em {formatted_date} foi {new_status}."
            create_notification(reservation['matricula'], notification_message)

            # Obter o e-mail do usuário no banco de dados
            cursor.execute('SELECT email FROM usuarios WHERE matricula = %s', (reservation['matricula'],))
            user = cursor.fetchone()

            if user:
                email = user['email']
                nome = reservation['nome']
                lab_name = reservation['lab_name']
                time = reservation['time']
                time_fim = reservation['time_fim']

                # Criar o corpo do e-mail de aprovação
                subject = "Reserva Aprovada"
                body = f"""
                <html>
                    <body>
                        <h2>Olá {nome}</h2>
                        <p>Sua reserva para o(a) <strong>{lab_name}</strong> no dia <strong>{formatted_date}</strong> das <strong>{time}</strong> às <strong>{time_fim}</strong> foi <strong style="color: #006400;">{new_status}</strong>.</p>
                        <br>
                        <p>Estamos ansiosos para recebê-lo. Caso tenha dúvidas, entre em contato com a Administração.</p>
                        <br>
                        <img src="https://reserva-lab-nassau.s3.amazonaws.com/uninassau.png" alt="Logo Uninassau" style="width:200px;"/>
                    </body>
                </html>
                """

                # Enviar o e-mail de aprovação de forma assíncrona
                send_email_async(email, subject, body)

        return jsonify({"message": "Status da reserva atualizado com sucesso"}), 200
    except Exception as e:
        return jsonify({"error": f"Erro ao atualizar a reserva: {str(e)}"}), 500
    finally:
        cursor.close()
        db.close()

# Função auxiliar para criar notificações
def create_notification(user_matricula, message):
    db = get_db_connection()
    if db is None:
        print("Erro ao conectar ao banco de dados")
        return

    cursor = db.cursor()
    try:
        insert_query = "INSERT INTO notifications (user_matricula, message) VALUES (%s, %s)"
        cursor.execute(insert_query, (user_matricula, message))
        db.commit()
    except Exception as e:
        print(f"Erro ao criar notificação: {e}")
    finally:
        cursor.close()
        db.close()

# Rota para obter notificações do usuário
@app.route('/notifications/<string:matricula>', methods=['GET'])
def get_notifications(matricula):
    db = get_db_connection()
    if db is None:
        return jsonify({"error": "Erro ao conectar ao banco de dados"}), 500

    cursor = db.cursor(dictionary=True)
    try:
        query = "SELECT id, message, created_at, is_read FROM notifications WHERE user_matricula = %s ORDER BY created_at DESC"
        cursor.execute(query, (matricula,))
        notifications = cursor.fetchall()
        return jsonify(notifications)
    except Exception as e:
        print(f"Erro: {e}")
        return jsonify({"error": "Erro ao recuperar as notificações"}), 500
    finally:
        cursor.close()
        db.close()

# Rota para marcar notificações como lidas
@app.route('/notifications/read', methods=['POST'])
def mark_notifications_read():
    db = get_db_connection()
    if db is None:
        return jsonify({"error": "Erro ao conectar ao banco de dados"}), 500

    cursor = db.cursor()
    try:
        data = request.json
        notification_ids = data.get('notification_ids', [])
        
        if not notification_ids:
            return jsonify({"error": "Nenhum ID de notificação fornecido"}), 400

        update_query = "UPDATE notifications SET is_read = TRUE WHERE id IN (%s)"
        format_strings = ','.join(['%s'] * len(notification_ids))
        cursor.execute(update_query % format_strings, tuple(notification_ids))
        db.commit()

        return jsonify({"message": "Notificações marcadas como lidas"}), 200
    except Exception as e:
        print(f"Erro: {e}")
        return jsonify({"error": "Erro ao marcar notificações como lidas"}), 500
    finally:
        cursor.close()
        db.close()

# Rota para limpar todas as notificações do usuário
@app.route('/notifications/clear/<string:matricula>', methods=['DELETE'])
def clear_notifications(matricula):
    db = get_db_connection()
    if db is None:
        return jsonify({"error": "Erro ao conectar ao banco de dados"}), 500

    cursor = db.cursor()
    try:
        delete_query = "DELETE FROM notifications WHERE user_matricula = %s"
        cursor.execute(delete_query, (matricula,))
        db.commit()
        return jsonify({"message": "Todas as notificações foram removidas"}), 200
    except Exception as e:
        print(f"Erro: {e}")
        return jsonify({"error": "Erro ao limpar as notificações"}), 500
    finally:
        cursor.close()
        db.close()

if __name__ == '__main__':
    app.run(debug=True)
