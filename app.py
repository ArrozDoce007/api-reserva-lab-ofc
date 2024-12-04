#app.py
from flask import Flask, request, jsonify
from flask_cors import CORS
from ROUTES import all_blueprints

app = Flask(__name__)

# Configurar CORS
CORS(app, resources={r"/*": {"origins": "https://reserva-salas-uninassau.netlify.app"}})

# Limitar o tamanho do upload para 10 MB
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10 MB

# Registrar todos os blueprints
for blueprint in all_blueprints:
    app.register_blueprint(blueprint)

if __name__ == '__main__':
    app.run(debug=True)
