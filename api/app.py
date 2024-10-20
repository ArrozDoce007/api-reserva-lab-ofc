from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime
from werkzeug.utils import secure_filename
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib
import mysql.connector
import pytz
import boto3
import threading

app = Flask(__name__)
CORS(app)

# Limitar o tamanho do upload para 10 MB
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10 MB

# Gerenciamento de erros para arquivo muito grande
@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({'error': 'O arquivo enviado é muito grande. O tamanho máximo permitido é de 10 MB.'}), 413

sala_lock = threading.Lock()

# Configurações do S3
AWS_ACCESS_KEY_ID = 'AKIA46ZDE6JYQL3P3EHE'
AWS_SECRET_ACCESS_KEY = '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'
AWS_S3_BUCKET_NAME = 'reserva-lab-nassau'

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

# Função para enviar e-mail
def send_email(to_email, subject, body):
    # Configuração do e-mail
    sender_email = "gui.teste.email.lab@gmail.com"  # Substitua pelo seu e-mail
    sender_password = "ozvvmpjttqoogzwn"
    smtp_server = "smtp.gmail.com"
    smtp_port = 587

    # Criar mensagem
    message = MIMEMultipart()
    message["From"] = sender_email
    message["To"] = to_email
    message["Subject"] = subject
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
        
# Função para conectar ao banco de dados
def get_db_connection():
    try:
        db = mysql.connector.connect(
            host="database-1.c9ec8o0ioxuo.us-east-2.rds.amazonaws.com",
            user="admin",
            password="26042004",
            database="lab_reservation"
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
        
# Rota para logar na página inicial
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
        cursor.execute('SELECT nome, matricula, tipo_usuario FROM usuarios WHERE matricula = %s AND senha = %s', (matricula, senha))
        user = cursor.fetchone()

        if user:
            tipo_usuario = user['tipo_usuario']
            if tipo_usuario not in ['adm', 'user']:
                return jsonify({'success': False, 'message': 'Seu cadastro já foi solicitado e está em análise'}), 403

            return jsonify({
                'success': True,
                'nome': user['nome'],
                'matricula': user['matricula'],
                'tipo_usuario': tipo_usuario
            })
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

    try:
        # Verifica se a matrícula já existe
        cursor.execute('SELECT * FROM usuarios WHERE matricula = %s', (matricula,))
        if cursor.fetchone():
            return jsonify({'success': False, 'message': 'Matrícula já cadastrada'}), 400

        # Insere o novo usuário com tipo_usuario como NULL
        cursor.execute(
            'INSERT INTO usuarios (nome, matricula, email, senha, tipo_usuario) VALUES (%s, %s, %s, %s, %s)',
            (nome, matricula, email, senha, 'null')
        )
        db.commit()

        # Enviar e-mail de confirmação
        subject = "Cadastro solicitado"
        body = f"""
        <html>
            <body>
                <h1>Olá {nome}</h1>
                <p>Seu cadastro ao sistema de reserva de salas foi solicitado com sucesso.</p>
                <p>Aguarde a aprovação do administrador.</p>
                <img src="https://reserva-lab-nassau.s3.us-east-2.amazonaws.com/uninassau.svg" alt="Logo Uninassau"/>
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

# Rota para buscar usuarios
@app.route('/usuarios', methods=['GET'])
def get_usuarios():
    db = get_db_connection()
    if db is None:
        return jsonify({"error": "Erro ao conectar ao banco de dados"}), 500

    cursor = db.cursor(dictionary=True)

    try:
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
def deletar_usuario(user_id):
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

        # Exclui o usuário
        cursor.execute('DELETE FROM usuarios WHERE id = %s', (user_id,))
        db.commit()

        return jsonify({'success': True, 'message': 'Usuário excluído com sucesso'}), 200
    except Exception as e:
        print(f"Erro: {e}")
        return jsonify({"error": "Erro ao excluir o usuário"}), 500
    finally:
        cursor.close()
        db.close()

# Rota para atualizar um usuário
@app.route('/usuarios/atualizar/<int:user_id>', methods=['PUT'])
def update_usuario(user_id):
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
        # Atualiza o tipo de usuário
        cursor.execute('UPDATE usuarios SET tipo_usuario = %s WHERE id = %s', (tipo_usuario, user_id))
        
        # Verifica se a atualização foi feita
        if cursor.rowcount == 0:
            return jsonify({"error": "Usuário não encontrado"}), 404

        db.commit()

        return jsonify({"success": True, "message": "Usuário atualizado com sucesso."})
    except Exception as e:
        print(f"Erro: {e}")
        return jsonify({"error": "Erro ao atualizar o usuário"}), 500
    finally:
        cursor.close()
        db.close()
        
# Rota para obter os laboratórios
@app.route('/laboratorios', methods=['GET'])
def get_laboratorios():
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
def criar_sala():
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
def edit_lab(lab_id):
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

def get_old_image_url(cursor, lab_id):
    cursor.execute("SELECT image FROM Laboratorios WHERE id = %s", (lab_id,))
    result = cursor.fetchone()
    return result[0] if result else None

# Rota para deletar laboratórios/salas
@app.route('/laboratorios/deletar/<int:lab_id>', methods=['DELETE'])
def delete_lab(lab_id):
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
def reservas_lab():
    db = get_db_connection()
    if db is None:
        return jsonify({"error": "Erro ao conectar ao banco de dados"}), 500

    cursor = db.cursor()
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

        return "", 204
    except Exception as e:
        print(f"Erro: {e}")
        return jsonify({"error": "Erro ao processar a reserva"}), 500
    finally:
        cursor.close()
        db.close()

# Rota para obter o reserva geral
@app.route('/reserve/status/geral', methods=['GET'])
def get_reservas_geral():
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
def get_reservas_por_matricula():
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

# Rota para cancelar solicitação
@app.route('/reserve/<int:id>', methods=['PUT'])
def update_reservas(id):
    db = get_db_connection()
    if db is None:
        return jsonify({"error": "Erro ao conectar ao banco de dados"}), 500

    cursor = db.cursor(dictionary=True)
    try:
        data = request.json
        new_status = data.get('status')

        if new_status not in ['pendente', 'aprovado', 'cancelado']:
            return jsonify({"error": "Status inválido"}), 400

        update_query = "UPDATE reservas SET status = %s WHERE id = %s"
        cursor.execute(update_query, (new_status, id))
        db.commit()

        if cursor.rowcount == 0:
            return jsonify({"error": "Reserva não encontrada"}), 404

        # Criar notificação para o usuário
        cursor.execute("SELECT matricula, lab_name, date FROM reservas WHERE id = %s", (id,))
        reservation = cursor.fetchone()
        if reservation:
            formatted_date = datetime.strptime(reservation['date'], '%Y-%m-%d').strftime('%d-%m-%Y')  # Formatar a data
            notification_message = f"Sua reserva para {reservation['lab_name']} em {formatted_date} foi {new_status}."
            create_notification(reservation['matricula'], notification_message)

        return jsonify({"message": "Status da reserva atualizado com sucesso"}), 200
    except Exception as e:
        return jsonify({"error": f"Erro ao atualizar a reserva: {str(e)}"}), 500
    finally:
        cursor.close()
        db.close()

# Rota para rejeitar um pedido
@app.route('/rejeitar/pedido/<int:id>', methods=['POST'])
def rejeitar_pedido(id):
    db = get_db_connection()
    if db is None:
        return jsonify({"error": "Erro ao conectar ao banco de dados"}), 500

    cursor = db.cursor(dictionary=True)
    try:
        data = request.json
        motivo = data.get('motivo')

        if not motivo:
            return jsonify({"error": "Motivo é obrigatório"}), 400

        # Atualiza o status do pedido para rejeitado
        update_query = "UPDATE reservas SET status = %s WHERE id = %s"
        cursor.execute(update_query, ('rejeitado', id))
        db.commit()

        if cursor.rowcount == 0:
            return jsonify({"error": "Pedido não encontrado"}), 404

        # Insere o motivo na tabela de rejeições
        insert_query = "INSERT INTO rejeicoes (pedido_id, motivo) VALUES (%s, %s)"
        cursor.execute(insert_query, (id, motivo))
        db.commit()

        # Criar notificação para o usuário
        cursor.execute("SELECT matricula, lab_name, date FROM reservas WHERE id = %s", (id,))
        reservation = cursor.fetchone()
        if reservation:
            formatted_date = datetime.strptime(reservation['date'], '%Y-%m-%d').strftime('%d-%m-%Y')  # Formatar a data
            notification_message = f"Sua reserva para {reservation['lab_name']} em {formatted_date} foi rejeitada. Motivo: {motivo}."
            create_notification(reservation['matricula'], notification_message)

        return jsonify({"message": "Pedido rejeitado com sucesso"}), 200
    except Exception as e:
        return jsonify({"error": "Erro ao rejeitar o pedido"}), 500
    finally:
        cursor.close()
        db.close()

# Rota para aprovar
@app.route('/aprovar/pedido/<int:id>', methods=['PUT'])
def update_reservas_aprj(id):
    db = get_db_connection()
    if db is None:
        return jsonify({"error": "Erro ao conectar ao banco de dados"}), 500

    cursor = db.cursor(dictionary=True)
    try:
        data = request.json
        new_status = data.get('status')

        if new_status not in ['pendente', 'aprovado']:
            return jsonify({"error": "Status inválido"}), 400

        update_query = "UPDATE reservas SET status = %s WHERE id = %s"
        cursor.execute(update_query, (new_status, id))
        db.commit()

        if cursor.rowcount == 0:
            return jsonify({"error": "Reserva não encontrada"}), 404

        # Criar notificação para o usuário
        cursor.execute("SELECT matricula, lab_name, date FROM reservas WHERE id = %s", (id,))
        reservation = cursor.fetchone()
        if reservation:
            formatted_date = datetime.strptime(reservation['date'], '%Y-%m-%d').strftime('%d-%m-%Y')  # Formatar a data
            notification_message = f"Sua reserva para {reservation['lab_name']} em {formatted_date} foi {new_status}."
            create_notification(reservation['matricula'], notification_message)

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
