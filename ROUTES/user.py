from flask import Blueprint, request, jsonify
from CONFIG.db import get_db_connection
from CONFIG.token import token_required
from CONFIG.email import send_email

user_bp = Blueprint('user', __name__)

# Rota para buscar usuários
@user_bp.route('/usuarios', methods=['GET'])
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
@user_bp.route('/usuarios/deletar/<int:user_id>', methods=['DELETE'])
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
                    <img src="https://reserva-lab-nassau.s3.amazonaws.com/assets/uninassau.png" alt="Logo Uninassau" style="width:200px;"/>
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
                    <img src="https://reserva-lab-nassau.s3.amazonaws.com/assets/uninassau.png" alt="Logo Uninassau" style="width:200px;"/>
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
@user_bp.route('/usuarios/aprovar/<int:user_id>', methods=['PUT'])
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
                <img src="https://reserva-lab-nassau.s3.amazonaws.com/assets/uninassau.png" alt="Logo Uninassau" style="width:200px;"/>
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
@user_bp.route('/usuarios/atualizar/<int:user_id>', methods=['PUT'])
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
                    <img src="https://reserva-lab-nassau.s3.amazonaws.com/assets/uninassau.png" alt="Logo Uninassau" style="width:200px;"/>
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
                    <img src="https://reserva-lab-nassau.s3.amazonaws.com/assets/uninassau.png" alt="Logo Uninassau" style="width:200px;"/>
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