# app.py
from flask import Flask, request, jsonify
from flask_cors import CORS
from ROUTES import all_blueprints

app = Flask(__name__)
@app.before_request
def check_origin():
    if request.method == "OPTIONS":
        return  # Ignora as requisições OPTIONS (necessárias para CORS)

    origin = request.headers.get('Origin')
    if origin and origin != "https://reserva-salas-uninassau.netlify.app":
        return jsonify({"message": "Acesso não permitido"}), 403  # Retorna erro 403 se a origem não for permitida

# Configurar CORS
CORS(app, resources={r"/*": {"origins": "https://reserva-salas-uninassau.netlify.app"}})


# Limitar o tamanho do upload para 10 MB
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10 MB

# Registrar todos os blueprints
for blueprint in all_blueprints:
    app.register_blueprint(blueprint)

if __name__ == '__main__':
    app.run(debug=True)
