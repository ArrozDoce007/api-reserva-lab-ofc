# app.py
from flask import Flask, jsonify
from flask_cors import CORS
from ROUTES import all_blueprints

app = Flask(__name__)
CORS(app)

# Limitar o tamanho do upload para 10 MB
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10 MB

# Gerenciamento de erros para arquivo muito grande
@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({'error': 'O arquivo enviado é muito grande. O tamanho máximo permitido é de 10 MB.'}), 413

# Registrar todos os blueprints
for blueprint in all_blueprints:
    app.register_blueprint(blueprint)

if __name__ == '__main__':
    app.run(debug=True)
