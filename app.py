from flask import Flask, request, jsonify
from flask_cors import CORS
from ROUTES import all_blueprints

app = Flask(__name__)

# Adicionar uma verificação no cabeçalho User-Agent
@app.before_request
def check_user_agent():
    if request.method == "OPTIONS":
        return  # Ignora as requisições OPTIONS (necessárias para CORS)

    user_agent = request.headers.get('User-Agent', '')
    if "Postman" in user_agent:
        return jsonify({"message": "Acesso não permitido"}), 403  # Bloqueia requisições do Postman

# Configurar CORS
CORS(app, resources={r"/*": {"origins": "https://reserva-salas-uninassau.netlify.app"}})

# Limitar o tamanho do upload para 10 MB
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10 MB

# Registrar todos os blueprints
for blueprint in all_blueprints:
    app.register_blueprint(blueprint)

if __name__ == '__main__':
    app.run(debug=True)
