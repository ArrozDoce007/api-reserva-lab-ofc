# routes/__init__.py
from .reservation import reservation_bp
from .room import room_bp
from .login_cadastro import login_cadastro_bp
from .user import user_bp
from .hr import hr_bp

# Lista de todos os blueprints para registro
all_blueprints = [reservation_bp, room_bp, login_cadastro_bp, hr_bp, user_bp]