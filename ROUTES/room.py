from flask import Blueprint, request, jsonify
from CONFIG.db import get_db_connection
from CONFIG.token import token_required
from CONFIG.s3 import allowed_file, upload_to_s3, check_image_exists, delete_from_s3, format_filename, get_old_image_url, AWS_S3_BUCKET_NAME
from werkzeug.utils import secure_filename
import mysql.connector
import threading
sala_lock = threading.Lock()

room_bp = Blueprint('room', __name__)

# Gerenciamento de erros para arquivo muito grande
@room_bp.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({'error': 'O arquivo enviado é muito grande. O tamanho máximo permitido é de 10 MB.'}), 413

# Rota para obter os laboratórios
@room_bp.route('/laboratorios', methods=['GET'])
@token_required  # Decorador para proteger a rota
def get_laboratorios(matricula, tipo_usuario, is_admin):
    if not is_admin:  # Restrição para usuários não administradores
        return jsonify({'message': 'Acesso negado! Apenas administradores podem acessar esta rota.'}), 403
    
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
@room_bp.route('/laboratorios/criar', methods=['POST'])
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
@room_bp.route('/laboratorios/editar/<int:lab_id>', methods=['PUT'])
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

# Rota para deletar laboratórios/salas
@room_bp.route('/laboratorios/deletar/<int:lab_id>', methods=['DELETE'])
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
