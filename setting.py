import os
import random
import secrets
import string
import threading

from flask import Flask
from flask_sqlalchemy import SQLAlchemy

# КОНФИГИ САЙТА КОНСТАНТЫ

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _env_flag(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ('1', 'true', 'yes', 'on', 'да')


# --- настройки запуска (можно переопределить переменными окружения) ---
# 0.0.0.0 — сайт виден друзьям в локальной сети / Hamachi / Radmin VPN.
# 127.0.0.1 — сайт виден только на этом компьютере.
HOST = os.environ.get('KINOBUDKA_HOST', '0.0.0.0')
PORT = int(os.environ.get('KINOBUDKA_PORT', '5000'))
DEBUG = _env_flag('KINOBUDKA_DEBUG')

# Папка с вашими видеофайлами («Моя медиатека» на странице «Фильмы»).
MEDIA_DIR = os.path.abspath(os.environ.get('KINOBUDKA_MEDIA') or os.path.join(BASE_DIR, 'media'))

# Сколько секунд живёт комната, в которой никого не осталось.
ROOM_TTL = int(os.environ.get('KINOBUDKA_ROOM_TTL', '600'))

FILMS_DB = os.path.join(BASE_DIR, 'instance', 'films.db')
UPLOADS_DIR = os.path.join(BASE_DIR, 'uploads')
DEFAULT_AVATAR = 'image114.png'

app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'  # класс бд
app.config['SQLALCHEMY_BINDS'] = {
    'user_db': 'sqlite:///users.db',
    'films_db': 'sqlite:///films.db'
}
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # максимальный размер загружаемого файла (аватарки)


def _load_secret_key():
    """Секретный ключ: из переменной окружения или из файла instance/secret_key.

    Файл создаётся при первом запуске и не попадает в git, поэтому у каждой
    установки свой ключ и подделать cookie сессии (а значит и права админа) нельзя.
    """
    key = os.environ.get('KINOBUDKA_SECRET_KEY')
    if key:
        return key
    path = os.path.join(app.instance_path, 'secret_key')
    try:
        with open(path, encoding='utf-8') as file:
            key = file.read().strip()
        if key:
            return key
    except OSError:
        pass
    key = secrets.token_hex(32)
    try:
        os.makedirs(app.instance_path, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as file:
            file.write(key)
    except OSError:
        pass  # не смогли сохранить — ключ будет жить до перезапуска
    return key


app.config['SECRET_KEY'] = _load_secret_key()  # секретный ключ

db = SQLAlchemy(app)  # создание класса бд

rooms = {}
rooms_lock = threading.RLock()  # комнаты меняются из нескольких потоков сразу


# для создания бд, если надо создать базу данных просто вызвать эту функцию перед запуском сайта
def create_db():
    with app.app_context():
        db.create_all()


# функц для создания радндомной посл букв и цифр
def create_name_room():
    while True:
        name = ''.join(
            random.choices(
                string.ascii_letters + string.digits,
                k=10
            )
        )
        if name not in rooms:
            return name
