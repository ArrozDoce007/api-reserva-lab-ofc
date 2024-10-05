from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
import mysql.connector
from datetime import datetime
import pytz

app = Flask(__name__)
CORS(app)  # Habilita CORS para todas as rotas

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
            return jsonify({
                'success': True,
                'nome': user['nome'],
                'matricula': user['matricula'],
                'tipo_usuario': user['tipo_usuario']
            })
        else:
            return jsonify({'success': False, 'message': 'Matrícula ou senha inválidos'}), 401
    except Exception as e:
        print(f"Erro: {e}")
        return jsonify({"error": "Erro ao realizar o login"}), 500
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
    cursor = db.cursor(dictionary=True)
    query = "SELECT motivo FROM rejeicoes WHERE pedido_id = %s"
    cursor.execute(query, (pedido_id,))
    result = cursor.fetchone()

    if result:
        return jsonify(result)
    else:
        return jsonify({"error": "Motivo de rejeição não encontrado"}), 404

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
            notification_message = f"Sua reserva para {reservation['lab_name']} em {reservation['date']} foi {new_status}."
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
            notification_message = f"Sua reserva para {reservation['lab_name']} em {reservation['date']} foi rejeitada. Motivo: {motivo}."
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
            notification_message = f"Sua reserva para {reservation['lab_name']} em {reservation['date']} foi {new_status}."
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
