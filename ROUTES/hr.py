from flask import Blueprint, jsonify
from datetime import datetime
import pytz

hr_bp = Blueprint('hr', __name__)

# Rota data e hora
@hr_bp.route('/time/brazilia', methods=['GET'])
def get_brasilia_time():
    try:
        brasilia_tz = pytz.timezone('America/Sao_Paulo')
        brasilia_time = datetime.now(brasilia_tz)
        formatted_time = brasilia_time.strftime('%Y-%m-%dT%H:%M:%S')
        return jsonify({'datetime': formatted_time})
    except Exception as e:
        print(f"Erro: {e}")
        return jsonify({"error": "Erro ao obter a data e hora atual"}), 500