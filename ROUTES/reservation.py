from flask import Blueprint, request, jsonify
from CONFIG.db import get_db_connection
from CONFIG.token import token_required
from CONFIG.email import send_email_async
from CONFIG.calendario import create_outlook_event
from datetime import datetime
import mysql.connector

reservation_bp = Blueprint('reservation', __name__)

# Rota para fazer a reserva
@reservation_bp.route('/reserve', methods=['POST'])
@token_required  # Decorador para proteger a rota
def reservas_lab(matricula, tipo_usuario, is_admin):
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
                <img src="https://reserva-lab-nassau.s3.amazonaws.com/assets/uninassau.png" alt="Logo Uninassau" style="width:200px;"/>
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
@reservation_bp.route('/reserve/status/geral', methods=['GET'])
@token_required  # Decorador para proteger a rota
def get_reservas_geral(matricula, tipo_usuario, is_admin):
    if not is_admin:  # Restrição para usuários não administradores
        return jsonify({'message': 'Acesso negado! Apenas administradores podem acessar esta rota.'}), 403
    
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
@reservation_bp.route('/reserve/status', methods=['GET'])
@token_required  # Decorador para proteger a rota
def get_reservas_por_matricula(matricula, tipo_usuario, is_admin):
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
@reservation_bp.route('/reserve/cancelar/<int:id>', methods=['PUT'])
@token_required  # Decorador para proteger a rota
def update_reservas(matricula, tipo_usuario, is_admin, id):
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
                        <img src="https://reserva-lab-nassau.s3.amazonaws.com/assets/uninassau.png" alt="Logo Uninassau" style="width:200px;"/>
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
@reservation_bp.route('/rejeicoes/<int:pedido_id>', methods=['GET'])
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
@reservation_bp.route('/rejeitar/pedido/<int:id>', methods=['POST'])
@token_required  # Decorador para proteger a rota
def rejeitar_pedido(matricula, tipo_usuario, is_admin, id):
    if not is_admin:  # Restrição para usuários não administradores
        return jsonify({'message': 'Acesso negado! Apenas administradores podem acessar esta rota.'}), 403
    
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
                        <img src="https://reserva-lab-nassau.s3.amazonaws.com/assets/uninassau.png" alt="Logo Uninassau" style="width:200px;"/>
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
@reservation_bp.route('/aprovar/pedido/<int:id>', methods=['PUT'])
@token_required  # Decorador para proteger a rota
def aprovar_pedido(matrimatricula, tipo_usuario, is_admin, id):
    if not is_admin:  # Restrição para usuários não administradores
        return jsonify({'message': 'Acesso negado! Apenas administradores podem acessar esta rota.'}), 403
    
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
                        <img src="https://reserva-lab-nassau.s3.amazonaws.com/assets/uninassau.png" alt="Logo Uninassau" style="width:200px;"/>
                    </body>
                </html>
                """

                # Enviar o e-mail de aprovação de forma assíncrona
                send_email_async(email, subject, body)
                
                start_datetime = f"{reservation['date']}T{reservation['time']}:00"
                end_datetime = f"{reservation['date']}T{reservation['time_fim']}:00"
                create_outlook_event(nome, email, lab_name, start_datetime, end_datetime)

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
@reservation_bp.route('/notifications/<string:matricula>', methods=['GET'])
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
@reservation_bp.route('/notifications/read', methods=['POST'])
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
@reservation_bp.route('/notifications/clear/<string:matricula>', methods=['DELETE'])
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